from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from urllib.parse import urlparse
import re


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProjectCreate(Payload):
    name: str = Field(min_length=1, max_length=200)
    brand: str = Field(min_length=1, max_length=200)
    aliases: list[str] = Field(default_factory=list, max_length=100)
    website_url: str = ""
    region: str = Field(default="", max_length=200)

    @field_validator("website_url")
    @classmethod
    def website(cls, value):
        if value and urlparse(value).scheme not in ("http", "https"):
            raise ValueError("官网必须为HTTP(S)地址")
        return value

    @field_validator("aliases")
    @classmethod
    def clean_aliases(cls, value):
        return list(dict.fromkeys(x.strip() for x in value if x.strip()))


class CompetitorCreate(Payload):
    name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = Field(default_factory=list, max_length=100)


class FactCreate(Payload):
    claim: str = Field(min_length=1, max_length=20000)
    source_url: str
    valid_from: str | None = None
    valid_to: str | None = None

    @field_validator("source_url")
    @classmethod
    def url(cls, value):
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("事实出处必须为不含凭据的HTTP(S) URL")
        return value

    @field_validator("valid_from", "valid_to")
    @classmethod
    def timestamp(cls, value):
        if value is None:
            return value
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            raise ValueError("时间必须包含时区")
        return dt.isoformat()

    @model_validator(mode="after")
    def ordered(self):
        if self.valid_from and self.valid_to and datetime.fromisoformat(self.valid_to) <= datetime.fromisoformat(self.valid_from):
            raise ValueError("事实有效结束时间必须晚于开始时间")
        return self


class QuestionCreate(Payload):
    text: str = Field(min_length=1, max_length=20000)
    branded: bool
    intent: str = Field(default="", max_length=200)
    region: str = Field(default="", max_length=200)


SECRET_KEY = re.compile(r"token|secret|password|cookie|authorization|api[_-]?key", re.I)


def reject_secrets(value):
    if isinstance(value, dict):
        if any(SECRET_KEY.search(str(key)) for key in value):
            raise ValueError("配置禁止保存凭据，请使用服务器环境变量")
        for item in value.values():
            reject_secrets(item)
    elif isinstance(value, list):
        for item in value:
            reject_secrets(item)


class SourceCreate(Payload):
    name: str = Field(min_length=1, max_length=200)
    platform: str = Field(min_length=1, max_length=100)
    source_id: str = Field(min_length=1, max_length=200)
    parameter_mapping: dict[str, str] = Field(default_factory=lambda: {"question": "question"})
    parameters: dict = Field(default_factory=dict)
    result_mapping: dict[str, str] = Field(default_factory=lambda: {"text": "normalized_data.response", "sources": "normalized_data.sources", "status": "normalized_data.status"})
    mode: str = Field(default="browser", min_length=1, max_length=100)
    answer_complete: bool = False

    @model_validator(mode="after")
    def mapping(self):
        reject_secrets(self.model_dump())
        if set(self.parameter_mapping) != {"question"} or not self.parameter_mapping["question"].strip():
            raise ValueError("parameter_mapping必须提供question对应的源参数名")
        if not self.result_mapping.get("text"):
            raise ValueError("result_mapping必须指定text路径")
        if set(self.result_mapping) - {"text", "sources", "status", "role", "complete"}:
            raise ValueError("不支持的结果映射字段")
        return self


class BatchCreate(Payload):
    name: str = Field(min_length=1, max_length=200)
    question_ids: list[int] | None = None
    source_ids: list[int] | None = None
    mode: str | None = None
    sampling: dict | None = None
    baseline_batch_id: int | None = None
    action_ids: list[int] = Field(default_factory=list)
    content_version_ids: list[int] = Field(default_factory=list)
    control_question_ids: list[int] | None = None

    @field_validator("sampling")
    @classmethod
    def safe_sampling(cls, value):
        reject_secrets(value)
        return value


class Citation(Payload):
    url: str
    title: str = ""
    type: Literal["reported", "verified", "text_url_extraction"] = "reported"

    @field_validator("url")
    @classmethod
    def validate_url(cls, value):
        return FactCreate.url(value)


class AnswerImport(Payload):
    question_version_id: int
    platform: str = Field(min_length=1, max_length=100)
    text: str = Field(max_length=2000000)
    task_status: Literal["pending", "running", "completed", "failed", "awaiting_confirm", "unknown"] = "completed"
    validity: Literal["valid", "invalid", "unknown"] = "unknown"
    invalid_reason: str = ""
    complete: bool = False
    sources: list[Citation] | None = None
    raw: dict = Field(default_factory=dict)
    observed_at: str | None = None

    @field_validator("observed_at")
    @classmethod
    def observation_time(cls, value):
        return FactCreate.timestamp(value)


class ImportPayload(Payload):
    answers: list[AnswerImport] = Field(min_length=1, max_length=1000)


class AnalyzePayload(Payload):
    use_model: bool = False
    use_current_aliases: bool = False


class DiagnosisReview(Payload):
    review_status: Literal["pending", "accepted", "rejected"]


class ActionCreate(Payload):
    title: str = Field(min_length=1, max_length=20000)
    question_ids: list[int] = Field(default_factory=list)
    target_page: str = ""
    fact_ids: list[int] = Field(default_factory=list)
    diagnosis_ids: list[int] = Field(default_factory=list)
    owner: str = Field(default="", max_length=200)
    status: Literal["todo", "in_progress", "blocked", "awaiting_review", "done", "cancelled"] = "todo"
    acceptance_method: str = Field(min_length=1, max_length=20000)
    due_at: str | None = None
    blocked_reason: str = ""
    opportunity_id: int | None = None
    page_id: int | None = None
    finding_id: int | None = None

    @field_validator("due_at")
    @classmethod
    def due_time(cls, value):
        return FactCreate.timestamp(value)

    @model_validator(mode="after")
    def operational_requirements(self):
        if any(x is not None for x in (self.opportunity_id, self.page_id, self.finding_id)):
            if not self.owner.strip() or not self.due_at or not self.acceptance_method.strip():
                raise ValueError("运营任务必须有负责人、到期时间和验收条件")
        if self.status == "blocked" and not self.blocked_reason.strip():
            raise ValueError("阻塞任务必须说明原因")
        return self


class ContentCreate(Payload):
    title: str = Field(min_length=1, max_length=200)
    target_url: str = ""
    action_id: int | None = None


class VersionCreate(Payload):
    before_text: str = Field(default="", max_length=2000000)
    after_text: str = Field(min_length=1, max_length=2000000)
    fact_ids: list[int] = Field(default_factory=list)


class GeneratePayload(Payload):
    instructions: str = Field(min_length=1, max_length=20000)
    before_text: str = Field(default="", max_length=2000000)
    fact_ids: list[int] = Field(min_length=1)




class Evidence(Payload):
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: str = Field(min_length=1)


class Finding(Payload):
    fact_id: int
    status: Literal["consistent", "inconsistent"]
    evidence: Evidence
    explanation: str


class CompetitorRecommendation(Payload):
    name: str
    recommendation: Literal["recommended", "not_recommended", "neutral", "unknown"]
    evidence: list[Evidence]


class SemanticResult(Payload):
    recommendation: Literal["recommended", "not_recommended", "neutral", "unknown"]
    recommendation_evidence: list[Evidence]
    recommendation_list_evidence: list[Evidence]
    factual_findings: list[Finding]
    competitor_recommendations: list[CompetitorRecommendation]


class GeneratedClaim(Evidence):
    fact_id: int


class GeneratedContent(Payload):
    text: str = Field(min_length=1)
    used_fact_ids: list[int] = Field(min_length=1)
    factual_claims: list[GeneratedClaim]
