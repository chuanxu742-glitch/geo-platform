from typing import Literal
from pydantic import Field, field_validator, model_validator
from .schemas import Payload, FactCreate


class OpportunityEvidence(Payload):
    url: str
    quote: str = Field(min_length=1, max_length=20000)
    answer_id: int | None = None

    @field_validator("url")
    @classmethod
    def url_valid(cls, value):
        return FactCreate.url(value)


class OpportunityCreate(Payload):
    title: str = Field(min_length=1, max_length=2000)
    question_ids: list[int] = Field(min_length=1, max_length=100)
    page_ids: list[int] = Field(default_factory=list, max_length=100)
    decision_stage: Literal["awareness", "consideration", "decision", "retention"] = "consideration"
    business_value: int = Field(default=3, ge=1, le=5)
    business_fit: int = Field(default=3, ge=1, le=5)
    content_gap: str = Field(min_length=1, max_length=20000)
    priority: Literal["low", "medium", "high"] = "medium"
    basis: Literal["evidence", "hypothesis"] = "hypothesis"
    evidence: list[OpportunityEvidence] = Field(default_factory=list, max_length=100)
    hypothesis: str = Field(default="", max_length=20000)
    status: Literal["open", "planned", "closed"] = "open"

    @model_validator(mode="after")
    def basis_present(self):
        if self.basis == "evidence" and not self.evidence:
            raise ValueError("证据型机会需要证据")
        if self.basis == "hypothesis" and not self.hypothesis.strip():
            raise ValueError("假设型机会必须说明待验证假设")
        return self


class PageCreate(Payload):
    url: str
    title: str = Field(default="", max_length=2000)
    page_type: str = Field(default="service", min_length=1, max_length=100)
    owner: str = Field(default="", max_length=200)
    next_review_at: str | None = None
    review_interval_days: int = Field(default=30, ge=1, le=3650)

    @field_validator("url")
    @classmethod
    def url_valid(cls, value):
        return FactCreate.url(value)

    @field_validator("next_review_at")
    @classmethod
    def time_valid(cls, value):
        return FactCreate.timestamp(value)


class PageDraft(Payload):
    snapshot_id: int
    content_id: int
    fact_ids: list[int] = Field(default_factory=list, max_length=100)
    question_ids: list[int] = Field(min_length=1, max_length=100)
    mode: Literal["manual", "model"] = "manual"
    instructions: str = Field(default="", max_length=20000)
    after_text: str = Field(default="", max_length=2000000)

    @model_validator(mode="after")
    def draft_requirements(self):
        if self.mode == "manual" and not self.after_text.strip():
            raise ValueError("人工改稿需要正文")
        if self.mode == "model" and (not self.fact_ids or not self.instructions.strip()):
            raise ValueError("模型改稿必须选有效事实并说明要求")
        return self


class ReviewPayload(Payload):
    status: Literal["approved", "rejected"]
    reviewer: str = Field(min_length=1, max_length=200)
    note: str = Field(min_length=1, max_length=20000)

    @field_validator("reviewer", "note")
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError("审核人和意见不可为空")
        return value


class PublisherCreate(Payload):
    name: str = Field(min_length=1, max_length=200)
    site_url: str
    resource: Literal["pages", "posts"] = "pages"
    post_id: int = Field(gt=0)
    enabled: bool = True

    @field_validator("site_url")
    @classmethod
    def site_valid(cls, value):
        return FactCreate.url(value)


class PublishJobCreate(Payload):
    publisher_id: int
    page_id: int


class ExternalPublication(Payload):
    page_id: int
    note: str = Field(min_length=1, max_length=20000)
    published_at: str | None = None

    @field_validator("published_at")
    @classmethod
    def time_valid(cls, value):
        return FactCreate.timestamp(value)


