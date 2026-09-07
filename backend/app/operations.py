from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import select
from .db import get_db
from .models import (Project, Opportunity, Question, QuestionVersion, Page, PageSnapshot,
                     Action, Content, ContentVersion, PublicationJob, Answer, Batch, Fact, now)
from .common import require, owned, rows, serialize
from .catalog import save, validate_patch
from .content import create_version
from .integrations import generate_content
from .analytics import active_facts
from .operations_schemas import OpportunityCreate, PageCreate, PageDraft
from .publishing import page_ownership, valid_version_facts, verify_job, TERMINAL_FAILURES
from .website import validate_url, capture_page, snapshot_view

router = APIRouter()


def opportunity_references(db, project_id, data):
    questions = owned(db, Question, data["question_ids"], project_id)
    if any(q.archived for q in questions):
        raise HTTPException(422, "新机会不能关联已归档问题")
    owned(db, Page, data["page_ids"], project_id)
    for evidence in data["evidence"]:
        if evidence.get("answer_id") is not None:
            answer = require(db, Answer, evidence["answer_id"])
            batch = require(db, Batch, answer.batch_id)
            if batch.project_id != project_id or answer.validity != "valid" or evidence["quote"] not in answer.text:
                raise HTTPException(422, "机会回答证据必须属于本项目有效回答且引文准确")


@router.get("/projects/{identifier}/opportunities")
def opportunities(identifier: int, db=Depends(get_db)):
    require(db, Project, identifier)
    return [serialize(o) for o in rows(db, Opportunity, project_id=identifier)]


@router.post("/projects/{identifier}/opportunities", status_code=201)
def create_opportunity(identifier: int, payload: OpportunityCreate, db=Depends(get_db)):
    require(db, Project, identifier)
    data = payload.model_dump()
    opportunity_references(db, identifier, data)
    return save(db, Opportunity(project_id=identifier, **data))


@router.patch("/opportunities/{identifier}")
def patch_opportunity(identifier: int, payload: dict = Body(...), db=Depends(get_db)):
    obj = require(db, Opportunity, identifier)
    data = validate_patch(obj, payload, OpportunityCreate)
    opportunity_references(db, obj.project_id, data)
    for key, value in data.items():
        setattr(obj, key, value)
    return save(db, obj)


def latest_job(db, page):
    return db.scalar(select(PublicationJob).where(PublicationJob.page_id == page.id).order_by(PublicationJob.id.desc()).limit(1))


def maintenance_reasons(db, page, job=None):
    reasons = []
    if page.next_review_at and datetime.fromisoformat(page.next_review_at) <= now():
        reasons.append("页面复核时间已到期")
    job = job or latest_job(db, page)
    if job:
        if job.status in TERMINAL_FAILURES:
            reasons.append("发布失败或提交未知，需要人工核实")
        version = require(db, ContentVersion, job.content_version_id)
        try:
            valid_version_facts(db, version)
        except HTTPException:
            reasons.append("发布版本事实已过期、归档或编辑，需要修订")
    return reasons


def page_view(db, page):
    snapshot = db.scalar(select(PageSnapshot).where(PageSnapshot.page_id == page.id).order_by(PageSnapshot.id.desc()).limit(1))
    job = latest_job(db, page)
    return {**serialize(page), "latest_snapshot": snapshot_view(db, snapshot) if snapshot else None,
            "latest_publication": serialize(job) if job else None,
            "maintenance_reasons": maintenance_reasons(db, page, job)}


@router.get("/projects/{identifier}/pages")
def pages(identifier: int, db=Depends(get_db)):
    require(db, Project, identifier)
    return [page_view(db, p) for p in rows(db, Page, project_id=identifier)]


@router.post("/projects/{identifier}/pages", status_code=201)
def create_page(identifier: int, payload: PageCreate, db=Depends(get_db)):
    require(db, Project, identifier)
    data = payload.model_dump()
    data["url"] = validate_url(data["url"])
    obj = Page(project_id=identifier, **data)
    page_ownership(db, obj)
    save(db, obj)
    return page_view(db, obj)


@router.patch("/pages/{identifier}")
def patch_page(identifier: int, payload: dict = Body(...), db=Depends(get_db)):
    page = require(db, Page, identifier)
    data = validate_patch(page, payload, PageCreate)
    data["url"] = validate_url(data["url"])
    if data["url"] != page.url and (rows(db, PageSnapshot, page_id=identifier) or rows(db, PublicationJob, page_id=identifier)):
        raise HTTPException(409, "已有快照或发布历史的页面URL不可改写；请登记新页面")
    for key, value in data.items():
        setattr(page, key, value)
    page_ownership(db, page)
    save(db, page)
    return page_view(db, page)


@router.post("/pages/{identifier}/draft", status_code=201)
def draft(identifier: int, payload: PageDraft, db=Depends(get_db)):
    page = require(db, Page, identifier)
    content = require(db, Content, payload.content_id)
    page_ownership(db, page, content)
    snapshot = require(db, PageSnapshot, payload.snapshot_id)
    if snapshot.page_id != page.id or snapshot.status != "success":
        raise HTTPException(422, "改稿必须选择目标页面成功快照，采集失败不是内容依据")
    questions = owned(db, Question, payload.question_ids, page.project_id)
    if any(q.archived for q in questions):
        raise HTTPException(422, "改稿不能选已归档问题")
    versions = [db.scalar(select(QuestionVersion).where(QuestionVersion.question_id == q.id).order_by(QuestionVersion.version.desc()).limit(1)) for q in questions]
    facts = owned(db, Fact, payload.fact_ids, page.project_id)
    fact_snapshot = [serialize(f) for f in facts]
    if any(f.archived for f in facts) or len(active_facts(fact_snapshot, now())) != len(fact_snapshot):
        raise HTTPException(422, "改稿只能选择当前有效事实")
    generation = {"method": payload.mode, "snapshot_id": snapshot.id, "source_kind": snapshot.source_kind,
                  "question_version_ids": [q.id for q in versions], "questions_snapshot": [serialize(q) for q in versions],
                  "instructions": payload.instructions, "review_required": True}
    after_text = payload.after_text
    fact_ids = payload.fact_ids
    if payload.mode == "model":
        instructions = payload.instructions + "\n目标客户问题（作为编辑目标而非事实）：\n" + "\n".join(q.text for q in versions)
        result = generate_content(instructions, snapshot.visible_text, fact_snapshot)
        after_text, fact_ids = result.text, result.used_fact_ids
        generation["claims"] = [c.model_dump() for c in result.factual_claims]
    return create_version(db, content, snapshot.visible_text, after_text, fact_ids, generation, source_snapshot_id=snapshot.id)


@router.get("/projects/{identifier}/operations/summary")
def summary(identifier: int, db=Depends(get_db)):
    require(db, Project, identifier)
    current = now()
    today_end = current.replace(hour=23, minute=59, second=59, microsecond=999999)
    week_end = current + timedelta(days=7)
    actions = [a for a in rows(db, Action, project_id=identifier) if a.status not in {"done", "cancelled"}]
    ordered = sorted(actions, key=lambda a: (a.due_at is None, datetime.fromisoformat(a.due_at) if a.due_at else datetime.max.replace(tzinfo=timezone.utc), a.id))
    week = [serialize(a) for a in ordered if a.due_at and datetime.fromisoformat(a.due_at) <= week_end]
    today = [serialize(a) for a in ordered if a.due_at and datetime.fromisoformat(a.due_at) <= today_end]
    blocked = [serialize(a) for a in ordered if a.status == "blocked"]
    pending, ready = [], []
    for content in rows(db, Content, project_id=identifier):
        version = db.scalar(select(ContentVersion).where(ContentVersion.content_id == content.id).order_by(ContentVersion.version.desc()).limit(1))
        if version and version.review_status == "pending":
            pending.append({**serialize(version), "content_title": content.title})
        elif version and version.review_status == "approved" and not rows(db, PublicationJob, content_version_id=version.id):
            blocker = ""
            try:
                valid_version_facts(db, version)
            except HTTPException as exc:
                blocker = exc.detail
            ready.append({**serialize(version), "content_title": content.title, "target_url": content.target_url, "blocked_reason": blocker})
    due = [page_view(db, p) for p in rows(db, Page, project_id=identifier) if maintenance_reasons(db, p)]
    failed = [serialize(j) for j in rows(db, PublicationJob, project_id=identifier) if j.status in TERMINAL_FAILURES]
    awaiting = [serialize(j) for j in rows(db, PublicationJob, project_id=identifier) if j.status in {"awaiting_verification", "submitting"}]
    steps = []
    for a in blocked:
        steps.append({"kind": "action", "id": a["id"], "title": a["title"], "reason": a["blocked_reason"], "href": "/?section=opportunities"})
    for v in pending:
        steps.append({"kind": "review", "id": v["id"], "title": v["content_title"], "reason": "最新内容版本等待人工审核", "href": "/?section=content"})
    for v in ready:
        steps.append({"kind": "publish", "id": v["id"], "title": v["content_title"], "reason": v["blocked_reason"] or "已审核版本等待操作员显式发布", "href": "/?section=content"})
    for j in awaiting:
        steps.append({"kind": "verify", "id": j["id"], "title": j["target_url"], "reason": "提交中，请勿重复点击" if j["status"] == "submitting" else "发布记录尚未核验批准正文", "href": "/?section=content"})
    for p in due:
        steps.append({"kind": "maintenance", "id": p["id"], "title": p["title"] or p["url"], "reason": "；".join(p["maintenance_reasons"]), "href": "/?section=pages"})
    for a in today:
        if a["status"] != "blocked":
            steps.append({"kind": "action", "id": a["id"], "title": a["title"], "reason": "任务已到期" if datetime.fromisoformat(a["due_at"]) <= current else "任务今日到期", "href": "/?section=opportunities"})
    return {"project_id": identifier, "as_of": current.isoformat(), "counts": {
        "open_opportunities": sum(o.status != "closed" for o in rows(db, Opportunity, project_id=identifier)),
        "week_plan": len(week), "today": len(today), "blocked": len(blocked), "pending_review": len(pending),
        "maintenance_due": len(due), "failed_publications": len(failed), "ready_to_publish": len(ready), "awaiting_verification": len(awaiting)},
        "week_plan": week, "today": today, "blocked": blocked, "pending_review": pending,
        "maintenance_due": due, "failed_publications": failed, "ready_to_publish": ready, "awaiting_verification": awaiting, "next_steps": steps}


@router.post("/projects/{identifier}/operations/check-due")
def check_due(identifier: int, db=Depends(get_db)):
    require(db, Project, identifier)
    checked, actions = [], []
    current = now()
    for page in rows(db, Page, project_id=identifier):
        reasons = maintenance_reasons(db, page)
        if not reasons:
            continue
        job = latest_job(db, page)
        if job and job.status != "submitting":
            try:
                result = verify_job(db, job)
                snapshot_id = result["verifications"][-1]["snapshot_id"]
                status = result["status"]
            except HTTPException:
                snapshot = capture_page(db, page)
                snapshot_id, status = snapshot.id, "facts_or_ownership_blocked"
        else:
            snapshot = capture_page(db, page)
            snapshot_id, status = snapshot.id, snapshot.status
        checked.append({"page_id": page.id, "publication_job_id": job.id if job else None, "status": status, "snapshot_id": snapshot_id})
        title = "页面维护复核：" + (page.title or page.url)
        action = next((a for a in rows(db, Action, project_id=identifier) if a.page_id == page.id and a.title == title and a.status not in {"done", "cancelled"}), None)
        if not action:
            action = Action(project_id=identifier, title=title, page_id=page.id, target_page=page.url,
                            owner=page.owner or "本地操作员", due_at=current.isoformat(), status="todo",
                            acceptance_method="复核事实有效期、修订并审核内容；页面完整批准正文核验通过，人工完成维护任务",
                            blocked_reason="；".join(reasons))
            db.add(action)
        page.next_review_at = (current + timedelta(days=page.review_interval_days)).isoformat()
        db.commit()
        actions.append(serialize(action))
    return {"checked_at": current.isoformat(), "checked": checked, "actions": actions}
