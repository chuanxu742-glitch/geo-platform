"use client";
import { useState } from "react";
import {
  Action,
  api,
  Empty,
  Form,
  Load,
  useData,
  LinkURL,
  type Field,
  type Row,
} from "./ui";
import { Actions } from "./actions";
import { Prelude } from "./visual";
import type { Batch, Question } from "./types";
import {
  opsLabels,
  type OpsContext,
  type OperationsSummary,
  type Opportunity,
  type SitePage,
  type OpsAction,
} from "./operations-types";

const briefSections = [
  { key: "applicability", label: "适用条件", hint: "适合谁、适用地区、前提条件与不适用情形。" },
  { key: "steps", label: "办理步骤", hint: "准备材料、操作顺序、负责方与预计时间；未核实的时间标为待确认。" },
  { key: "fees", label: "费用说明", hint: "收费项目、计费依据、包含与不包含项、生效日期；未知费用不填写估算值。" },
  { key: "sources", label: "可核验来源", hint: "填写来源链接、对应主张与核验日期；区分客户原话和业务事实。" },
  { key: "cases", label: "真实案例", hint: "仅填写可核验且可公开的案例、适用背景与局限；没有案例就写暂无。" },
  { key: "acceptance", label: "验收方式", hint: "谁在何时检查哪些内容、如何核对来源与页面正文，以及客户下一步入口是否可用。" },
];

type QueryMeasurement = {
  id: number;
  date: string;
  page_url: string;
  channel: string;
  query: string;
  source_label?: string;
  impressions: number | null;
  clicks: number | null;
  leads: number | null;
  orders: number | null;
};
const queryMetrics = [
  ["impressions", "曝光"], ["clicks", "点击"], ["leads", "线索"], ["orders", "订单"],
] as const;
const queryMetricText = (row: QueryMeasurement) => queryMetrics.map(([key, label]) => `${label}：${row[key] == null ? "未知" : row[key]}`).join("；");

function QueryCandidates({ projectId, revision, onPrepare }: {
  projectId: number;
  revision: number;
  onPrepare: (row: QueryMeasurement, question: Question) => void;
}) {
  const state = useData<{ rows: QueryMeasurement[] }>(`projects/${projectId}/measurements`, revision);
  const [selected, setSelected] = useState<QueryMeasurement | null>(null);
  const [preparing, setPreparing] = useState(false);
  const candidates = (state.data?.rows ?? []).filter((row) => row.query.trim());
  return <section className="card" style={{ minWidth: 0, overflowWrap: "anywhere" }}>
    <h2>从真实查询记录选择候选问题</h2>
    <p className="muted">以下为已导入的查询记录，按原记录展示，不自动排序优先级。未知不等于 0；观察到查询词不证明优化有效，也不能单独确认购买需求。</p>
    <Load state={state}>
      {!candidates.length && <Empty>暂无包含查询词的测量记录。可先在效果测量中导入真实数据，或继续手动新增机会。</Empty>}
      {!!candidates.length && <div className="table-wrap" tabIndex={0} role="region" aria-label="真实查询候选记录">
        <table>
          <thead><tr><th scope="col">查询词</th><th scope="col">来源 / 日期</th><th scope="col">页面 / 渠道</th><th scope="col">已导入指标</th><th scope="col">操作</th></tr></thead>
          <tbody>{candidates.map((row) => <tr key={row.id}>
            <td>{row.query}</td><td>{row.source_label || "来源未知"}<br />{row.date}</td>
            <td><LinkURL url={row.page_url} /><br />{row.channel === "other" ? "其他" : row.channel.toUpperCase()}</td>
            <td>{queryMetricText(row)}</td>
            <td><button type="button" className="secondary" disabled={preparing} aria-pressed={selected?.id === row.id} onClick={() => setSelected(row)}>选择此查询词</button></td>
          </tr>)}</tbody>
        </table>
      </div>}
    </Load>
    {selected && <div>
      <p>已选择：<strong>{selected.query}</strong>。确认后将复用文字及品牌分类相同的已有问题；若没有则新建问题，机会仍需填写并保存。</p>
      <Form key={selected.id} title="确认查询词并准备新机会" expanded fields={[
        { key: "branded", label: "这个查询词是否包含品牌？", required: true, options: [
          { value: "", label: "请人工判断" }, { value: "yes", label: "包含品牌" }, { value: "no", label: "不含品牌" },
        ] },
      ]} submit="确认创建或复用问题，并带入新增机会" onSubmit={async (body) => {
        setPreparing(true);
        try {
        const text = selected.query.trim();
        const branded = body.branded === "yes";
        const latest: Question[] = await api(`projects/${projectId}/questions`);
        const existing = latest.find((q) => q.current_version.text.trim() === text && q.current_version.branded === branded);
        const question: Question = existing ?? await api(`projects/${projectId}/questions`, "POST", { text, branded });
        onPrepare(selected, question);
        setSelected(null);
        } finally {
          setPreparing(false);
        }
      }} />
    </div>}
  </section>;
}

function OpportunityBrief({ opportunity, questions, pages, onPrepare }: {
  opportunity: Opportunity;
  questions: Question[];
  pages: SitePage[];
  onPrepare: (preset: Row) => void;
}) {
  return (
    <details className="form-disclosure">
      <summary>填写内容简报 → 带入行动任务</summary>
      <form className="form" onSubmit={(event) => {
        event.preventDefault();
        const body = Object.fromEntries(new FormData(event.currentTarget));
        const page = pages.find((p) => p.id === Number(body.page_id));
        const questionText = opportunity.question_ids.map((id) => questions.find((q) => q.id === id)?.current_version.text || `问题 #${id}（暂无法读取）`);
        const brief = [
          `客户问题：${questionText.join("；") || opportunity.title}`,
          `依据类型：${opsLabels[opportunity.basis] || opportunity.basis}`,
          `证据：${opportunity.evidence.map((e) => [e.quote, e.url].filter(Boolean).join(" — ")).join("；") || "暂无，需补充"}`,
          `待验证假设：${opportunity.hypothesis || "未填写"}`,
          `业务价值：${opportunity.business_value}/5；业务适配：${opportunity.business_fit}/5（人工判断）`,
          `内容缺口：${opportunity.content_gap}`,
          `目标页面：${page?.url || "待确定"}`,
          ...briefSections.map((s) => `${s.label}：${String(body[s.key] || "").trim() || "待补充，不作事实陈述"}`),
          "验收边界：页面内容核验与后续效果观测分别记录，不承诺排名、引用或成交结果。",
        ].join("\n\n");
        onPrepare({ title: `完善内容：${opportunity.title}`, opportunity_id: opportunity.id,
          question_ids: opportunity.question_ids, page_id: page?.id ?? null,
          target_page: page?.url ?? "", acceptance_method: brief });
      }}>
        <div className="fields">
          <label className="wide">
            <span>本次要优化的页面</span>
            <select name="page_id" defaultValue={opportunity.page_ids.length === 1 ? String(opportunity.page_ids[0]) : ""}>
              <option value="">尚未确定页面</option>
              {pages.map((p) => <option key={p.id} value={p.id}>{opportunity.page_ids.includes(p.id) ? "已关联 · " : ""}{p.title || p.url}</option>)}
            </select>
          </label>
          {briefSections.map((s) => <label className="wide" key={s.key}>
            <span>{s.label}{s.key === "acceptance" ? " *" : ""}</span>
            <textarea name={s.key} rows={3} required={s.key === "acceptance"} aria-describedby={`brief-${opportunity.id}-${s.key}`} />
            <small id={`brief-${opportunity.id}-${s.key}`}>{s.hint}</small>
          </label>)}
        </div>
        <p className="muted">此处填写的是临时简报，带入后请在任务表单中确认并保存。</p>
        <button type="submit">带入任务表单（尚未保存）</button>
      </form>
    </details>
  );
}
export function OperationsHome({
  projectId,
  revision,
  refresh,
  navigate,
}: OpsContext) {
  const state = useData<OperationsSummary>(
    `projects/${projectId}/operations/summary`,
    revision,
  );
  const opportunities = useData<Opportunity[]>(
    `projects/${projectId}/opportunities`,
    revision,
  );
  const [period, setPeriod] = useState("week");
  return (
    <Load state={state}>
      {state.data && (
        <>
          <div className="ops-intro">
            <div>
              <p className="eyebrow">从观察走向执行</p>
              <h2>把下一步，落到今天。</h2>
              <p>
                先优化已有页面，再审核与发布。每个结果保留依据，每项行动都有负责人和验收条件。
              </p>
            </div>
            <div className="ops-asof">
              工作清单更新于
              <br />
              {new Date(state.data.as_of).toLocaleString("zh-CN")}
            </div>
          </div>
          <div className="ops-counts">
            {[
              { key: "week_plan", title: "本周计划", area: "plans" },
              { key: "pending_review", title: "待审核稿", area: "content" },
              { key: "ready_to_publish", title: "已审待发布", area: "content" },
              {
                key: "awaiting_verification",
                title: "待正文核验",
                area: "content",
              },
              {
                key: "failed_publications",
                title: "失败发布",
                area: "content",
              },
              { key: "maintenance_due", title: "到期维护", area: "pages" },
            ].map((c) => (
              <button key={c.key} onClick={() => navigate(c.area)}>
                <span>{c.title}</span>
                <strong>{state.data!.counts[c.key] ?? 0}</strong>
                <small>查看工作项 ↗</small>
              </button>
            ))}
          </div>
          <div className="ops-columns">
            <section>
              <div className="section-toolbar">
                <h2>执行清单</h2>
                <div className="segmented">
                  <button
                    aria-pressed={period === "today"}
                    onClick={() => setPeriod("today")}
                  >
                    今日
                  </button>
                  <button
                    aria-pressed={period === "week"}
                    onClick={() => setPeriod("week")}
                  >
                    本周
                  </button>
                </div>
              </div>
              {!(period === "today" ? state.data.today : state.data.week_plan)
                .length && (
                <Empty>
                  尚未安排到期任务。从一个业务问题或页面发现创建行动，并填写负责人、到期时间与验收方式。
                </Empty>
              )}
              {(period === "today"
                ? state.data.today
                : state.data.week_plan
              ).map((task) => (
                <article className="work-item" key={task.id}>
                  <div>
                    <span className="status-tag">
                      {opsLabels[task.status] ?? task.status}
                    </span>
                    <h3>{task.title}</h3>
                    <p>{task.acceptance_method}</p>
                    <small>
                      {task.owner || "未分配"} ·{" "}
                      {task.due_at
                        ? new Date(task.due_at).toLocaleString("zh-CN")
                        : "未安排到期"}
                      {task.blocked_reason ? ` · ${task.blocked_reason}` : ""}
                    </small>
                  </div>
                  <div className="toolbar">
                    {task.status === "todo" && (
                      <Action
                        run={async () => {
                          await api(`actions/${task.id}`, "PATCH", {
                            status: "in_progress",
                          });
                          refresh();
                        }}
                      >
                        开始执行
                      </Action>
                    )}
                    <button className="ghost" onClick={() => navigate("plans")}>
                      编辑 / 状态流转 ↗
                    </button>
                  </div>
                </article>
              ))}
              <button onClick={() => navigate("plans")}>
                安排本周优化计划 ↗
              </button>
            </section>
            <aside className="ops-margin">
              <h2>优先优化机会</h2>
              {!(opportunities.data ?? []).some(
                (o) => o.status !== "closed",
              ) && (
                <p className="muted">
                  没有预填机会。可以从真实业务问题建立假设，再逐步补齐证据。
                </p>
              )}
              {(opportunities.data ?? [])
                .filter((o) => o.status !== "closed")
                .sort(
                  (a, b) =>
                    (({ high: 0, medium: 1, low: 2 })[a.priority as "high"] ??
                      3) -
                    ({ high: 0, medium: 1, low: 2 }[b.priority as "high"] ?? 3),
                )
                .slice(0, 4)
                .map((o) => (
                  <article className="margin-note" key={o.id}>
                    <small>
                      {opsLabels[o.priority]}优先级 · {opsLabels[o.basis]}
                    </small>
                    <h3>{o.title}</h3>
                    <p>{o.content_gap}</p>
                    <button className="ghost" onClick={() => navigate("plans")}>
                      纳入计划 ↗
                    </button>
                  </article>
                ))}
              <h2>下一步</h2>
              {state.data.next_steps.map((step, i) => (
                <button
                  className="next-step"
                  key={`${step.kind}-${step.id}-${i}`}
                  onClick={() =>
                    navigate(
                      /review|publish|content|verify/.test(step.kind)
                        ? "content"
                        : /page|mainten/.test(step.kind)
                          ? "pages"
                          : "plans",
                    )
                  }
                >
                  <strong>{step.title}</strong>
                  <small>{step.reason}</small>
                </button>
              ))}
              <div className="quick-links">
                <button className="secondary" onClick={() => navigate("pages")}>
                  诊断现有页面
                </button>
                <button
                  className="secondary"
                  onClick={() => navigate("research")}
                >
                  记录研究与实验
                </button>
                <button
                  className="ghost"
                  onClick={() => navigate("observation")}
                >
                  观测与验收 ↗
                </button>
              </div>
            </aside>
          </div>
          <div className="ops-followup">
            <section>
              <h2>待审核稿</h2>
              {state.data.pending_review.length ? (
                state.data.pending_review.map((v) => (
                  <button
                    className="next-step"
                    key={v.id}
                    onClick={() => navigate("content")}
                  >
                    内容版本 v{v.version}
                    <small>{v.after_text.slice(0, 100)}</small>
                  </button>
                ))
              ) : (
                <p className="muted">当前没有待审核版本。</p>
              )}
            </section>
            <section>
              <h2>发布与维护</h2>
              {(state.data.ready_to_publish ?? []).map((v) => (
                <button
                  className="next-step"
                  key={`ready-${v.id}`}
                  onClick={() => navigate("content")}
                >
                  <strong>
                    已审核待发布 · {v.content_title} v{v.version}
                  </strong>
                  <small>
                    {v.blocked_reason || "需要操作员明确授权，不自动发布"}
                  </small>
                </button>
              ))}
              {(state.data.awaiting_verification ?? []).map((j) => (
                <button
                  className="next-step"
                  key={`verify-${j.id}`}
                  onClick={() => navigate("content")}
                >
                  <strong>{opsLabels[j.status]} · 等待批准正文核验</strong>
                  <small>{j.target_url}</small>
                </button>
              ))}
              {state.data.failed_publications.map((j) => (
                <button
                  className="next-step"
                  key={j.id}
                  onClick={() => navigate("content")}
                >
                  <strong>{opsLabels[j.status] ?? j.status}</strong>
                  <small>
                    {j.target_url} · {j.error || "请核对页面正文"}
                  </small>
                </button>
              ))}
              {state.data.maintenance_due.map((p) => (
                <button
                  className="next-step"
                  key={p.id}
                  onClick={() => navigate("pages")}
                >
                  <strong>{p.title || p.url}</strong>
                  <small>
                    {p.maintenance_reasons.join("；") || "已到维护时间"}
                  </small>
                </button>
              ))}
              {!state.data.failed_publications.length &&
                !state.data.maintenance_due.length &&
                !(state.data.ready_to_publish ?? []).length &&
                !(state.data.awaiting_verification ?? []).length && (
                  <p className="muted">
                    当前没有待处理的发布或到期维护项。页面核验不等于 AI
                    已索引、引用或产生优化效果。
                  </p>
                )}
            </section>
          </div>
        </>
      )}
    </Load>
  );
}
export function Opportunities(props: OpsContext) {
  return <OpportunitiesProject key={props.projectId} {...props} />;
}

function OpportunitiesProject({
  projectId,
  revision,
  refresh,
  navigate,
}: OpsContext) {
  const state = useData<Opportunity[]>(
      `projects/${projectId}/opportunities`,
      revision,
    ),
    questions = useData<Question[]>(
      `projects/${projectId}/questions`,
      revision,
    ),
    pages = useData<SitePage[]>(`projects/${projectId}/pages`, revision),
    batches = useData<Batch[]>(`projects/${projectId}/batches`, revision),
    actions = useData<OpsAction[]>(`projects/${projectId}/actions`, revision);
  const [preset, setPreset] = useState<Row>({}),
    [stage, setStage] = useState("");
  const [candidate, setCandidate] = useState<{ row: QueryMeasurement; question: Question } | null>(null);
  const availableQuestions = [...(questions.data ?? [])];
  if (candidate && !availableQuestions.some((q) => q.id === candidate.question.id)) availableQuestions.push(candidate.question);
  const prepareTask = (body: Row) => {
    setPreset(body);
    requestAnimationFrame(() => {
      document.getElementById("opportunity-actions")?.scrollIntoView({ behavior: "smooth" });
      document.querySelector<HTMLInputElement>('#opportunity-actions #create-action input[name="title"]')?.focus({ preventScroll: true });
    });
  };
  const fields: Field[] = [
    { key: "title", label: "客户在问什么 / 机会标题", required: true, hint: "记录客户原话或明确标为待验证的问题，例如适用条件、流程或费用。" },
    {
      key: "decision_stage",
      label: "用户决策阶段",
      options: ["awareness", "consideration", "decision", "retention"].map(
        (value) => ({ value, label: opsLabels[value] }),
      ),
    },
    {
      key: "business_value",
      label: "业务价值（人工判断 1–5，非搜索量）",
      hint: "1：与业务目标关系弱；3：有助客户判断；5：直接影响关键决策。",
      type: "number",
      required: true,
    },
    {
      key: "business_fit",
      label: "业务适配（人工判断 1–5）",
      hint: "1：超出服务范围；3：部分可承接；5：现有服务与事实材料能充分支持。",
      type: "number",
      required: true,
    },
    {
      key: "question_ids",
      label: "目标问题",
      required: true,
      type: "ids",
      multiple: true,
      options: availableQuestions.map((q) => ({
        value: String(q.id),
        label: q.current_version.text,
      })),
    },
    {
      key: "page_ids",
      label: "目标页面",
      type: "ids",
      multiple: true,
      options: (pages.data ?? []).map((p) => ({
        value: String(p.id),
        label: p.title || p.url,
      })),
    },
    {
      key: "content_gap",
      label: "内容缺口 / 决策障碍",
      hint: "客户缺少什么信息？为什么值得做、能否承接，以及页面应补充什么？",
      type: "textarea",
      required: true,
    },
    {
      key: "priority",
      label: "人工优先级",
      options: ["medium", "high", "low"].map((value) => ({
        value,
        label: opsLabels[value],
      })),
    },
    {
      key: "basis",
      label: "依据类型",
      options: [
        { value: "hypothesis", label: "待验证假设" },
        { value: "evidence", label: "有来源证据" },
      ],
    },
    { key: "hypothesis", label: "明确假设与尚未证实之处", type: "textarea" },
    { key: "evidence_url", label: "证据来源 URL", type: "url" },
    {
      key: "evidence_quote",
      label: "原始证据摘录（不编造）",
      type: "textarea",
    },
    {
      key: "status",
      label: "机会状态",
      options: ["open", "planned", "closed"].map((value) => ({
        value,
        label: opsLabels[value],
      })),
    },
  ];
  const fieldOrder = ["title", "question_ids", "decision_stage", "basis", "hypothesis", "evidence_url", "evidence_quote", "business_value", "business_fit", "content_gap", "page_ids", "priority", "status"];
  fields.sort((a, b) => fieldOrder.indexOf(a.key) - fieldOrder.indexOf(b.key));
  const save = async (body: Row, id?: number) => {
    const { evidence_url, evidence_quote, ...rest } = body;
    if (![rest.business_value, rest.business_fit].every((value) => Number.isInteger(value) && value >= 1 && value <= 5))
      throw Error("价值与适配须为 1–5 的整数。");
    const existingEvidence = state.data?.find((o) => o.id === id)?.evidence ?? [];
    if ((evidence_url || evidence_quote) && !(evidence_url && evidence_quote))
      throw Error("请同时填写证据来源 URL 和原始摘录。");
    if (rest.basis === "hypothesis" && !String(rest.hypothesis || "").trim())
      throw Error("请说明待验证假设与尚未证实之处。");
    await api(
      id ? `opportunities/${id}` : `projects/${projectId}/opportunities`,
      id ? "PATCH" : "POST",
      {
        ...rest,
        evidence:
          [
            ...(evidence_url || evidence_quote ? [{ ...existingEvidence[0], url: evidence_url, quote: evidence_quote }] : []),
            ...existingEvidence.slice(1),
          ],
      },
    );
    refresh();
  };
  return (
    <>
      <div className="ops-intro">
        <div>
          <p className="eyebrow">从客户问题到内容行动</p>
          <h2>先回答客户的疑问，再安排值得做的内容。</h2>
          <p>保留问题原话与来源，判断业务价值和承接能力，选择页面，再交付有验收方式的内容简报。</p>
        </div>
      </div>
      <ol style={{ display: "flex", flexWrap: "wrap", gap: "12px 32px", paddingInlineStart: 24 }} aria-label="商机工作步骤">
        <li>客户问题</li><li>证据或假设</li><li>价值与适配</li><li>目标页面</li><li>行动与简报</li>
      </ol>
      <p className="notice">问题记录不代表已有市场需求；价值和适配是人工判断。尚无来源时保留为假设，未知费用、案例与结果不作补全。</p>
      <QueryCandidates projectId={projectId} revision={revision} onPrepare={(row, question) => {
        setCandidate({ row, question });
        refresh();
        requestAnimationFrame(() => {
          document.getElementById("query-opportunity-draft")?.scrollIntoView({ behavior: "smooth" });
          document.querySelector<HTMLInputElement>('#query-opportunity-draft input[name="title"]')?.focus({ preventScroll: true });
        });
      }} />
      {candidate && <section id="query-opportunity-draft" className="card">
        <h2>由查询记录准备的新机会</h2>
        <p role="status">已关联问题 #{candidate.question.id}：{candidate.question.current_version.text}。机会尚未保存，请补充内容缺口与人工判断；下方手动新增表单保留不变。</p>
        <p className="muted">来源：{candidate.row.source_label || "未知"} · {candidate.row.date} · 观测页面：<LinkURL url={candidate.row.page_url} />。页面链接仅标识观测对象，数据来源以导入凭据说明为准。</p>
        <Form key={`${candidate.row.id}-${candidate.question.id}`} expanded title="完善并保存查询机会" fields={fields.map((field) =>
          ["priority", "decision_stage"].includes(field.key) ? { ...field, required: true, options: [{ value: "", label: "请人工选择" }, ...(field.options ?? [])] } : field
        )} initial={{
          title: candidate.row.query,
          question_ids: [candidate.question.id],
          page_ids: (pages.data ?? []).filter((page) => page.url === candidate.row.page_url).map((page) => page.id),
          business_value: "", business_fit: "", priority: "", decision_stage: "",
          basis: "hypothesis", status: "open",
          hypothesis: `已导入查询记录：${candidate.row.query}\n来源：${candidate.row.source_label || "未知"}；日期：${candidate.row.date}；渠道：${candidate.row.channel}\n观测页面：${candidate.row.page_url}\n${queryMetricText(candidate.row)}\n待验证：此查询是否反映目标客户的决策障碍，以及页面是否需要补充内容；查询记录不证明优化效果或购买需求。`,
        }} submit="保存为新机会" onSubmit={async (body) => {
          await save(body);
          setCandidate(null);
        }} />
        <button type="button" className="ghost" onClick={() => setCandidate(null)}>收起此次机会草稿（保留已保存的问题）</button>
      </section>}
      <div className="section-toolbar">
        <h2>业务问题地图</h2>
        <label>
          决策阶段
          <select value={stage} onChange={(e) => setStage(e.target.value)}>
            <option value="">全部阶段</option>
            {["awareness", "consideration", "decision", "retention"].map(
              (s) => (
                <option key={s} value={s}>
                  {opsLabels[s]}
                </option>
              ),
            )}
          </select>
        </label>
      </div>
      <Load state={state}>
        {!state.data?.length && (
          <Prelude
            compact
            title="从一个真实业务问题开始。"
            action={
              <button className="secondary" onClick={() => navigate("pages")}>
                先登记需要优化的页面 ↗
              </button>
            }
          >
            描述用户在何处犹豫、现有内容缺少什么，再安排可验收的优化行动。
          </Prelude>
        )}
        {!!state.data?.length && !state.data.some((o) => !stage || o.decision_stage === stage) && <Empty>这个决策阶段暂无机会，可切换到全部阶段或新增记录。</Empty>}
        {state.data
          ?.filter((o) => !stage || o.decision_stage === stage)
          .map((o) => (
            <article key={o.id} className="work-item" style={{ display: "block", minWidth: 0, overflowWrap: "anywhere" }}>
              <p className="eyebrow">
                {opsLabels[o.decision_stage]} / {opsLabels[o.priority]}优先级 /{" "}
                {opsLabels[o.basis]}
              </p>
              <h3>{o.title}</h3>
              <h4>1 · 客户问题</h4>
              {o.question_ids.length ? <ul>{o.question_ids.map((id) => <li key={id}>{questions.data?.find((q) => q.id === id)?.current_version.text || `问题 #${id}（暂无法读取）`}</li>)}</ul> : <p className="muted">尚未关联问题。请在编辑中选择已有问题，并核对是否来自真实客户。</p>}
              <h4>2 · 证据与待验证假设</h4>
              {!o.evidence.length && <p className="muted">暂无来源证据，不能据此确认需求。</p>}
              {o.hypothesis && <p className="notice">假设：{o.hypothesis}</p>}
              {o.evidence.map((e, i) => (
                <figure className="evidence-notes" key={i}>
                  <blockquote>{e.quote || "未填写摘录，请核验原文。"}</blockquote>
                  <figcaption><LinkURL url={e.url} /></figcaption>
                </figure>
              ))}
              <h4>3 · 业务价值与适配</h4>
              <p>{o.content_gap}</p>
              <p className="muted">
                价值 {o.business_value}/5 · 适配 {o.business_fit}/5 ·{" "}
                {opsLabels[o.status]}
              </p>
              <h4>4 · 目标页面</h4>
              {o.page_ids.length ? <ul>{o.page_ids.map((id) => {
                const page = pages.data?.find((p) => p.id === id);
                return <li key={id}>{page ? <><span>{page.title} · </span><LinkURL url={page.url} /></> : `页面 #${id}（暂无法读取）`}</li>;
              })}</ul> : <p className="muted">尚未选择页面。可先登记现有页面，再确定此次补充的位置。</p>}
              <button className="ghost" onClick={() => navigate("pages")}>管理目标页面 ↗</button>
              <h4>5 · 行动与内容简报</h4>
              <p className="muted">补齐适用条件、步骤、费用、来源、真实案例和验收方式；简报会带入下方任务的验收方法，确认后保存。</p>
              <OpportunityBrief opportunity={o} questions={questions.data ?? []} pages={pages.data ?? []} onPrepare={prepareTask} />
              {(actions.data ?? []).filter((a) => a.opportunity_id === o.id).map((a) => <p key={a.id}>已关联：{a.title} · {opsLabels[a.status] || a.status} · {a.owner || "未分配负责人"}</p>)}
              <div className="toolbar">
                <button
                  onClick={() => {
                    prepareTask({
                      title: o.title,
                      question_ids: o.question_ids,
                      opportunity_id: o.id,
                      page_id: o.page_ids[0],
                      target_page:
                        pages.data?.find((p) => p.id === o.page_ids[0])?.url ??
                        "",
                    });
                  }}
                >
                  直接填写行动任务
                </button>
              </div>
              <Form
                title="关联已有任务"
                fields={[
                  {
                    key: "action_id",
                    label: "选择任务",
                    type: "number",
                    required: true,
                    options: (actions.data ?? []).map((a) => ({
                      value: String(a.id),
                      label: a.title,
                    })),
                  },
                ]}
                submit="关联机会"
                onSubmit={async (body) => {
                  await api(`actions/${body.action_id}`, "PATCH", {
                    opportunity_id: o.id,
                  });
                  refresh();
                }}
              />
              <Form
                title="编辑机会与依据"
                fields={fields}
                initial={{
                  ...o,
                  evidence_url: o.evidence[0]?.url ?? "",
                  evidence_quote: o.evidence[0]?.quote ?? "",
                }}
                submit="保存机会"
                onSubmit={(body) => save(body, o.id)}
              />
            </article>
          ))}
      </Load>
      <Form
        title="新增业务问题与机会"
        fields={fields}
        initial={{ business_value: 3, business_fit: 3 }}
        submit="保存真实机会"
        onSubmit={(body) => save(body)}
      />
      <div id="opportunity-actions">
        <Actions
          key={JSON.stringify(preset)}
          projectId={projectId}
          batches={batches.data ?? []}
          revision={revision}
          refresh={refresh}
          mode="tasks"
          initialTask={preset}
        />
      </div>
    </>
  );
}
