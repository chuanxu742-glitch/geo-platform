export interface Project {
  id: number;
  name: string;
  brand: string;
  aliases: string[];
  website_url: string;
  region: string;
  created_at: string;
}
export interface QuestionVersion {
  id: number;
  question_id: number;
  version: number;
  text: string;
  branded: boolean;
  intent: string;
  region: string;
  created_at: string;
}
export interface Question {
  id: number;
  project_id: number;
  archived: boolean;
  current_version: QuestionVersion;
}
export interface Source {
  id: number;
  name: string;
  platform: string;
  source_id: string;
  parameter_mapping: Record<string, string>;
  parameters: Record<string, unknown>;
  result_mapping: Record<string, string>;
  mode: string;
  answer_complete: boolean;
}
export interface Fact {
  id: number;
  project_id: number;
  claim: string;
  source_url: string;
  valid_from: string | null;
  valid_to: string | null;
}
export interface Answer {
  id: number;
  batch_id: number;
  question_version_id: number;
  platform: string;
  text: string;
  task_status: string;
  validity: "valid" | "invalid" | "unknown";
  invalid_reason: string;
  complete: boolean;
  sources: { url: string; title?: string; type?: string }[] | null;
  source_state: string;
  raw: Record<string, unknown>;
  created_at: string;
}
export interface Batch {
  id: number;
  project_id: number;
  name: string;
  mode: string;
  status: string;
  baseline_batch_id: number | null;
  action_ids: number[];
  content_version_ids: number[];
  control_question_ids: number[];
  snapshot: {
    questions: QuestionVersion[];
    sources: Source[];
    sampling: { platforms?: string[]; [key: string]: unknown };
    [key: string]: unknown;
  };
  created_at: string;
  answers?: Answer[];
  jobs?: Record<string, unknown>[];
}
export const statusLabel: Record<string, string> = {
  valid: "有效",
  invalid: "无效",
  unknown: "未知",
  completed: "已完成",
  failed: "失败",
  pending: "等待 / 待复核",
  todo: "待办",
  in_progress: "进行中",
  done: "完成",
  cancelled: "取消",
  accepted: "已接受",
  rejected: "已拒绝",
  consistent: "一致",
  inconsistent: "事实不一致",
  neutral: "中性 / 未明确推荐",
  recommended: "明确推荐",
  not_recommended: "明确不建议",
};
