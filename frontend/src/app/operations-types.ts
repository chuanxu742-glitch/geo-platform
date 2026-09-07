import type { Answer, Batch, Fact, Question } from "./types";
export interface OpsAction {
  id: number;
  project_id: number;
  title: string;
  owner: string;
  due_at: string | null;
  status: string;
  acceptance_method: string;
  blocked_reason: string;
  question_ids: number[];
  fact_ids: number[];
  diagnosis_ids: number[];
  opportunity_id: number | null;
  page_id: number | null;
  finding_id: number | null;
  target_page: string;
}
export interface Evidence {
  url: string;
  quote: string;
  answer_id?: number;
}
export interface Opportunity {
  id: number;
  title: string;
  question_ids: number[];
  page_ids: number[];
  decision_stage: string;
  business_value: number;
  business_fit: number;
  content_gap: string;
  priority: string;
  basis: string;
  evidence: Evidence[];
  hypothesis: string;
  status: string;
}
export interface Finding {
  id: number;
  page_id: number;
  snapshot_id: number;
  kind: string;
  title: string;
  evidence: { location?: string; observed?: unknown; [key: string]: unknown };
  recommendation: string;
  severity: string;
}
export interface PageSnapshot {
  id: number;
  page_id: number;
  source_kind: string;
  requested_url: string;
  final_url: string;
  http_status: number | null;
  status: string;
  error: string;
  content_hash: string;
  html: string;
  visible_text: string;
  title: string;
  meta_description: string;
  headings: { level: number; text: string }[];
  canonical: string;
  robots_meta: string[];
  json_ld: unknown[];
  robots_txt: {
    status: string;
    url: string;
    content: string;
    agents: Record<string, boolean | null>;
  };
  fetch_evidence: Record<string, unknown>;
  created_at: string;
  findings: Finding[];
}
export interface SitePage {
  id: number;
  project_id: number;
  url: string;
  title: string;
  page_type: string;
  owner: string;
  next_review_at: string | null;
  review_interval_days: number;
  latest_snapshot: PageSnapshot | null;
  latest_publication: PublicationJob | null;
  maintenance_reasons: string[];
}
export interface ContentVersion {
  id: number;
  content_id: number;
  version: number;
  before_text: string;
  after_text: string;
  fact_ids: number[];
  facts_snapshot: Fact[];
  published_at: string | null;
  review_status: string;
  reviewer: string;
  review_note: string;
  reviewed_at: string | null;
  source_snapshot_id: number | null;
  generation?: Record<string, unknown>;
}
export interface Content {
  id: number;
  title: string;
  target_url: string;
  action_id: number | null;
  versions: ContentVersion[];
}
export interface Publisher {
  id: number;
  name: string;
  site_url: string;
  resource: "pages" | "posts";
  post_id: number;
  enabled: boolean;
}
export interface PublicationJob {
  id: number;
  project_id: number;
  content_version_id: number;
  page_id: number;
  publisher_id: number | null;
  source_kind: string;
  status: string;
  error: string;
  target_url: string;
  expected_hash: string;
  config_snapshot: Record<string, unknown>;
  execution_evidence: Record<string, unknown>;
  verified_at: string | null;
  verifications?: {
    id: number;
    status: string;
    matched_by: string;
    summary: string;
    verified_at: string;
  }[];
}
export interface OperationsSummary {
  project_id: number;
  as_of: string;
  counts: Record<string, number>;
  week_plan: OpsAction[];
  today: OpsAction[];
  blocked: OpsAction[];
  pending_review: ContentVersion[];
  ready_to_publish: (ContentVersion & {
    content_title: string;
    target_url: string;
    blocked_reason: string;
  })[];
  awaiting_verification: PublicationJob[];
  maintenance_due: SitePage[];
  failed_publications: PublicationJob[];
  next_steps: {
    kind: string;
    id: number;
    title: string;
    reason: string;
    href: string;
  }[];
}
export interface Research {
  id: number;
  platform: string;
  channel: string;
  mode: string;
  scenario: string;
  source_type: string;
  claim: string;
  status: string;
  conditions: string;
  limitations: string;
  evidence: Evidence[];
  reviewer: string;
  review_note: string;
  revisions?: unknown[];
}
export interface Experiment {
  id: number;
  title: string;
  hypothesis: string;
  primary_change: string;
  page_id: number;
  content_version_id: number;
  baseline_batch_id: number;
  retest_batch_id: number;
  window_start: string;
  window_end: string;
  metric: string;
  direction: string;
  conditions: string;
  limitations: string;
  status?: string;
  comparison?: Record<string, unknown>;
  compare_snapshot?: Record<string, unknown>;
  conclusion?: Record<string, unknown>;
  [key: string]: unknown;
}
export interface OperatingRule {
  id: number;
  title: string;
  instruction: string;
  conditions: string;
  limitations: string;
  experiment_id: number | null;
  research_id: number | null;
  reviewer: string;
  review_note: string;
}
export type OpsContext = {
  projectId: number;
  revision: number;
  refresh: () => void;
  navigate: (area: string) => void;
};
export type SelectionData = {
  questions: Question[];
  facts: Fact[];
  pages: SitePage[];
  contents: Content[];
  batches: Batch[];
  answers: Answer[];
};
export const opsLabels: Record<string, string> = {
  awareness: "认知",
  consideration: "考虑",
  decision: "决策",
  retention: "留存",
  high: "高",
  medium: "中",
  low: "低",
  hypothesis: "待验证假设",
  evidence: "已有证据",
  supported: "当前证据支持",
  inconclusive: "证据不足",
  refuted: "当前证据反驳",
  open: "待计划",
  planned: "已计划",
  closed: "已关闭",
  todo: "待办",
  in_progress: "进行中",
  done: "完成",
  cancelled: "取消",
  blocked: "受阻",
  awaiting_review: "待审核",
  pending: "待审核",
  approved: "审核通过",
  rejected: "已退回",
  submitting: "正在提交",
  submission_unknown: "提交不确定，需人工核对",
  running: "远端执行中",
  execution_failed: "远端执行失败",
  awaiting_verification: "执行完成，待页面核验",
  verification_failed: "页面核验失败",
  verified: "页面已核验",
  manual_import: "人工导入HTML",
  http: "HTTP抓取",
  success: "观察成功",
  failure: "抓取失败",
  wordpress: "WordPress 既有资源更新",
  external_record: "人工外部发布记录",
};
export interface ResearchSourceSnapshot {
  id: number;
  project_id: number;
  url: string;
  final_url: string;
  title: string;
  visible_text: string;
  content_hash: string;
  status: string;
  error: string;
  http_status: number | null;
  fetch_evidence: Record<string, unknown>;
  created_at: string;
}
