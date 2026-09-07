from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy import select, func
from .db import get_db
from .models import Project, Question, Fact, Diagnosis, Action, Content, ContentVersion, Batch, Opportunity, Page, PageFinding, PublicationJob, now
from .schemas import DiagnosisReview, ActionCreate, ContentCreate, VersionCreate, GeneratePayload
from .common import require, rows, owned, serialize
from .catalog import save, update, validate_patch
from .integrations import generate_content
from .analytics import active_facts

router = APIRouter()


def action_references(db, project_id, data):
    owned(db, Question, data["question_ids"], project_id)
    owned(db, Fact, data["fact_ids"], project_id)
    owned(db, Diagnosis, data["diagnosis_ids"], project_id)
    for key, model in (("opportunity_id", Opportunity), ("page_id", Page)):
        if data.get(key) is not None:
            owned(db, model, [data[key]], project_id)
    if data.get("page_id") is not None:
        page = require(db, Page, data["page_id"])
        if data["target_page"] and data["target_page"] != page.url:
            raise HTTPException(422, "行动目标URL必须匹配登记页面")
        data["target_page"] = page.url
    if data.get("finding_id") is not None:
        finding = require(db, PageFinding, data["finding_id"])
        if finding.page_id != data.get("page_id"):
            raise HTTPException(422, "诊断发现必须属于行动目标页面")


def content_view(db, obj):
    return {**serialize(obj), "versions": [serialize(v) for v in rows(db, ContentVersion, content_id=obj.id)]}


@router.get("/projects/{identifier}/diagnoses")
def diagnoses(identifier: int, db=Depends(get_db)):
    require(db, Project, identifier)
    return [serialize(item) for item in rows(db, Diagnosis, project_id=identifier)]


@router.patch("/diagnoses/{identifier}")
def review_diagnosis(identifier: int, payload: DiagnosisReview, db=Depends(get_db)):
    obj = require(db, Diagnosis, identifier)
    obj.review_status = payload.review_status
    return save(db, obj)


@router.get("/projects/{identifier}/actions")
def actions(identifier: int, db=Depends(get_db)):
    require(db, Project, identifier)
    return [serialize(item) for item in rows(db, Action, project_id=identifier)]


@router.post("/projects/{identifier}/actions", status_code=201)
def create_action(identifier: int, payload: ActionCreate, db=Depends(get_db)):
    require(db, Project, identifier)
    data = payload.model_dump()
    action_references(db, identifier, data)
    return save(db, Action(project_id=identifier, **data))


@router.patch("/actions/{identifier}")
def patch_action(identifier: int, payload: dict = Body(...), db=Depends(get_db)):
    obj = require(db, Action, identifier)
    data = validate_patch(obj, payload, ActionCreate)
    action_references(db, obj.project_id, data)
    for key, value in data.items():
        setattr(obj, key, value)
    return save(db, obj)


@router.delete("/actions/{identifier}")
def delete_action(identifier: int, db=Depends(get_db)):
    obj = require(db, Action, identifier)
    if rows(db, Content, action_id=identifier) or any(identifier in b.action_ids for b in rows(db, Batch, project_id=obj.project_id)):
        raise HTTPException(409, "行动已关联内容或复测，请改为cancelled保留历史")
    db.delete(obj)
    db.commit()
    return {"deleted": True}


@router.get("/projects/{identifier}/contents")
def contents(identifier: int, db=Depends(get_db)):
    require(db, Project, identifier)
    return [content_view(db, item) for item in rows(db, Content, project_id=identifier)]


@router.post("/projects/{identifier}/contents", status_code=201)
def create_content(identifier: int, payload: ContentCreate, db=Depends(get_db)):
    require(db, Project, identifier)
    if payload.action_id is not None:
        owned(db, Action, [payload.action_id], identifier)
    obj = Content(project_id=identifier, **payload.model_dump())
    db.add(obj)
    db.commit()
    return content_view(db, obj)


@router.patch("/contents/{identifier}")
def patch_content(identifier: int, payload: dict = Body(...), db=Depends(get_db)):
    obj = require(db, Content, identifier)
    if set(payload) - {"title", "target_url"}:
        raise HTTPException(422, "仅可修改标题与目标URL")
    update(db, obj, payload, ContentCreate)
    return content_view(db, obj)


@router.delete("/contents/{identifier}")
def delete_content(identifier: int, db=Depends(get_db)):
    obj = require(db, Content, identifier)
    versions = rows(db, ContentVersion, content_id=identifier)
    ids = {v.id for v in versions}
    if any(v.published_at for v in versions) or any(rows(db, PublicationJob, content_version_id=v.id) for v in versions) or any(ids & set(b.content_version_ids) for b in rows(db, Batch, project_id=obj.project_id)):
        raise HTTPException(409, "内容已发布或被复测引用，禁止删除历史")
    for version in versions:
        db.delete(version)
    db.delete(obj)
    db.commit()
    return {"deleted": True}


def create_version(db, content, before_text, after_text, fact_ids, generation=None, source_snapshot_id=None):
    facts = owned(db, Fact, fact_ids, content.project_id)
    if any(f.archived for f in facts):
        raise HTTPException(422, "新内容不能使用已归档事实")
    version = (db.scalar(select(func.max(ContentVersion.version)).where(ContentVersion.content_id == content.id)) or 0) + 1
    obj = ContentVersion(content_id=content.id, version=version, before_text=before_text, after_text=after_text, fact_ids=list(dict.fromkeys(fact_ids)), facts_snapshot=[serialize(f) for f in facts], generation=generation or {"method": "manual", "review_required": True}, source_snapshot_id=source_snapshot_id)
    return save(db, obj)


@router.post("/contents/{identifier}/versions", status_code=201)
def add_version(identifier: int, payload: VersionCreate, db=Depends(get_db)):
    return create_version(db, require(db, Content, identifier), payload.before_text, payload.after_text, payload.fact_ids)


@router.post("/contents/{identifier}/generate", status_code=201)
def generate(identifier: int, payload: GeneratePayload, db=Depends(get_db)):
    obj = require(db, Content, identifier)
    facts = owned(db, Fact, payload.fact_ids, obj.project_id)
    if any(f.archived for f in facts):
        raise HTTPException(422, "生成不能使用已归档事实")
    snapshot = [serialize(f) for f in facts]
    if len(active_facts(snapshot, now())) != len(snapshot):
        raise HTTPException(422, "生成只能使用当前有效事实，请检查有效时间")
    result = generate_content(payload.instructions, payload.before_text, snapshot)
    return create_version(db, obj, payload.before_text, result.text, result.used_fact_ids, {"method": "model", "review_required": True, "instructions": payload.instructions, "claims": [claim.model_dump() for claim in result.factual_claims], "notice": "引用偏移校验不等于事实语义保证；此稿必须由人工审核后发布"})


