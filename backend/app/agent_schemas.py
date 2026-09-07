from typing import Annotated, Literal
from pydantic import Field, StringConstraints, model_validator
from .schemas import Payload

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20000)]


class AgentPolicy(Payload):
    max_pages: int = Field(default=2, ge=1, le=3)
    max_model_requests: int = Field(default=8, ge=3, le=12)
    review_interval_days: int = Field(default=30, ge=1, le=365)
    sample: bool = False
    continuous_maintenance: bool = False


class StartRun(Payload):
    goal: Text
    policy: AgentPolicy = Field(default_factory=AgentPolicy)


class Binding(Payload):
    page_id: int = Field(gt=0)
    content_version_id: int = Field(gt=0)
    target_url: str
    body_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class ReviewRun(Payload):
    proposal_id: int = Field(gt=0)
    decision: Literal['approve', 'approve_only', 'approve_and_publish', 'request_changes', 'reject']
    feedback: Text
    reviewer: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    allow_publish: bool = False
    bindings: list[Binding] = Field(default_factory=list, max_length=3)

    @model_validator(mode='after')
    def consent(self):
        publishing = self.decision == 'approve_and_publish'
        if publishing != self.allow_publish or (not publishing and self.bindings) or (publishing and not self.bindings):
            raise ValueError('发布授权必须明确绑定准确版本，其他决定不可授权发布')
        return self


class SourceQuote(Payload):
    snapshot_id: int = Field(gt=0)
    url: str
    quote: Text
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class FactCandidate(Payload):
    claim: Text
    source_url: str
    snapshot_id: int = Field(gt=0)
    quote: Text
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class KnowledgeReference(Payload):
    kind: Literal['research', 'rule']
    id: int = Field(gt=0)
    application: Literal['conditional_hypothesis']
    conditions_to_verify: Text


class TargetPlan(Payload):
    page_id: int = Field(gt=0)
    snapshot_id: int = Field(gt=0)
    target_url: str
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    question: Text
    content_gap: Text
    hypothesis: Text
    priority: Literal['low', 'medium', 'high']
    acceptance_method: Text
    branded: bool
    intent: Text
    decision_stage: Literal['awareness', 'consideration', 'decision', 'retention']
    business_value: int = Field(ge=1, le=5)
    business_fit: int = Field(ge=1, le=5)
    judgment_basis: Text
    instructions: Text
    expected_change: Text
    fact_ids: list[int] = Field(max_length=30)
    fact_candidates: list[FactCandidate] = Field(max_length=8)
    evidence: list[SourceQuote] = Field(min_length=1, max_length=8)
    answer_evidence: list['AnswerQuote'] = Field(default_factory=list, max_length=8)
    knowledge_references: list[KnowledgeReference] = Field(default_factory=list, max_length=8)


class SamplingPlan(Payload):
    requested: bool
    reason: Text


class Plan(Payload):
    summary: Text
    targets: list[TargetPlan] = Field(min_length=1, max_length=3)
    sampling: SamplingPlan
    limitations: list[Text] = Field(min_length=1, max_length=10)


class Discovery(Payload):
    urls: list[str] = Field(min_length=1, max_length=3)
    summary: Text


class AnswerQuote(Payload):
    answer_id: int = Field(gt=0)
    analysis_id: int | None
    analysis_version: int | None
    question_version_id: int = Field(gt=0)
    batch_id: int = Field(gt=0)
    platform: str
    observed_at: str
    quote: str = Field(min_length=1, max_length=20000)
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class StrategyJudgment(Payload):
    problem_type: Literal['brand_absent', 'fact_mismatch', 'information_gap', 'recommendation', 'unknown']
    observation: Text
    cause_hypothesis: Text
    fact_ids: list[int] = Field(max_length=30)
    answer_evidence: list[AnswerQuote] = Field(max_length=8)
    website_evidence: list[SourceQuote] = Field(max_length=8)


class StrategyTarget(Payload):
    page_id: int = Field(gt=0)
    target_url: str
    question_ids: list[int] = Field(min_length=1, max_length=3)
    fact_ids: list[int] = Field(max_length=30)
    judgments: list[StrategyJudgment] = Field(min_length=1, max_length=8)
    instructions: Text
    expected_change: Text
    acceptance_method: Text
    knowledge_references: list[KnowledgeReference] = Field(default_factory=list, max_length=8)


class Strategy(Payload):
    status: Literal['ready', 'inconclusive', 'scope_change_required']
    mode: Literal['answer_evidence', 'website_hypothesis']
    summary: Text
    targets: list[StrategyTarget] = Field(max_length=3)
    limitations: list[Text] = Field(min_length=1, max_length=10)


Plan.model_rebuild()
