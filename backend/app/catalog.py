from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import ValidationError
from sqlalchemy import select
from .db import get_db
from .models import Project, Competitor, Fact, Question, QuestionVersion, Source, Batch, Action, Content, Diagnosis, Opportunity, Page, Publisher, Research, ResearchSourceSnapshot, Experiment, OperationRule, now
from .schemas import ProjectCreate, CompetitorCreate, FactCreate, QuestionCreate, SourceCreate
from .common import require, rows, serialize

router = APIRouter()


def validate_patch(obj, patch, schema):
    fields = set(schema.model_fields)
    if not patch or set(patch) - fields:
        raise HTTPException(422, "更新字段为空或包含不可修改字段")
    data = {field: getattr(obj, field) for field in fields}
    try:
        return schema.model_validate({**data, **patch}).model_dump()
    except ValidationError:
        raise HTTPException(422, "更新内容不符合字段约束，请检查必填值、URL、时间和配置")


def save(db, obj):
    db.add(obj)
    db.commit()
    return serialize(obj)


def update(db, obj, patch, schema):
    data = validate_patch(obj, patch, schema)
    for key, value in data.items():
        setattr(obj, key, value)
    return save(db, obj)


def current_question(db, question):
    version = db.scalar(select(QuestionVersion).where(QuestionVersion.question_id == question.id).order_by(QuestionVersion.version.desc()).limit(1))
    return {**serialize(question), "current_version": serialize(version)}


@router.get("/projects")
def projects(db=Depends(get_db)):
    return [serialize(item) for item in rows(db, Project)]


@router.post("/projects", status_code=201)
def create_project(payload: ProjectCreate, db=Depends(get_db)):
    return save(db, Project(**payload.model_dump()))


@router.get("/projects/{identifier}")
def project(identifier: int, db=Depends(get_db)):
    return serialize(require(db, Project, identifier))


@router.patch("/projects/{identifier}")
def patch_project(identifier: int, payload: dict = Body(...), db=Depends(get_db)):
    return update(db, require(db, Project, identifier), payload, ProjectCreate)


@router.delete("/projects/{identifier}")
def delete_project(identifier: int, db=Depends(get_db)):
    obj = require(db, Project, identifier)
    from .measurement_models import Measurement
    if db.scalar(select(Measurement.id).where(Measurement.project_id == identifier).limit(1)):
        raise HTTPException(409, "项目包含测量记录，请保留项目以保障追溯")
    for model in (Batch, Question, Fact, Competitor, Source, Action, Content, Diagnosis, Opportunity, Page, Publisher, Research, ResearchSourceSnapshot, Experiment, OperationRule):
        if db.scalar(select(model.id).where(model.project_id == identifier).limit(1)):
            raise HTTPException(409, "项目包含业务数据或历史，请保留项目以保障追溯")
    db.delete(obj)
    db.commit()
    return {"deleted": True}


@router.get("/projects/{identifier}/competitors")
def competitors(identifier: int, db=Depends(get_db)):
    require(db, Project, identifier)
    return [serialize(item) for item in rows(db, Competitor, project_id=identifier)]


@router.post("/projects/{identifier}/competitors", status_code=201)
def create_competitor(identifier: int, payload: CompetitorCreate, db=Depends(get_db)):
    require(db, Project, identifier)
    return save(db, Competitor(project_id=identifier, **payload.model_dump()))


@router.patch("/competitors/{identifier}")
def patch_competitor(identifier: int, payload: dict = Body(...), db=Depends(get_db)):
    return update(db, require(db, Competitor, identifier), payload, CompetitorCreate)


@router.delete("/competitors/{identifier}")
def delete_competitor(identifier: int, db=Depends(get_db)):
    db.delete(require(db, Competitor, identifier))
    db.commit()
    return {"deleted": True}


@router.get("/projects/{identifier}/facts")
def facts(identifier: int, include_archived: bool = False, db=Depends(get_db)):
    require(db, Project, identifier)
    return [serialize(item) for item in rows(db, Fact, project_id=identifier) if include_archived or not item.archived]


@router.post("/projects/{identifier}/facts", status_code=201)
def create_fact(identifier: int, payload: FactCreate, db=Depends(get_db)):
    require(db, Project, identifier)
    data = payload.model_dump()
    data["valid_from"] = data["valid_from"] or now().isoformat()
    # Revalidate after supplying the default boundary.
    try:
        FactCreate.model_validate(data)
    except ValidationError:
        raise HTTPException(422, "事实有效结束时间必须晚于开始时间；历史事实请显式填写valid_from")
    return save(db, Fact(project_id=identifier, **data))


@router.patch("/facts/{identifier}")
def patch_fact(identifier: int, payload: dict = Body(...), db=Depends(get_db)):
    obj = require(db, Fact, identifier)
    if obj.archived:
        raise HTTPException(409, "已归档事实不可修改；请新建事实")
    return update(db, obj, payload, FactCreate)


@router.delete("/facts/{identifier}")
def delete_fact(identifier: int, db=Depends(get_db)):
    obj = require(db, Fact, identifier)
    obj.archived = True
    return save(db, obj)


@router.get("/projects/{identifier}/questions")
def questions(identifier: int, include_archived: bool = False, db=Depends(get_db)):
    require(db, Project, identifier)
    return [current_question(db, item) for item in rows(db, Question, project_id=identifier) if include_archived or not item.archived]


@router.post("/projects/{identifier}/questions", status_code=201)
def create_question(identifier: int, payload: QuestionCreate, db=Depends(get_db)):
    require(db, Project, identifier)
    obj = Question(project_id=identifier)
    db.add(obj)
    db.flush()
    db.add(QuestionVersion(question_id=obj.id, version=1, **payload.model_dump()))
    db.commit()
    return current_question(db, obj)


@router.patch("/questions/{identifier}")
def patch_question(identifier: int, payload: dict = Body(...), db=Depends(get_db)):
    obj = require(db, Question, identifier)
    if obj.archived:
        raise HTTPException(409, "已归档问题不可修改；请新建问题")
    current = db.scalar(select(QuestionVersion).where(QuestionVersion.question_id == identifier).order_by(QuestionVersion.version.desc()).limit(1))
    data = validate_patch(current, payload, QuestionCreate)
    db.add(QuestionVersion(question_id=identifier, version=current.version + 1, **data))
    db.commit()
    return current_question(db, obj)


@router.delete("/questions/{identifier}")
def delete_question(identifier: int, db=Depends(get_db)):
    obj = require(db, Question, identifier)
    obj.archived = True
    db.commit()
    return current_question(db, obj)


@router.get("/questions/{identifier}/versions")
def question_versions(identifier: int, db=Depends(get_db)):
    require(db, Question, identifier)
    return [serialize(item) for item in rows(db, QuestionVersion, question_id=identifier)]


@router.get("/projects/{identifier}/sources")
def sources(identifier: int, include_archived: bool = False, db=Depends(get_db)):
    require(db, Project, identifier)
    return [serialize(item) for item in rows(db, Source, project_id=identifier) if include_archived or not item.archived]


@router.post("/projects/{identifier}/sources", status_code=201)
def create_source(identifier: int, payload: SourceCreate, db=Depends(get_db)):
    require(db, Project, identifier)
    return save(db, Source(project_id=identifier, **payload.model_dump()))


@router.patch("/sources/{identifier}")
def patch_source(identifier: int, payload: dict = Body(...), db=Depends(get_db)):
    obj = require(db, Source, identifier)
    if obj.archived:
        raise HTTPException(409, "已归档采集源不可修改")
    return update(db, obj, payload, SourceCreate)


@router.delete("/sources/{identifier}")
def delete_source(identifier: int, db=Depends(get_db)):
    obj = require(db, Source, identifier)
    obj.archived = True
    return save(db, obj)
