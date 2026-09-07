"use client";
import { useState } from "react";
import {
  Action,
  api,
  Empty,
  Form,
  Load,
  useData,
  Json,
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
export function Opportunities({
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
  const fields: Field[] = [
    { key: "title", label: "业务问题 / 机会标题", required: true },
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
      type: "number",
      required: true,
    },
    {
      key: "business_fit",
      label: "业务适配（人工判断 1–5）",
      type: "number",
      required: true,
    },
    {
      key: "question_ids",
      label: "目标问题",
      type: "ids",
      multiple: true,
      options: (questions.data ?? []).map((q) => ({
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
  const save = async (body: Row, id?: number) => {
    const { evidence_url, evidence_quote, ...rest } = body;
    if (rest.business_value > 5 || rest.business_fit > 5)
      throw Error("价值与适配只能为1–5。");
    await api(
      id ? `opportunities/${id}` : `projects/${projectId}/opportunities`,
      id ? "PATCH" : "POST",
      {
        ...rest,
        evidence:
          evidence_url || evidence_quote
            ? [{ url: evidence_url, quote: evidence_quote }]
            : [],
      },
    );
    refresh();
  };
  return (
    <>
      <p className="notice">
        业务问题地图用于理解用户决策，不是虚构搜索量榜单。价值和适配由运营人员判断，证据与假设明确区分。
      </p>
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
        {state.data
          ?.filter((o) => !stage || o.decision_stage === stage)
          .map((o) => (
            <article key={o.id} className="work-item">
              <p className="eyebrow">
                {opsLabels[o.decision_stage]} / {opsLabels[o.priority]}优先级 /{" "}
                {opsLabels[o.basis]}
              </p>
              <h3>{o.title}</h3>
              <p>{o.content_gap}</p>
              <p className="muted">
                价值 {o.business_value}/5 · 适配 {o.business_fit}/5 ·{" "}
                {opsLabels[o.status]}
              </p>
              {o.hypothesis && <p className="notice">假设：{o.hypothesis}</p>}
              {o.evidence.map((e, i) => (
                <figure className="evidence-notes" key={i}>
                  <blockquote>{e.quote}</blockquote>
                  <figcaption>
                    <a href={e.url} target="_blank" rel="noreferrer">
                      {e.url}
                    </a>
                  </figcaption>
                </figure>
              ))}
              <div className="toolbar">
                <button
                  onClick={() => {
                    setPreset({
                      title: o.title,
                      question_ids: o.question_ids,
                      opportunity_id: o.id,
                      page_id: o.page_ids[0],
                      target_page:
                        pages.data?.find((p) => p.id === o.page_ids[0])?.url ??
                        "",
                    });
                    requestAnimationFrame(() =>
                      document
                        .getElementById("opportunity-actions")
                        ?.scrollIntoView({ behavior: "smooth" }),
                    );
                  }}
                >
                  为此机会创建运营任务
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
