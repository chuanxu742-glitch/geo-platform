from datetime import datetime, timezone
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    brand: Mapped[str] = mapped_column(String(200))
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    website_url: Mapped[str] = mapped_column(Text, default="")
    region: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Competitor(Base):
    __tablename__ = "competitors"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(200))
    aliases: Mapped[list] = mapped_column(JSON, default=list)


class Fact(Base):
    __tablename__ = "facts"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    claim: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)
    valid_from: Mapped[str | None] = mapped_column(String(50), nullable=True)
    valid_to: Mapped[str | None] = mapped_column(String(50), nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class QuestionVersion(Base):
    __tablename__ = "question_versions"
    __table_args__ = (UniqueConstraint("question_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"))
    version: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    branded: Mapped[bool] = mapped_column(Boolean)
    intent: Mapped[str] = mapped_column(String(200), default="")
    region: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(200))
    platform: Mapped[str] = mapped_column(String(100))
    source_id: Mapped[str] = mapped_column(String(200))
    parameter_mapping: Mapped[dict] = mapped_column(JSON, default=lambda: {"question": "question"})
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    result_mapping: Mapped[dict] = mapped_column(JSON, default=lambda: {"text": "normalized_data.response", "sources": "normalized_data.sources", "status": "normalized_data.status"})
    mode: Mapped[str] = mapped_column(String(100), default="browser")
    answer_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class Batch(Base):
    __tablename__ = "batches"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(200))
    mode: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(50), default="created")
    snapshot: Mapped[dict] = mapped_column(JSON)
    baseline_batch_id: Mapped[int | None] = mapped_column(ForeignKey("batches.id"), nullable=True)
    action_ids: Mapped[list] = mapped_column(JSON, default=list)
    content_version_ids: Mapped[list] = mapped_column(JSON, default=list)
    control_question_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("batch_id", "question_version_id", "source_config_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"))
    question_version_id: Mapped[int] = mapped_column(ForeignKey("question_versions.id"))
    source_config_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    remote_task_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="submitting")
    error: Mapped[str] = mapped_column(Text, default="")
    raw_result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("job_id", "record_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"))
    question_version_id: Mapped[int] = mapped_column(ForeignKey("question_versions.id"))
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    record_key: Mapped[str | None] = mapped_column(String(250), nullable=True)
    platform: Mapped[str] = mapped_column(String(100))
    text: Mapped[str] = mapped_column(Text)
    task_status: Mapped[str] = mapped_column(String(50))
    validity: Mapped[str] = mapped_column(String(20))
    invalid_reason: Mapped[str] = mapped_column(Text, default="")
    complete: Mapped[bool] = mapped_column(Boolean, default=False)
    sources: Mapped[list | None] = mapped_column(JSON, nullable=True)
    source_state: Mapped[str] = mapped_column(String(20))
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    observed_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    extracted_sources: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"))
    input_snapshot: Mapped[dict] = mapped_column(JSON)
    model_status: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Analysis(Base):
    __tablename__ = "analyses"
    __table_args__ = (UniqueConstraint("answer_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    answer_id: Mapped[int] = mapped_column(ForeignKey("answers.id"))
    run_id: Mapped[int] = mapped_column(ForeignKey("analysis_runs.id"))
    version: Mapped[int] = mapped_column(Integer)
    brand_mentioned: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    brand_evidence: Mapped[list] = mapped_column(JSON, default=list)
    competitor_evidence: Mapped[list] = mapped_column(JSON, default=list)
    recommendation: Mapped[str] = mapped_column(String(50), default="unknown")
    recommendation_evidence: Mapped[list] = mapped_column(JSON, default=list)
    rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rank_evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    factual_status: Mapped[str] = mapped_column(String(50), default="unknown")
    factual_findings: Mapped[list] = mapped_column(JSON, default=list)
    competitor_recommendations: Mapped[list] = mapped_column(JSON, default=list)
    model_status: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Diagnosis(Base):
    __tablename__ = "diagnoses"
    __table_args__ = (UniqueConstraint("answer_id", "kind", "analysis_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"))
    answer_id: Mapped[int] = mapped_column(ForeignKey("answers.id"))
    analysis_id: Mapped[int] = mapped_column(ForeignKey("analyses.id"))
    kind: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSON)
    hypothesis: Mapped[str] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Action(Base):
    __tablename__ = "actions"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(Text)
    question_ids: Mapped[list] = mapped_column(JSON, default=list)
    target_page: Mapped[str] = mapped_column(Text, default="")
    fact_ids: Mapped[list] = mapped_column(JSON, default=list)
    diagnosis_ids: Mapped[list] = mapped_column(JSON, default=list)
    owner: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(30), default="todo")
    acceptance_method: Mapped[str] = mapped_column(Text)
    due_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    blocked_reason: Mapped[str] = mapped_column(Text, default="")
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id"), nullable=True)
    page_id: Mapped[int | None] = mapped_column(ForeignKey("pages.id"), nullable=True)
    finding_id: Mapped[int | None] = mapped_column(ForeignKey("page_findings.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Content(Base):
    __tablename__ = "contents"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(200))
    target_url: Mapped[str] = mapped_column(Text, default="")
    action_id: Mapped[int | None] = mapped_column(ForeignKey("actions.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ContentVersion(Base):
    __tablename__ = "content_versions"
    __table_args__ = (UniqueConstraint("content_id", "version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    content_id: Mapped[int] = mapped_column(ForeignKey("contents.id"))
    version: Mapped[int] = mapped_column(Integer)
    before_text: Mapped[str] = mapped_column(Text, default="")
    after_text: Mapped[str] = mapped_column(Text)
    fact_ids: Mapped[list] = mapped_column(JSON)
    facts_snapshot: Mapped[list] = mapped_column(JSON)
    generation: Mapped[dict] = mapped_column(JSON, default=dict)
    published_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    review_status: Mapped[str] = mapped_column(String(30), default="pending")
    reviewer: Mapped[str] = mapped_column(String(200), default="")
    review_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("page_snapshots.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Opportunity(Base):
    __tablename__ = "opportunities"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(Text)
    question_ids: Mapped[list] = mapped_column(JSON, default=list)
    page_ids: Mapped[list] = mapped_column(JSON, default=list)
    decision_stage: Mapped[str] = mapped_column(String(30))
    business_value: Mapped[int] = mapped_column(Integer)
    business_fit: Mapped[int] = mapped_column(Integer)
    content_gap: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20))
    basis: Mapped[str] = mapped_column(String(30))
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    hypothesis: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Page(Base):
    __tablename__ = "pages"
    __table_args__ = (UniqueConstraint("project_id", "url"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, default="")
    page_type: Mapped[str] = mapped_column(String(100), default="service")
    owner: Mapped[str] = mapped_column(String(200), default="")
    next_review_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    review_interval_days: Mapped[int] = mapped_column(Integer, default=30)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PageSnapshot(Base):
    __tablename__ = "page_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id"))
    source_kind: Mapped[str] = mapped_column(String(30))
    requested_url: Mapped[str] = mapped_column(Text)
    final_url: Mapped[str] = mapped_column(Text, default="")
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(30))
    error: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    html: Mapped[str] = mapped_column(Text, default="")
    visible_text: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(Text, default="")
    meta_description: Mapped[str] = mapped_column(Text, default="")
    headings: Mapped[list] = mapped_column(JSON, default=list)
    canonical: Mapped[str] = mapped_column(Text, default="")
    robots_meta: Mapped[list] = mapped_column(JSON, default=list)
    json_ld: Mapped[list] = mapped_column(JSON, default=list)
    robots_txt: Mapped[dict] = mapped_column(JSON, default=dict)
    fetch_evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PageFinding(Base):
    __tablename__ = "page_findings"
    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id"))
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("page_snapshots.id"))
    kind: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSON)
    recommendation: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), default="info")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Publisher(Base):
    __tablename__ = "publishers"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(200))
    site_url: Mapped[str] = mapped_column(Text)
    resource: Mapped[str] = mapped_column(String(20), default="pages")
    post_id: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class PublicationJob(Base):
    __tablename__ = "publication_jobs"
    __table_args__ = (UniqueConstraint("content_version_id", "page_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    content_version_id: Mapped[int] = mapped_column(ForeignKey("content_versions.id"))
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id"))
    publisher_id: Mapped[int | None] = mapped_column(ForeignKey("publishers.id"), nullable=True)
    source_kind: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(40))
    error: Mapped[str] = mapped_column(Text, default="")
    target_url: Mapped[str] = mapped_column(Text)
    expected_hash: Mapped[str] = mapped_column(String(64))
    config_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    execution_evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    verified_at: Mapped[str | None] = mapped_column(String(50), nullable=True)


class PublicationVerification(Base):
    __tablename__ = "publication_verifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    publication_job_id: Mapped[int] = mapped_column(ForeignKey("publication_jobs.id"))
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("page_snapshots.id"))
    status: Mapped[str] = mapped_column(String(40))
    matched_by: Mapped[str] = mapped_column(String(50), default="")
    response_hash: Mapped[str] = mapped_column(String(64), default="")
    summary: Mapped[str] = mapped_column(Text)
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Research(Base):
    __tablename__ = "research"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    platform: Mapped[str] = mapped_column(String(100))
    channel: Mapped[str] = mapped_column(String(100))
    mode: Mapped[str] = mapped_column(String(100))
    scenario: Mapped[str] = mapped_column(Text)
    source_type: Mapped[str] = mapped_column(String(100))
    claim: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="hypothesis")
    conditions: Mapped[str] = mapped_column(Text)
    limitations: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    reviewer: Mapped[str] = mapped_column(String(200), default="")
    review_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ResearchRevision(Base):
    __tablename__ = "research_revisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    research_id: Mapped[int] = mapped_column(ForeignKey("research.id"))
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Experiment(Base):
    __tablename__ = "experiments"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(Text)
    hypothesis: Mapped[str] = mapped_column(Text)
    primary_change: Mapped[str] = mapped_column(Text)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id"))
    content_version_id: Mapped[int] = mapped_column(ForeignKey("content_versions.id"))
    baseline_batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"))
    retest_batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"))
    window_start: Mapped[str] = mapped_column(String(50))
    window_end: Mapped[str] = mapped_column(String(50))
    metric: Mapped[str] = mapped_column(String(40))
    direction: Mapped[str] = mapped_column(String(20))
    conditions: Mapped[str] = mapped_column(Text)
    limitations: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="hypothesis")
    reviewer: Mapped[str] = mapped_column(String(200), default="")
    review_note: Mapped[str] = mapped_column(Text, default="")
    comparison: Mapped[dict] = mapped_column(JSON)
    analysis_run_ids: Mapped[dict] = mapped_column(JSON)
    control_question_ids: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    reviewed_at: Mapped[str | None] = mapped_column(String(50), nullable=True)


class OperationRule(Base):
    __tablename__ = "operation_rules"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(Text)
    instruction: Mapped[str] = mapped_column(Text)
    conditions: Mapped[str] = mapped_column(Text)
    limitations: Mapped[str] = mapped_column(Text)
    experiment_id: Mapped[int | None] = mapped_column(ForeignKey("experiments.id"), nullable=True)
    research_id: Mapped[int | None] = mapped_column(ForeignKey("research.id"), nullable=True)
    reviewer: Mapped[str] = mapped_column(String(200))
    review_note: Mapped[str] = mapped_column(Text)
    source_snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ResearchSourceSnapshot(Base):
    __tablename__ = "research_source_snapshots"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    url: Mapped[str] = mapped_column(Text)
    final_url: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(Text, default="")
    visible_text: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(30))
    error: Mapped[str] = mapped_column(Text, default="")
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fetch_evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AgentRun(Base):
    __tablename__ = "agent_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    goal: Mapped[str] = mapped_column(Text)
    policy: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="queued")
    phase: Mapped[str] = mapped_column(String(60), default="context")
    blocked_reason: Mapped[str] = mapped_column(Text, default="")
    checkpoint: Mapped[dict] = mapped_column(JSON, default=dict)
    lease_owner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_due: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class AgentStep(Base):
    __tablename__ = "agent_steps"
    __table_args__ = (UniqueConstraint("run_id", "key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id"))
    key: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(30), default="running")
    summary: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    output: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class AgentApproval(Base):
    __tablename__ = "agent_approvals"
    __table_args__ = (UniqueConstraint("proposal_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id"))
    proposal_id: Mapped[int] = mapped_column(ForeignKey("agent_steps.id"))
    decision: Mapped[str] = mapped_column(String(30))
    feedback: Mapped[str] = mapped_column(Text)
    reviewer: Mapped[str] = mapped_column(String(200))
    allow_publish: Mapped[bool] = mapped_column(Boolean, default=False)
    bindings: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
