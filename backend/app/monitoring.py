import copy
import re
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy import select
from .db import get_db
from .models import Project, Question, QuestionVersion, Source, Fact, Competitor, Batch, Answer, Job, Analysis, AnalysisRun, Action, Content, ContentVersion, PublicationJob, now
from .schemas import BatchCreate, ImportPayload, AnalyzePayload
from .common import require, owned, rows, serialize, redact
from .catalog import current_question
from .integrations import Razormind, RemoteError, record_answer, validity
from .analytics import analyze_batch, overview, diagnose, compare_groups, latest_analyses

router = APIRouter()


def observation_time(data, supplied=None):
    received = now()
    observed = None
    if isinstance(supplied, str):
        try:
            parsed = datetime.fromisoformat(supplied.replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                observed = parsed.isoformat()
        except ValueError:
            pass
    data["observed_at"] = observed or received.isoformat()
    data["created_at"] = received
    raw = data.get("raw", {})
    provenance = {"basis": "provided_observation" if observed else "server_received", "received_at": received.isoformat()}
    if "_geo_observation_time" in raw:
        provenance["original_input_value"] = raw["_geo_observation_time"]
    data["raw"] = {**raw, "_geo_observation_time": provenance}


def extract_urls(text):
    return [{"url": url, "title": "", "type": "text_url_extraction"} for url in dict.fromkeys(re.findall(r"https?://[^\s<>\"'）)\]，。]+", text))]


def lock_batch(db, identifier):
    batch = db.scalar(select(Batch).where(Batch.id == identifier).with_for_update())
    if not batch:
        raise HTTPException(404, "批次不存在")
    return batch


@router.get("/projects/{identifier}/batches")
def batches(identifier: int, db=Depends(get_db)):
    require(db, Project, identifier)
    return [serialize(item) for item in rows(db, Batch, project_id=identifier)]


@router.post("/projects/{identifier}/batches", status_code=201)
def create_batch(identifier: int, payload: BatchCreate, db=Depends(get_db)):
    project = require(db, Project, identifier)
    owned(db, Action, payload.action_ids, identifier)
    for version_id in payload.content_version_ids:
        version = require(db, ContentVersion, version_id)
        content = require(db, Content, version.content_id)
        if content.project_id != identifier:
            raise HTTPException(422, "内容版本不属于当前项目")
        if not any(j.status == "verified" for j in rows(db, PublicationJob, content_version_id=version_id)):
            raise HTTPException(422, "复测关联内容必须已核验批准版本完整可见正文；历史published_at或人工声明不足")
    if payload.baseline_batch_id:
        baseline = require(db, Batch, payload.baseline_batch_id)
        if baseline.project_id != identifier:
            raise HTTPException(422, "基线批次不属于当前项目")
        if not rows(db, Answer, batch_id=baseline.id):
            raise HTTPException(422, "基线尚无回答样本，不能创建复测")
        if payload.question_ids is not None and payload.question_ids != [q["question_id"] for q in baseline.snapshot["questions"]]:
            raise HTTPException(422, "复测问题必须与基线冻结版本一致，请省略question_ids")
        if payload.source_ids is not None and payload.source_ids != [s["id"] for s in baseline.snapshot["sources"]]:
            raise HTTPException(422, "复测采集源必须与基线一致")
        if payload.sampling is not None and payload.sampling != baseline.snapshot["sampling"]:
            raise HTTPException(422, "复测采样条件不得偏离基线")
        if payload.mode is not None and payload.mode != baseline.mode:
            raise HTTPException(422, "复测采样模式必须与基线一致")
        snapshot = copy.deepcopy(baseline.snapshot)
        mode = baseline.mode
    else:
        if not payload.question_ids:
            raise HTTPException(422, "请选择至少一个问题")
        questions = owned(db, Question, payload.question_ids, identifier)
        if any(q.archived for q in questions):
            raise HTTPException(422, "不能用已归档问题创建新基线")
        sources = owned(db, Source, payload.source_ids or [], identifier)
        if any(s.archived for s in sources):
            raise HTTPException(422, "不能用已归档采集源创建新基线")
        mode = payload.mode or ("collection" if sources else "manual")
        if mode == "manual" and sources:
            raise HTTPException(422, "人工批次不应绑定自动采集源")
        if mode != "manual" and not sources:
            raise HTTPException(422, "自动批次必须绑定采集源")
        sampling = copy.deepcopy(payload.sampling or {})
        if sources:
            platforms = sorted({s.platform for s in sources})
            if "platforms" in sampling and sorted(set(sampling["platforms"])) != platforms:
                raise HTTPException(422, "采样平台必须与采集源平台一致")
            sampling["platforms"] = platforms
        else:
            platforms = sampling.get("platforms")
            if not isinstance(platforms, list) or not platforms or any(not isinstance(p, str) or not p.strip() for p in platforms):
                raise HTTPException(422, "人工批次请在sampling.platforms声明平台列表，复测将冻结该方案")
            sampling["platforms"] = list(dict.fromkeys(p.strip() for p in platforms))
        snapshot = {"questions": [current_question(db, q)["current_version"] for q in questions], "sources": [serialize(s) for s in sources], "brand": project.brand, "aliases": project.aliases, "website_url": project.website_url, "region": project.region, "competitors": [serialize(c) for c in rows(db, Competitor, project_id=identifier)], "facts": [serialize(f) for f in rows(db, Fact, project_id=identifier) if not f.archived], "sampling": sampling}
    question_ids = {q["question_id"] for q in snapshot["questions"]}
    controls = payload.control_question_ids if payload.control_question_ids is not None else list(baseline.control_question_ids) if payload.baseline_batch_id else []
    if not set(controls).issubset(question_ids):
        raise HTTPException(422, "对照问题必须属于冻结的问题集")
    for action in owned(db, Action, payload.action_ids, identifier):
        if not set(action.question_ids).issubset(question_ids):
            raise HTTPException(422, "关联行动的目标问题必须属于复测问题集")
        if set(action.question_ids) & set(controls):
            raise HTTPException(422, "被关联行动直接修改的目标问题不能同时声明为未变对照")
    obj = Batch(project_id=identifier, name=payload.name, mode=mode, snapshot=snapshot, baseline_batch_id=payload.baseline_batch_id, action_ids=payload.action_ids, content_version_ids=payload.content_version_ids, control_question_ids=controls)
    db.add(obj)
    db.commit()
    return serialize(obj)


@router.get("/batches/{identifier}")
def batch(identifier: int, db=Depends(get_db)):
    return {**serialize(require(db, Batch, identifier)), "answers": [serialize(item) for item in rows(db, Answer, batch_id=identifier)], "jobs": [serialize(item) for item in rows(db, Job, batch_id=identifier)]}


@router.post("/batches/{identifier}/import", status_code=201)
def import_answers(identifier: int, payload: ImportPayload, db=Depends(get_db)):
    batch = lock_batch(db, identifier)
    if batch.mode != "manual":
        raise HTTPException(422, "自动采集批次不可混入人工回答，请建立独立人工批次")
    allowed = {q["id"] for q in batch.snapshot["questions"]}
    imported = []
    for item in payload.answers:
        if item.question_version_id not in allowed:
            raise HTTPException(422, "回答的问题版本不在批次快照内")
        if item.platform not in batch.snapshot["sampling"]["platforms"]:
            raise HTTPException(422, "回答平台不在冻结采样方案内")
        data = item.model_dump()
        valid, reason = validity(item.text, item.task_status, item.validity, item.complete)
        data.update(validity=valid, invalid_reason=reason or item.invalid_reason, source_state="unknown" if item.sources is None else "empty" if not item.sources else "present", extracted_sources=extract_urls(item.text))
        observation_time(data, item.observed_at)
        answer = Answer(batch_id=identifier, **data)
        db.add(answer)
        imported.append(answer)
    batch.status = "imported"
    db.commit()
    return [serialize(item) for item in imported]


@router.post("/batches/{identifier}/collect")
def collect(identifier: int, db=Depends(get_db)):
    return collect_batch(identifier, db)


def collect_batch(identifier, db, before_trigger=None):
    batch = require(db, Batch, identifier)
    if batch.mode == "manual":
        raise HTTPException(422, "人工批次请使用导入回答")
    remote = Razormind()
    try:
        for question in batch.snapshot["questions"]:
            for source in batch.snapshot["sources"]:
                existing = db.scalar(select(Job).where(Job.batch_id == identifier, Job.question_version_id == question["id"], Job.source_config_id == source["id"]))
                if existing:
                    continue
                job = Job(batch_id=identifier, question_version_id=question["id"], source_config_id=source["id"], status="submitting")
                db.add(job)
                db.commit()  # Durable reservation BEFORE a non-idempotent external request.
                if before_trigger is not None:
                    before_trigger()
                try:
                    remote_id, raw = remote.trigger(source, question)
                    job.remote_task_id = remote_id
                    job.raw_result = {"trigger": raw}
                    job.status = "pending"
                except RemoteError as exc:
                    job.status = "submission_unknown"
                    job.error = str(redact(str(exc))) + "；不要重新触发，请在源服务核对后绑定任务ID"
                db.commit()
        batch.status = aggregate_job_status([job.status for job in rows(db, Job, batch_id=identifier)])
        db.commit()
        return {"jobs": [serialize(item) for item in rows(db, Job, batch_id=identifier)]}
    finally:
        remote.close()


@router.post("/jobs/{identifier}/attach")
def attach_job(identifier: int, payload: dict = Body(...), db=Depends(get_db)):
    job = require(db, Job, identifier)
    if job.status not in ("submitting", "submission_unknown") or job.remote_task_id:
        raise HTTPException(409, "只能为提交状态未知的任务绑定已核实的远端ID")
    task_id = payload.get("remote_task_id")
    if set(payload) != {"remote_task_id"} or not isinstance(task_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", task_id):
        raise HTTPException(422, "请提供已人工核实的remote_task_id")
    job.remote_task_id = task_id
    job.status = "pending"
    job.error = ""
    db.commit()
    return serialize(job)


@router.post("/batches/{identifier}/sync")
def sync(identifier: int, db=Depends(get_db)):
    batch = require(db, Batch, identifier)
    if batch.mode == "manual":
        raise HTTPException(422, "人工批次无需同步源任务")
    remote = Razormind()
    imported = 0
    try:
        for job in rows(db, Job, batch_id=identifier):
            if not job.remote_task_id or job.status == "ingested":
                continue
            try:
                task, raw = remote.task(job.remote_task_id)
                status = str(task.get("status", "unknown")).lower()
                job.raw_result = {**job.raw_result, "task": raw}
                job.status = status if status in ("pending", "running", "completed", "failed", "awaiting_confirm") else "unknown"
                job.error = ""
                db.commit()
                if status != "completed":
                    continue
                runs = remote.runs(job.remote_task_id)
                job.raw_result = {**job.raw_result, "runs": runs}
                records = remote.records(job.remote_task_id)
                job_imported = 0
                source = next(s for s in batch.snapshot["sources"] if s["id"] == job.source_config_id)
                for record in records:
                    if not isinstance(record, dict):
                        raise RemoteError("record必须为对象")
                    if record.get("task_id") is not None and str(record["task_id"]) != job.remote_task_id:
                        raise RemoteError("源返回了其他任务的record，拒绝污染样本")
                    data = record_answer(record, source)
                    if db.scalar(select(Answer.id).where(Answer.job_id == job.id, Answer.record_key == data["record_key"])):
                        continue
                    normalized_data = record.get("normalized_data")
                    supplied = normalized_data.get("observed_at") if isinstance(normalized_data, dict) else None
                    observation_time(data, supplied or record.get("observed_at"))
                    db.add(Answer(batch_id=identifier, question_version_id=job.question_version_id, job_id=job.id, extracted_sources=extract_urls(data["text"]), **data))
                    db.flush()
                    job_imported += 1
                if records:
                    job.status = "ingested"
                else:
                    job.error = "任务完成但暂无records；保留completed供下次显式同步，不制造空回答样本"
                db.commit()
                imported += job_imported
            except RemoteError as exc:
                db.rollback()
                job = require(db, Job, job.id)
                job.error = str(redact(str(exc)))
                db.commit()
        statuses = [job.status for job in rows(db, Job, batch_id=identifier)]
        batch.status = aggregate_job_status(statuses)
        db.commit()
        return {"jobs": [serialize(item) for item in rows(db, Job, batch_id=identifier)], "imported": imported, "status": batch.status, "failed_count": statuses.count("failed")}
    finally:
        remote.close()


@router.post("/batches/{identifier}/analyze")
def analyze(identifier: int, payload: AnalyzePayload = AnalyzePayload(), db=Depends(get_db)):
    return analyze_batch(db, lock_batch(db, identifier), payload.use_model, payload.use_current_aliases)


@router.get("/answers/{identifier}")
def answer(identifier: int, db=Depends(get_db)):
    answer = require(db, Answer, identifier)
    analyses = rows(db, Analysis, answer_id=identifier)
    return {**serialize(answer), "analyses": [{**serialize(a), "input_snapshot": serialize(require(db, AnalysisRun, a.run_id))["input_snapshot"]} for a in analyses]}


@router.get("/projects/{identifier}/overview")
def project_overview(identifier: int, batch_id: int | None = None, platform: str | None = None, region: str | None = None, intent: str | None = None, group_by: str | None = None, db=Depends(get_db)):
    require(db, Project, identifier)
    if group_by not in (None, "platform", "region", "intent"):
        raise HTTPException(422, "group_by只支持platform、region或intent")
    return overview(db, identifier, batch_id, platform, region, intent, group_by=group_by)


@router.post("/batches/{identifier}/diagnose")
def batch_diagnose(identifier: int, db=Depends(get_db)):
    return diagnose(db, require(db, Batch, identifier))


@router.get("/batches/{identifier}/compare")
def compare(identifier: int, db=Depends(get_db)):
    retest = require(db, Batch, identifier)
    if not retest.baseline_batch_id:
        raise HTTPException(422, "该批次未关联基线")
    baseline = require(db, Batch, retest.baseline_batch_id)
    same = retest.mode == baseline.mode and retest.snapshot == baseline.snapshot
    left = overview(db, retest.project_id, baseline.id)
    right = overview(db, retest.project_id, retest.id)
    warnings = ["结果是描述性比较，不承诺行动导致提升；平台上下文、时间和重复回答相关性均可能影响结果"]
    publication_evidence = []
    for version_id in retest.content_version_ids:
        jobs = rows(db, PublicationJob, content_version_id=version_id)
        verified = [j for j in jobs if j.status == "verified"]
        publication_evidence.append({"content_version_id": version_id, "verified": bool(verified), "source_kinds": sorted({j.source_kind for j in jobs}), "verification_job_ids": [j.id for j in verified]})
    if any(not p["verified"] for p in publication_evidence):
        warnings.append("关联历史内容只有人工发布声明或当前核验失效，不能声称版本真实上线；结果仅描述性比较")
    expected = {(q["id"], p) for q in baseline.snapshot["questions"] for p in baseline.snapshot["sampling"]["platforms"]}
    baseline_coverage = {(a.question_version_id, a.platform) for a in rows(db, Answer, batch_id=baseline.id)}
    retest_coverage = {(a.question_version_id, a.platform) for a in rows(db, Answer, batch_id=retest.id)}
    coverage_match = baseline_coverage == retest_coverage
    coverage_complete = baseline_coverage == expected and retest_coverage == expected
    analysis_basis_match = analysis_bases(db, baseline.id) == analysis_bases(db, retest.id)
    if not analysis_basis_match:
        warnings.append("双方最新分析的别名或规则版本基准不一致，请按同一分析输入重算后比较")
    if not coverage_match:
        warnings.append("基线与复测的实际问题版本×平台覆盖不同")
    if not coverage_complete:
        warnings.append("实际观测覆盖不完整，不能将缺失样本当作未提及")
    if not retest_coverage:
        warnings.append("复测没有回答样本，不可比较")
    if not same:
        warnings.append("冻结条件不一致，不可直接归因比较")
    if not retest.control_question_ids:
        warnings.append("未设置未变对照问题")
    groups = compare_groups(left["groups"], right["groups"])
    controls = compare_groups(overview(db, retest.project_id, baseline.id, question_ids=retest.control_question_ids)["groups"], overview(db, retest.project_id, retest.id, question_ids=retest.control_question_ids)["groups"])
    platform_groups = []
    for platform in baseline.snapshot["sampling"]["platforms"]:
        platform_groups.append({"platform": platform, "groups": compare_groups(overview(db, retest.project_id, baseline.id, platform=platform)["groups"], overview(db, retest.project_id, retest.id, platform=platform)["groups"])})
    return {"baseline_batch_id": baseline.id, "retest_batch_id": retest.id, "comparable": same and coverage_match and coverage_complete and analysis_basis_match and bool(retest_coverage), "conditions_match": same, "analysis_basis_match": analysis_basis_match, "coverage_match": coverage_match, "coverage_complete": coverage_complete, "coverage": {"expected": len(expected), "baseline": len(baseline_coverage), "retest": len(retest_coverage)}, "warnings": warnings, "groups": groups, "platform_groups": platform_groups, "control_question_ids": retest.control_question_ids, "control_groups": controls, "publication_evidence": publication_evidence, "causal_claim": False}


def aggregate_job_status(statuses):
    if statuses and all(s == "ingested" for s in statuses):
        return "completed"
    if statuses and all(s == "failed" for s in statuses):
        return "failed"
    if statuses and all(s in ("ingested", "failed") for s in statuses):
        return "partial_failed"
    if "awaiting_confirm" in statuses:
        return "awaiting_confirm"
    return "collecting"


def analysis_bases(db, batch_id):
    answers = rows(db, Answer, batch_id=batch_id)
    latest = latest_analyses(db, [answer.id for answer in answers])
    run_ids = {analysis.run_id for analysis in latest.values()}
    runs = {run.id: run.input_snapshot for run in db.scalars(select(AnalysisRun).where(AnalysisRun.id.in_(run_ids)))} if run_ids else {}
    bases = {}
    for answer in answers:
        key = (answer.question_version_id, answer.platform)
        analysis = latest.get(answer.id)
        snapshot = runs[analysis.run_id] if analysis else None
        basis = (tuple(sorted({alias.casefold() for alias in snapshot["aliases"]})), snapshot.get("analyzer_version")) if snapshot else None
        bases.setdefault(key, set()).add(basis)
    return bases
