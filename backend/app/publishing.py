import base64
import hashlib
import json
import os
from datetime import datetime
from urllib.parse import urlsplit
from fastapi import APIRouter, Body, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .db import get_db
from .models import (Project, Page, Publisher, Content, ContentVersion, Fact,
                     PublicationJob, PublicationVerification, now)
from .common import require, rows, owned, serialize
from .catalog import save
from .analytics import active_facts
from .operations_schemas import ReviewPayload, PublisherCreate, PublishJobCreate, ExternalPublication
from .website import capture_page, validate_url, request_url, controlled_local_url, visible_text, FetchError

router = APIRouter()
TERMINAL_FAILURES = {"execution_failed", "verification_failed", "submission_unknown"}


def normalized(text):
    return " ".join(text.split())


def origin(url):
    parts = urlsplit(validate_url(url))
    return parts.scheme, parts.hostname, parts.port or (443 if parts.scheme == "https" else 80)


def page_ownership(db, page, content=None):
    project = require(db, Project, page.project_id)
    if not project.website_url or origin(page.url) != origin(project.website_url):
        raise HTTPException(422, "登记页面必须属于项目官网origin；请先维护官网地址")
    if content and (content.project_id != page.project_id or validate_url(content.target_url) != validate_url(page.url)):
        raise HTTPException(422, "内容目标URL必须匹配同项目登记页面")


def valid_version_facts(db, version, at=None):
    snapshot = version.facts_snapshot
    if len(active_facts(snapshot, at or now())) != len(snapshot):
        raise HTTPException(422, "稿件事实已过期或尚未有效；请创建修订版本")
    content = require(db, Content, version.content_id)
    current = owned(db, Fact, version.fact_ids, content.project_id)
    by_id = {f["id"]: f for f in snapshot}
    for fact in current:
        frozen = by_id.get(fact.id, {})
        if fact.archived or any(getattr(fact, k) != frozen.get(k) for k in ("claim", "source_url", "valid_from", "valid_to")):
            raise HTTPException(422, "事实已归档或编辑，旧批准版本依据已失效；请创建修订版本")
    if len(current) != len(snapshot):
        raise HTTPException(422, "稿件事实依据不完整")


def publication_gate(db, version, page):
    if version.review_status != "approved":
        raise HTTPException(409, "内容版本必须先经人工审核通过")
    if not normalized(visible_text(version.after_text)):
        raise HTTPException(422, "批准稿件必须包含可见正文，不能只有标记或隐藏内容")
    valid_version_facts(db, version)
    content = require(db, Content, version.content_id)
    page_ownership(db, page, content)
    return content


def job_view(db, job):
    return {**serialize(job), "verifications": [serialize(v) for v in rows(db, PublicationVerification, publication_job_id=job.id)]}


@router.post("/content-versions/{identifier}/review")
def review(identifier: int, payload: ReviewPayload, db=Depends(get_db)):
    version = require(db, ContentVersion, identifier)
    if rows(db, PublicationJob, content_version_id=identifier):
        raise HTTPException(409, "已有发布记录的版本审核已冻结；请创建新版本")
    if payload.status == "approved":
        valid_version_facts(db, version)
    version.review_status = payload.status
    version.reviewer = payload.reviewer
    version.review_note = payload.note
    version.reviewed_at = now().isoformat()
    return save(db, version)


def publisher_scope(db, project_id, site_url):
    project = require(db, Project, project_id)
    site = validate_url(site_url).rstrip("/")
    parts = urlsplit(site)
    if parts.query or parts.fragment:
        raise HTTPException(422, "WordPress站点根地址不可包含查询或片段")
    if not project.website_url or origin(site) != origin(project.website_url):
        raise HTTPException(422, "WordPress站点必须属于项目官网origin")
    if parts.scheme != "https" and not controlled_local_url(site):
        raise HTTPException(422, "WordPress Application Password必须使用HTTPS；仅显式allowlist受控回环可HTTP验收")
    return site


@router.get("/projects/{identifier}/publishers")
def publishers(identifier: int, db=Depends(get_db)):
    require(db, Project, identifier)
    return [serialize(p) for p in rows(db, Publisher, project_id=identifier)]


@router.post("/projects/{identifier}/publishers", status_code=201)
def create_publisher(identifier: int, payload: PublisherCreate, db=Depends(get_db)):
    data = payload.model_dump()
    data["site_url"] = publisher_scope(db, identifier, payload.site_url)
    return save(db, Publisher(project_id=identifier, **data))


@router.patch("/publishers/{identifier}")
def patch_publisher(identifier: int, payload: dict = Body(...), db=Depends(get_db)):
    from .catalog import validate_patch
    publisher = require(db, Publisher, identifier)
    data = validate_patch(publisher, payload, PublisherCreate)
    data["site_url"] = publisher_scope(db, publisher.project_id, data["site_url"])
    for key, value in data.items():
        setattr(publisher, key, value)
    return save(db, publisher)


def wp_headers(config):
    base = os.getenv("WORDPRESS_URL", "").rstrip("/")
    username = os.getenv("WORDPRESS_USERNAME", "")
    password = os.getenv("WORDPRESS_APPLICATION_PASSWORD", "")
    if not base or not username or not password:
        raise HTTPException(503, "请在服务器配置WORDPRESS_URL、WORDPRESS_USERNAME、WORDPRESS_APPLICATION_PASSWORD")
    if validate_url(base).rstrip("/") != config["site_url"]:
        raise HTTPException(503, "服务器WordPress根地址与发布器不匹配；未发送凭据")
    if urlsplit(base).scheme != "https" and not controlled_local_url(base):
        raise HTTPException(503, "带认证的WordPress请求必须HTTPS；HTTP仅用于显式allowlist受控回环")
    credential = base64.b64encode((username + ":" + password).encode()).decode()
    return {"Authorization": "Basic " + credential, "Content-Type": "application/json", "Accept": "application/json"}


def wp_request(config, method, body=None):
    headers = wp_headers(config)
    url = config["site_url"] + f'/wp-json/wp/v2/{config["resource"]}/{config["post_id"]}'
    response = request_url(url, method=method, body=json.dumps(body, ensure_ascii=False).encode() if body is not None else None, headers=headers)
    try:
        data = json.loads(response["html"])
    except (ValueError, TypeError):
        data = None
    return response, data


def wp_identity(data, config, target_url):
    if not isinstance(data, dict) or type(data.get("id")) is not int or data["id"] != config["post_id"] or not isinstance(data.get("link"), str):
        return False
    try:
        return validate_url(data["link"]) == validate_url(target_url)
    except HTTPException:
        return False


def wp_evidence(response, data):
    return {"http_status": response["http_status"], "response_hash": hashlib.sha256(response["html"].encode()).hexdigest(),
            "id": data.get("id") if isinstance(data, dict) else None,
            "link": data.get("link") if isinstance(data, dict) else None,
            "status": data.get("status") if isinstance(data, dict) else None, "observed_at": now().isoformat()}


def reserve_job(db, version, page, source_kind, publisher=None):
    existing = db.scalar(select(PublicationJob).where(PublicationJob.content_version_id == version.id, PublicationJob.page_id == page.id))
    if existing:
        if existing.source_kind != source_kind or (publisher and existing.publisher_id != publisher.id):
            raise HTTPException(409, "此版本页面已有其他发布来源记录，不能重复外发")
        return existing, False
    content = publication_gate(db, version, page)
    job = PublicationJob(project_id=content.project_id, content_version_id=version.id, page_id=page.id,
                         publisher_id=publisher.id if publisher else None, source_kind=source_kind,
                         status="submitting" if publisher else "awaiting_verification", target_url=page.url,
                         expected_hash=hashlib.sha256(normalized(visible_text(version.after_text)).encode()).hexdigest())
    if publisher:
        if not publisher.enabled or publisher.project_id != content.project_id:
            raise HTTPException(422, "发布器未启用或不属于当前项目")
        publisher_scope(db, content.project_id, publisher.site_url)
        config = {"site_url": publisher.site_url, "resource": publisher.resource, "post_id": publisher.post_id,
                  "approved_content": version.after_text, "title": content.title}
        wp_headers(config)
        try:
            response, data = wp_request(config, "GET")
        except FetchError:
            raise HTTPException(502, "WordPress更新前身份核对失败；未提交写请求")
        if response["http_status"] != 200 or not wp_identity(data, config, page.url):
            raise HTTPException(422, "WordPress资源ID/link与登记目标页面不匹配或不可读取；未提交写请求")
        job.config_snapshot = config
        job.execution_evidence = {"preflight": wp_evidence(response, data)}
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(PublicationJob).where(PublicationJob.content_version_id == version.id, PublicationJob.page_id == page.id))
        if not existing:
            raise
        if existing.source_kind != source_kind or (publisher and existing.publisher_id != publisher.id):
            raise HTTPException(409, "并发操作已创建不同发布来源，未再次提交")
        return existing, False
    return job, True


@router.post("/content-versions/{identifier}/publish-jobs", status_code=201)
def publish(identifier: int, payload: PublishJobCreate, response: Response, db=Depends(get_db)):
    return publish_version(identifier, payload, response, db)


def publish_version(identifier, payload, response, db, *, expected_baseline=None, authorization_guard=None):
    version = require(db, ContentVersion, identifier)
    publisher = require(db, Publisher, payload.publisher_id)
    page = require(db, Page, payload.page_id)
    if expected_baseline is not None and not db.scalar(select(PublicationJob).where(PublicationJob.content_version_id == version.id, PublicationJob.page_id == page.id)):
        config = {"site_url": publisher.site_url, "resource": publisher.resource, "post_id": publisher.post_id}
        try:
            observed, data = wp_request(config, "GET")
        except FetchError:
            raise HTTPException(502, "发布前目标正文基准读取失败；未提交更新")
        content = data.get("content", {}) if isinstance(data, dict) else {}
        representation = expected_baseline["representation"]
        body = content.get(representation) if isinstance(content, dict) else None
        if (observed["http_status"] != 200 or not wp_identity(data, config, page.url)
                or not isinstance(body, str)
                or hashlib.sha256(body.encode("utf-8")).hexdigest() != expected_baseline["content_hash"]
                or data.get("modified_gmt") != expected_baseline.get("modified_gmt")):
            raise HTTPException(409, "WordPress正文或修改时间已改变；旧审批已陈旧，未提交更新，请重新取证审核")
    job, created = reserve_job(db, version, page, "wordpress", publisher)
    if not created:
        response.status_code = 200
        return job_view(db, job)
    if authorization_guard is not None:
        authorization_guard()
    try:
        result, data = wp_request(job.config_snapshot, "POST", {"content": version.after_text, "title": job.config_snapshot["title"], "status": "publish"})
        job.execution_evidence = {**job.execution_evidence, "submission": wp_evidence(result, data)}
        status = result["http_status"]
        if status in {401, 403, 404, 400, 405, 422}:
            job.status, job.error = "execution_failed", "WordPress拒绝更新；请核对Application Password权限或资源配置"
        elif 200 <= status < 300 and wp_identity(data, job.config_snapshot, job.target_url) and data.get("status") == "publish":
            job.status, job.error = "awaiting_verification", ""
        else:
            job.status, job.error = "submission_unknown", "更新响应不能证明目标资源已发布；可显式同步/核验，绝不自动重发"
    except (FetchError, HTTPException):
        job.status = "submission_unknown"
        job.error = "更新提交结果未知；请GET核对目标正文，绝不自动重发"
    db.commit()
    return job_view(db, job)


@router.post("/content-versions/{identifier}/external-publication", status_code=201)
def external_publication(identifier: int, payload: ExternalPublication, response: Response, db=Depends(get_db)):
    version = require(db, ContentVersion, identifier)
    page = require(db, Page, payload.page_id)
    if payload.published_at and datetime.fromisoformat(payload.published_at) > now():
        raise HTTPException(422, "外部发布记录不能来自未来")
    publication_gate(db, version, page)
    valid_version_facts(db, version, payload.published_at)
    job, created = reserve_job(db, version, page, "external_record")
    if created:
        job.execution_evidence = {"note": payload.note, "operator_reported_at": payload.published_at or now().isoformat(), "system_issued_write": False}
        version.published_at = version.published_at or payload.published_at or now().isoformat()
        db.commit()
    else:
        response.status_code = 200
    return job_view(db, job)


@router.get("/projects/{identifier}/publication-jobs")
def publication_jobs(identifier: int, db=Depends(get_db)):
    require(db, Project, identifier)
    return [serialize(j) for j in rows(db, PublicationJob, project_id=identifier)]


@router.get("/publication-jobs/{identifier}")
def publication_job(identifier: int, db=Depends(get_db)):
    return job_view(db, require(db, PublicationJob, identifier))


@router.post("/publication-jobs/{identifier}/sync")
def sync_publication(identifier: int, db=Depends(get_db)):
    job = require(db, PublicationJob, identifier)
    if job.source_kind != "wordpress":
        raise HTTPException(409, "外部发布记录没有WordPress API资源可同步；请直接核验")
    try:
        response, data = wp_request(job.config_snapshot, "GET")
        job.execution_evidence = {**job.execution_evidence, "sync": wp_evidence(response, data)}
        if response["http_status"] == 200 and wp_identity(data, job.config_snapshot, job.target_url) and data.get("status") == "publish":
            if job.status != "verified":
                job.status = "awaiting_verification"
            job.error = ""
        else:
            job.status, job.error = "execution_failed", "WordPress资源不可用、身份不匹配或非公开发布状态；未认定上线"
    except FetchError:
        job.error = "WordPress只读同步失败，保留当前状态；可显式重新核验，未发出更新"
    db.commit()
    return job_view(db, job)


def verify_job(db, job):
    if job.status == "submitting":
        raise HTTPException(409, "提交仍在进行中；请等待结果或先显式只读同步")
    page = require(db, Page, job.page_id)
    version = require(db, ContentVersion, job.content_version_id)
    publication_gate(db, version, page)
    snapshot = capture_page(db, page)
    expected = normalized(visible_text(version.after_text))
    same_origin = bool(snapshot.final_url) and origin(snapshot.final_url) == origin(job.target_url)
    matched = snapshot.status == "success" and same_origin and bool(expected) and expected in normalized(snapshot.visible_text)
    job.status = "verified" if matched else "verification_failed"
    summary = "批准版本完整可见正文已匹配；这不是索引、引用或GEO效果证明" if matched else "页面抓取失败、跳转不属于官网或可见正文不匹配批准完整版本；未重新发布"
    evidence = PublicationVerification(publication_job_id=job.id, snapshot_id=snapshot.id, status=job.status,
                                       matched_by="visible_body" if matched else "", response_hash=snapshot.content_hash, summary=summary)
    db.add(evidence)
    job.error = "" if matched else summary
    if matched:
        job.verified_at = now().isoformat()
        version.published_at = version.published_at or job.verified_at
    db.commit()
    return job_view(db, job)


@router.post("/publication-jobs/{identifier}/verify")
def verify(identifier: int, db=Depends(get_db)):
    return verify_job(db, require(db, PublicationJob, identifier))
