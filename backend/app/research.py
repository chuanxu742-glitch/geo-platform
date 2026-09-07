import copy
from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import Field, StringConstraints, field_validator, model_validator
from sqlalchemy import select

from .analytics import compare_groups, group_metrics, latest_analyses
from .catalog import save, validate_patch
from .common import owned, require, rows, serialize
from .db import get_db
from .models import (Action, AnalysisRun, Answer, Batch, Content, ContentVersion,
                     Experiment, OperationRule, Page, PageSnapshot, Project,
                     PublicationJob, PublicationVerification,
                     Research, ResearchRevision, ResearchSourceSnapshot, now)
from .monitoring import compare
from .schemas import Payload
from .website import FetchError, _observations, fetch_url, validate_url

router = APIRouter()
Nonempty = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class Evidence(Payload):
    url: str
    quote: str = Field(min_length=1)
    answer_id: int | None = Field(default=None, gt=0)
    snapshot_id: int | None = Field(default=None, gt=0)
    research_source_id: int | None = Field(default=None, gt=0)
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, ge=0)

    @field_validator("url")
    @classmethod
    def http_url(cls, value):
        return validate_url(value)

    @field_validator("quote")
    @classmethod
    def real_quote(cls, value):
        if not value.strip():
            raise ValueError("证据引文不能为空")
        return value

    @model_validator(mode="after")
    def source_offsets(self):
        references = sum(value is not None for value in (self.answer_id, self.snapshot_id, self.research_source_id))
        if references > 1:
            raise ValueError("每条引文只能引用一个来源，以保持offset含义明确")
        if (self.start is None) != (self.end is None):
            raise ValueError("start和end必须同时提供或同时省略")
        if self.start is not None and (not references or self.end <= self.start):
            raise ValueError("offset必须引用已保存来源，且end必须晚于start")
        return self


class ResearchPayload(Payload):
    platform: Nonempty
    channel: Nonempty
    mode: Nonempty
    scenario: Nonempty
    source_type: Nonempty
    claim: Nonempty
    status: Literal["hypothesis", "supported", "inconclusive", "refuted"] = "hypothesis"
    conditions: Nonempty
    limitations: Nonempty
    evidence: list[Evidence] = Field(default_factory=list)
    reviewer: str = ""
    review_note: str = ""

    @model_validator(mode="after")
    def reviewed(self):
        if self.status != "hypothesis" and (not self.evidence or not self.reviewer.strip() or not self.review_note.strip()):
            raise ValueError("非假设研究必须有证据、审阅人及审阅说明")
        return self


class ResearchSourcePayload(Payload):
    url: str

    @field_validator("url")
    @classmethod
    def http_url(cls, value):
        return validate_url(value)


@router.get("/projects/{identifier}/research-sources")
def research_sources(identifier: int, db=Depends(get_db)):
    require(db, Project, identifier)
    return [serialize(item) for item in rows(db, ResearchSourceSnapshot, project_id=identifier)]


@router.post("/projects/{identifier}/research-sources/fetch", status_code=201)
def fetch_research_source(identifier: int, payload: ResearchSourcePayload, db=Depends(get_db)):
    require(db, Project, identifier)
    data = {"project_id": identifier, "url": payload.url, "final_url": "", "title": "", "visible_text": "", "content_hash": "", "status": "success", "error": "", "http_status": None, "fetch_evidence": {"source_kind": "http", "redirects": [], "headers": {}, "visibility_method": "static_html; excludes hidden attributes and inline styles; external CSS and JavaScript not evaluated"}}
    try:
        fetched = fetch_url(payload.url)
        data.update(final_url=fetched["final_url"], http_status=fetched["http_status"])
        data["fetch_evidence"].update({key: fetched[key] for key in ("headers", "redirects", "bytes", "response_sha256") if key in fetched})
        content_type = fetched["headers"].get("content-type", "").split(";", 1)[0].strip().lower()
        if not 200 <= fetched["http_status"] < 300:
            raise FetchError("http_status_error", final_url=fetched["final_url"], http_status=fetched["http_status"], headers=fetched["headers"], redirects=fetched["redirects"])
        if content_type and content_type not in ("text/html", "application/xhtml+xml"):
            raise FetchError("non_html_response", final_url=fetched["final_url"], http_status=fetched["http_status"], headers=fetched["headers"], redirects=fetched["redirects"])
        _, observations = _observations(fetched["html"])
        data.update({key: observations[key] for key in ("title", "visible_text", "content_hash")})
    except FetchError as exc:
        data.update(status="failure", error=exc.code, final_url=exc.final_url or data["final_url"], http_status=exc.http_status if exc.http_status is not None else data["http_status"])
        data["fetch_evidence"].update(redirects=exc.redirects, headers=exc.headers)
    return save(db, ResearchSourceSnapshot(**data))


def quote_offsets(item, text):
    start, end = item.get("start"), item.get("end")
    if start is None:
        start = text.find(item["quote"])
        end = start + len(item["quote"])
    if start < 0 or end > len(text) or text[start:end] != item["quote"]:
        raise HTTPException(422, "quote及start/end必须精确匹配已保存来源正文（Unicode字符，end不含）")
    item.update(start=start, end=end)


def evidence_snapshot(db, project_id, evidence):
    result = []
    for item in evidence:
        frozen = {"verification": "operator_provided"}
        if item.get("answer_id") is not None:
            answer = require(db, Answer, item["answer_id"])
            owned(db, Batch, [answer.batch_id], project_id)
            if answer.validity != "valid" or not answer.complete or item["quote"] not in answer.text:
                raise HTTPException(422, "引用Answer必须有效、完整且quote确切属于原始回答")
            quote_offsets(item, answer.text)
            frozen.update(verification="verified_answer", answer=serialize(answer), batch=serialize(require(db, Batch, answer.batch_id)))
        if item.get("snapshot_id") is not None:
            snapshot = require(db, PageSnapshot, item["snapshot_id"])
            owned(db, Page, [snapshot.page_id], project_id)
            if snapshot.source_kind != "http" or snapshot.status != "success" or snapshot.http_status is None or not 200 <= snapshot.http_status < 300:
                raise HTTPException(422, "研究快照必须为真实HTTP成功抓取，不能使用人工导入或失败快照")
            quote_offsets(item, snapshot.visible_text)
            if item["url"] not in {validate_url(snapshot.requested_url), validate_url(snapshot.final_url)}:
                raise HTTPException(422, "证据URL必须匹配所引用HTTP快照的请求或最终URL")
            frozen.update(verification="verified_http_snapshot", snapshot=serialize(snapshot), page=serialize(require(db, Page, snapshot.page_id)))
        if item.get("research_source_id") is not None:
            source = owned(db, ResearchSourceSnapshot, [item["research_source_id"]], project_id)[0]
            if source.status != "success" or source.http_status is None or not 200 <= source.http_status < 300:
                raise HTTPException(422, "研究来源必须是HTTP成功抓取")
            if item["url"] not in {validate_url(source.url), validate_url(source.final_url)}:
                raise HTTPException(422, "证据URL必须匹配研究来源请求或最终URL")
            quote_offsets(item, source.visible_text)
            frozen.update(verification="verified_research_source", research_source=serialize(source))
        frozen["evidence"] = copy.deepcopy(item)
        result.append(frozen)
    return result


def validated_research_evidence(db, project_id, data):
    frozen = evidence_snapshot(db, project_id, data["evidence"])
    if data["status"] in ("supported", "refuted") and not any(item["verification"] != "operator_provided" for item in frozen):
        raise HTTPException(422, "supported/refuted需要有效Answer或HTTP成功快照的精确引文；仅人工填写URL不能作为核验证据")
    return frozen


def research_view(db, obj):
    return {**serialize(obj), "revisions": [serialize(item) for item in rows(db, ResearchRevision, research_id=obj.id)]}


@router.get("/projects/{identifier}/research")
def research_list(identifier: int, db=Depends(get_db)):
    require(db, Project, identifier)
    return [serialize(item) for item in rows(db, Research, project_id=identifier)]


@router.post("/projects/{identifier}/research", status_code=201)
def create_research(identifier: int, payload: ResearchPayload, db=Depends(get_db)):
    require(db, Project, identifier)
    data = payload.model_dump()
    frozen = validated_research_evidence(db, identifier, data)
    obj = Research(project_id=identifier, **data)
    db.add(obj)
    db.flush()
    db.add(ResearchRevision(research_id=obj.id, snapshot={"before": None, "after": serialize(obj), "evidence_snapshot": frozen}))
    return save(db, obj)


@router.get("/research/{identifier}")
def research_detail(identifier: int, db=Depends(get_db)):
    return research_view(db, require(db, Research, identifier))


@router.patch("/research/{identifier}")
def patch_research(identifier: int, payload: dict = Body(...), db=Depends(get_db)):
    obj = db.scalar(select(Research).where(Research.id == identifier).with_for_update())
    if obj is None:
        raise HTTPException(404, "记录不存在")
    data = validate_patch(obj, payload, ResearchPayload)
    frozen = validated_research_evidence(db, obj.project_id, data)
    before = copy.deepcopy(serialize(obj))
    previous = rows(db, ResearchRevision, research_id=obj.id)
    before_evidence = copy.deepcopy(previous[-1].snapshot.get("evidence_snapshot", [])) if previous else []
    for key, value in data.items():
        setattr(obj, key, value)
    obj.updated_at = now()
    db.flush()
    db.add(ResearchRevision(research_id=obj.id, snapshot={"before": before, "after": serialize(obj), "before_evidence_snapshot": before_evidence, "evidence_snapshot": frozen}))
    return save(db, obj)


def aware_time(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("时间必须包含时区")
    return parsed.astimezone(timezone.utc)


class ExperimentPayload(Payload):
    title: Nonempty
    hypothesis: Nonempty
    primary_change: Nonempty
    page_id: int = Field(gt=0)
    content_version_id: int = Field(gt=0)
    baseline_batch_id: int = Field(gt=0)
    retest_batch_id: int = Field(gt=0)
    window_start: str
    window_end: str
    metric: Literal["mention_rate", "recommendation_rate", "factual_error_rate"]
    direction: Literal["increase", "decrease"]
    conditions: Nonempty
    limitations: Nonempty

    @field_validator("window_start", "window_end")
    @classmethod
    def timestamp(cls, value):
        return aware_time(value).isoformat()

    @model_validator(mode="after")
    def ordered(self):
        if aware_time(self.window_start) >= aware_time(self.window_end):
            raise ValueError("观察窗口结束时间必须晚于开始时间")
        if self.baseline_batch_id == self.retest_batch_id:
            raise ValueError("基线与复测不能是同一批次")
        return self


class ConclusionPayload(Payload):
    status: Literal["supported", "inconclusive", "refuted"]
    reviewer: Nonempty
    note: Nonempty


def publication_timeline(jobs):
    for job in jobs:
        if job["status"] != "verified":
            continue
        source_kind = job["source_kind"]
        if source_kind == "wordpress":
            start_value, start_basis = job["created_at"], "publication_job.created_at"
        elif source_kind == "external_record":
            start_value, start_basis = job["execution_evidence"].get("operator_reported_at"), "operator_reported_at (人工声明，非系统外发时间)"
        else:
            continue
        try:
            start = aware_time(start_value)
            verified = [(aware_time(item["verified_at"]), item) for item in job["verifications"] if item["status"] == "verified" and item["snapshot"]["source_kind"] == "http" and item["snapshot"]["status"] == "success" and item["snapshot"]["http_status"] is not None and 200 <= item["snapshot"]["http_status"] < 300]
        except (ValueError, TypeError, AttributeError):
            continue
        if not verified:
            continue
        end, verification = min(verified, key=lambda item: item[0])
        if start > end:
            continue
        return {"status": "known", "publication_job_id": job["id"], "source_kind": source_kind, "start": start.isoformat(), "end": end.isoformat(), "start_basis": start_basis, "end_basis": "首次成功HTTP正文核验时间（保守可见上界）", "verification_id": verification["id"], "limitations": "外部发布开始时间由操作员报告；首次核验仅证明此时已可见，不证明更早已上线" if source_kind == "external_record" else "发布开始至首次成功核验是保守干预窗口，不是平台索引生效时间"}
    return {"status": "unknown", "start": None, "end": None, "reason": "缺少有效发布开始时间和首次成功HTTP核验上界，或发布时间证据倒置"}


def freeze_comparison(db, baseline, retest, payload):
    comparison = copy.deepcopy(compare(retest.id, db))
    controls = set(retest.control_question_ids)
    questions = {q["id"]: q for q in baseline.snapshot["questions"]}
    start, end = aware_time(payload.window_start), aware_time(payload.window_end)
    frozen, run_ids, treatment = {}, {}, {}
    for label, batch in (("baseline", baseline), ("retest", retest)):
        answers = rows(db, Answer, batch_id=batch.id)
        analyses = latest_analyses(db, [a.id for a in answers])
        for answer in answers:
            try:
                observed = aware_time(answer.observed_at) if answer.observed_at else None
            except (ValueError, TypeError):
                observed = None
            if observed is None or not start <= observed <= end:
                raise HTTPException(422, f"Answer {answer.id} 的observed_at缺失、无时区或不在观察窗口内")
        run_ids[label] = sorted({a.run_id for a in analyses.values()})
        runs = [require(db, AnalysisRun, identifier) for identifier in run_ids[label]]
        if any(run.batch_id != batch.id for run in runs):
            raise HTTPException(422, "分析运行与回答批次不一致")
        frozen[label] = {"batch": serialize(batch), "answers": [serialize(a) for a in answers], "analyses": [serialize(a) for a in analyses.values()], "analysis_runs": [serialize(run) for run in runs]}
        treatment[label] = [group_metrics([(a, analyses.get(a.id), batch.snapshot) for a in answers if a.question_version_id in questions and questions[a.question_version_id]["question_id"] not in controls and questions[a.question_version_id]["branded"] == branded], branded) for branded in (False, True)]
    comparison["treatment_groups"] = compare_groups(treatment["baseline"], treatment["retest"])
    comparison["evidence_snapshot"] = frozen
    comparison["page_snapshot"] = serialize(require(db, Page, payload.page_id))
    comparison["content_version_snapshot"] = serialize(require(db, ContentVersion, payload.content_version_id))
    jobs = rows(db, PublicationJob, project_id=baseline.project_id, page_id=payload.page_id, content_version_id=payload.content_version_id)
    comparison["publication_snapshots"] = [{**serialize(job), "verifications": [{**serialize(verification), "snapshot": serialize(require(db, PageSnapshot, verification.snapshot_id))} for verification in rows(db, PublicationVerification, publication_job_id=job.id)]} for job in jobs]
    comparison["publication_timeline"] = publication_timeline(comparison["publication_snapshots"])
    for publication in comparison.get("publication_evidence", []):
        if publication["content_version_id"] == payload.content_version_id:
            publication["verified"] = any(job.status == "verified" for job in jobs)
            publication["verification_job_ids"] = [job.id for job in jobs if job.status == "verified"]
    return comparison, run_ids


def conclusion_reasons(obj, status):
    frozen = obj.comparison
    reasons = []
    for field in ("comparable", "conditions_match", "analysis_basis_match", "coverage_complete", "coverage_match"):
        if frozen.get(field) is not True:
            reasons.append(f"冻结比较不满足{field}")
    if not obj.conditions.strip() or not obj.limitations.strip():
        reasons.append("必须明确记录适用条件和局限")
    publication = next((item for item in frozen.get("publication_evidence", []) if item["content_version_id"] == obj.content_version_id), None)
    if not publication or publication.get("verified") is not True:
        reasons.append("冻结发布证据未核验所引用内容版本；历史人工发布声明只能作不确定结论")
    timeline = frozen.get("publication_timeline", {})
    if timeline.get("status") != "known":
        reasons.append("缺少可核验干预时间窗口；未知发布时间只能作不确定结论")
    else:
        try:
            intervention_start, intervention_end = aware_time(timeline["start"]), aware_time(timeline["end"])
            baseline_times = [aware_time(item["observed_at"]) for item in frozen["evidence_snapshot"]["baseline"]["answers"]]
            retest_times = [aware_time(item["observed_at"]) for item in frozen["evidence_snapshot"]["retest"]["answers"]]
            if intervention_start > intervention_end:
                reasons.append("干预时间证据倒置")
            if max(baseline_times) > intervention_start:
                reasons.append("基线回答必须全部观察于干预开始之前或当时，不能用发布后样本充当基线")
            if min(retest_times) < intervention_end:
                reasons.append("复测回答必须全部观察于首次成功核验之后或当时")
            if max(baseline_times) >= min(retest_times):
                reasons.append("基线与复测观察时间重叠或倒置")
        except (KeyError, ValueError, TypeError, AttributeError):
            reasons.append("冻结回答或干预时间缺失、无时区或无有效样本")
    metric_fields = {"mention_rate": ("brand_mentioned", None, "mention"), "recommendation_rate": ("recommendation", "unknown", "recommendation"), "factual_error_rate": ("factual_status", "unknown", "factual_error")}
    analysis_field, unknown, interval_name = metric_fields[obj.metric]
    evidence = frozen.get("evidence_snapshot", {})
    controls = set(obj.control_question_ids)
    if not controls:
        reasons.append("缺少真实未变对照问题")
    for label in ("baseline", "retest"):
        source = evidence.get(label, {})
        batch = source.get("batch", {})
        snapshot = batch.get("snapshot", {})
        questions = snapshot.get("questions", [])
        expected = {(q["id"], p) for q in questions for p in snapshot.get("sampling", {}).get("platforms", [])}
        analyses = {a["answer_id"]: a for a in source.get("analyses", [])}
        valid_coverage = {(a["question_version_id"], a["platform"]) for a in source.get("answers", []) if a["validity"] == "valid" and a["complete"] and a["id"] in analyses and analyses[a["id"]].get(analysis_field) not in (None, unknown)}
        if not expected or valid_coverage != expected:
            reasons.append(f"{label}有效且已分析的样本覆盖不完整")
        if not controls.issubset({q["question_id"] for q in questions}):
            reasons.append(f"{label}缺少冻结对照问题")
    control_groups = [g for g in frozen.get("control_groups", []) if g["baseline"]["sample_count"] or g["retest"]["sample_count"]]
    if not control_groups or any(g["uncertainty"].get(f"{interval_name}_difference_interval") is None for g in control_groups):
        reasons.append("对照组双方缺少目标指标已知有效样本")
    groups = [g for g in frozen.get("treatment_groups", []) if g["baseline"]["sample_count"] or g["retest"]["sample_count"]]
    if not groups:
        reasons.append("缺少对照之外的实验目标样本")
    positive = (obj.direction == "increase") == (status == "supported")
    for group in groups:
        interval = group["uncertainty"].get(f"{interval_name}_difference_interval")
        effect = group.get(f"{obj.metric}_delta")
        if effect is None or (effect <= 0 if positive else effect >= 0):
            reasons.append("目标指标实际变化方向不支持所选结论")
        if not interval or (interval[0] <= 0 if positive else interval[1] >= 0):
            reasons.append("目标组保守差值范围跨越0或不支持所选方向；不显著不等于否定")
    return list(dict.fromkeys(reasons))


def experiment_view(obj):
    return {**serialize(obj), "conclusion_gate": {status: conclusion_reasons(obj, status) for status in ("supported", "refuted")}}


@router.get("/projects/{identifier}/experiments")
def experiments(identifier: int, db=Depends(get_db)):
    require(db, Project, identifier)
    return [experiment_view(item) for item in rows(db, Experiment, project_id=identifier)]


@router.post("/projects/{identifier}/experiments", status_code=201)
def create_experiment(identifier: int, payload: ExperimentPayload, db=Depends(get_db)):
    require(db, Project, identifier)
    page = owned(db, Page, [payload.page_id], identifier)[0]
    version = require(db, ContentVersion, payload.content_version_id)
    content = owned(db, Content, [version.content_id], identifier)[0]
    if validate_url(content.target_url) != validate_url(page.url):
        raise HTTPException(422, "内容版本目标URL不匹配实验页面")
    if version.source_snapshot_id is not None and require(db, PageSnapshot, version.source_snapshot_id).page_id != page.id:
        raise HTTPException(422, "内容版本来源快照不属于实验页面")
    batches = list(db.scalars(select(Batch).where(Batch.id.in_([payload.baseline_batch_id, payload.retest_batch_id])).order_by(Batch.id).with_for_update()))
    by_id = {b.id: b for b in batches}
    baseline, retest = [by_id.get(i) for i in (payload.baseline_batch_id, payload.retest_batch_id)]
    if baseline is None or retest is None:
        raise HTTPException(404, "批次不存在")
    if any(b.project_id != identifier for b in batches):
        raise HTTPException(422, "批次不属于当前项目")
    if retest.baseline_batch_id != baseline.id or version.id not in retest.content_version_ids:
        raise HTTPException(422, "复测必须严格关联指定基线和内容版本")
    controls = set(retest.control_question_ids)
    question_ids = {q["question_id"] for q in baseline.snapshot["questions"]}
    if not controls.issubset(question_ids) or controls != set(baseline.control_question_ids):
        raise HTTPException(422, "对照问题必须来自基线冻结对照集且保持一致")
    targets = set(version.generation.get("question_ids", []))
    target_versions = set(version.generation.get("question_version_ids", []))
    targets.update(q["question_id"] for q in baseline.snapshot["questions"] if q["id"] in target_versions)
    for action in owned(db, Action, list(set(retest.action_ids + ([content.action_id] if content.action_id else []))), identifier):
        targets.update(action.question_ids)
    if targets & controls:
        raise HTTPException(422, "被内容或行动直接修改的目标问题不能作为未变对照")
    comparison, run_ids = freeze_comparison(db, baseline, retest, payload)
    obj = Experiment(project_id=identifier, **payload.model_dump(), comparison=comparison, analysis_run_ids=run_ids, control_question_ids=list(retest.control_question_ids))
    save(db, obj)
    return experiment_view(obj)


@router.get("/experiments/{identifier}")
def experiment_detail(identifier: int, db=Depends(get_db)):
    return experiment_view(require(db, Experiment, identifier))


@router.post("/experiments/{identifier}/conclude")
def conclude(identifier: int, payload: ConclusionPayload, db=Depends(get_db)):
    obj = db.scalar(select(Experiment).where(Experiment.id == identifier).with_for_update())
    if obj is None:
        raise HTTPException(404, "记录不存在")
    if obj.status != "hypothesis":
        raise HTTPException(409, "实验已经审阅；历史结论不可覆盖，请建立新实验")
    if payload.status != "inconclusive":
        reasons = conclusion_reasons(obj, payload.status)
        if reasons:
            raise HTTPException(422, "；".join(reasons))
    elif not obj.limitations.strip():
        raise HTTPException(422, "不确定结论必须明确记录局限")
    obj.status, obj.reviewer, obj.review_note, obj.reviewed_at = payload.status, payload.reviewer, payload.note, now().isoformat()
    save(db, obj)
    return experiment_view(obj)


class RulePayload(Payload):
    title: Nonempty
    instruction: Nonempty
    conditions: Nonempty
    limitations: Nonempty
    experiment_id: int | None = Field(default=None, gt=0)
    research_id: int | None = Field(default=None, gt=0)
    reviewer: Nonempty
    review_note: Nonempty

    @model_validator(mode="after")
    def has_source(self):
        if self.experiment_id is None and self.research_id is None:
            raise ValueError("规则至少需要一个已有supported来源")
        return self


@router.get("/projects/{identifier}/operations/rules")
def rules(identifier: int, db=Depends(get_db)):
    require(db, Project, identifier)
    return [serialize(item) for item in rows(db, OperationRule, project_id=identifier)]


@router.post("/projects/{identifier}/operations/rules", status_code=201)
def create_rule(identifier: int, payload: RulePayload, db=Depends(get_db)):
    require(db, Project, identifier)
    source_snapshot = {}
    for key, model in (("experiment", Experiment), ("research", Research)):
        source_id = getattr(payload, f"{key}_id")
        if source_id is None:
            continue
        obj = owned(db, model, [source_id], identifier)[0]
        if obj.status != "supported" or not obj.reviewer.strip() or not obj.review_note.strip():
            raise HTTPException(422, "规则引用来源必须为已人工审阅的supported记录")
        if key == "experiment":
            if obj.reviewed_at is None or conclusion_reasons(obj, "supported"):
                raise HTTPException(422, "实验来源未通过冻结证据门禁")
            source_snapshot[key] = experiment_view(obj)
        else:
            view = research_view(db, obj)
            revisions = view["revisions"]
            frozen = revisions[-1]["snapshot"] if revisions else {}
            after = frozen.get("after", {})
            current = serialize(obj)
            matches = all(after.get(field) == current[field] for field in (*ResearchPayload.model_fields, "id", "project_id"))
            if not matches or not any(e["verification"] != "operator_provided" for e in frozen.get("evidence_snapshot", [])):
                raise HTTPException(422, "研究来源缺少核验证据及完整不可变修订记录")
            source_snapshot[key] = view
    return save(db, OperationRule(project_id=identifier, **payload.model_dump(), source_snapshot=copy.deepcopy(source_snapshot)))
