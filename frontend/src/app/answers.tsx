"use client";
import { useState } from "react";
import {
  Action,
  api,
  Empty,
  Form,
  Json,
  LinkURL,
  Load,
  useData,
  type Row,
} from "./ui";
import { statusLabel, type Answer, type Batch } from "./types";
import { Prelude } from "./visual";
export const rate = (value: unknown) =>
  typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "未知";
type QuoteEvidence = { start: number; end: number; quote: string };
function EvidenceQuotes({
  title,
  items,
}: {
  title: string;
  items: QuoteEvidence[];
}) {
  return (
    <section className="evidence-notes">
      <h4>{title}</h4>
      {items.length ? (
        items.map((item, i) => (
          <figure key={i}>
            <blockquote>{item.quote}</blockquote>
            <figcaption>
              原文字符 {item.start}–{item.end} · Unicode 码点 · 右边界不含
            </figcaption>
          </figure>
        ))
      ) : (
        <p className="muted">
          本版本没有可展示的证据片段；不代表已作出否定判断。
        </p>
      )}
    </section>
  );
}
export function BatchPicker({
  batches,
  value,
  onChange,
  optional = false,
}: {
  batches: Row[];
  value: string;
  onChange: (value: string) => void;
  optional?: boolean;
}) {
  return (
    <label className="picker">
      批次
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">{optional ? "全部批次" : "请选择批次"}</option>
        {batches.map((b) => (
          <option key={b.id} value={b.id}>
            #{b.id} {b.name} · {b.status}
          </option>
        ))}
      </select>
    </label>
  );
}
const recommendationLabels: Record<string, string> = {
  recommended: "明确推荐",
  not_recommended: "明确不建议",
  neutral: "中性 / 未明确推荐",
  unknown: "无法判断",
};
export function AnswerDetail({
  id,
  revision,
}: {
  id: number;
  revision: number;
}) {
  const state = useData<Answer & { analyses: Row[] }>(
    `answers/${id}`,
    revision,
  );
  return (
    <Load state={state}>
      {state.data && (
        <article className="answer-detail">
          <h3>回答 #{id}</h3>
          <p>
            <b>{state.data.platform}</b> · 任务 {state.data.task_status} ·
            回答有效性 <strong>{statusLabel[state.data.validity]}</strong> ·
            完整性 {state.data.complete ? "已确认完整" : "未确认完整"}
          </p>
          {state.data.invalid_reason && (
            <p className="notice">{state.data.invalid_reason}</p>
          )}
          <h4>不可变回答原文</h4>
          <pre className="answer-text">
            {state.data.text || "（没有回答原文）"}
          </pre>
          <h4>引用来源</h4>
          {state.data.sources == null ? (
            <p>未知：未提供引用信息，不能记为零。</p>
          ) : state.data.sources.length === 0 ? (
            <p>已观察：无引用。</p>
          ) : (
            <ul>
              {state.data.sources.map((s: Row, i: number) => (
                <li key={i}>
                  {s.title && <span>{s.title} · </span>}
                  <LinkURL url={s.url} />
                </li>
              ))}
            </ul>
          )}
          <h4>分析版本与证据</h4>
          {!state.data.analyses?.length && (
            <Empty>尚未分析。请显式运行规则或模型分析。</Empty>
          )}
          {state.data.analyses?.map((a: Row) => (
            <details key={a.id} className="card">
              <summary>
                分析 v{a.version} · 提及{" "}
                {a.brand_mentioned == null
                  ? "未知"
                  : a.brand_mentioned
                    ? "是"
                    : "否"}{" "}
                · 推荐 {recommendationLabels[a.recommendation] ?? "无法判断"} ·
                事实 {statusLabel[a.factual_status] ?? a.factual_status}
              </summary>
              <p>
                模型状态：{a.model_status}。证据位置按 Unicode
                码点计数，以下直接显示后端核验的 quote。
              </p>
              <EvidenceQuotes
                title="品牌证据片段"
                items={a.brand_evidence ?? []}
              />
              {(a.competitor_evidence ?? []).map((competitor: Row) => (
                <EvidenceQuotes
                  key={competitor.name}
                  title={`竞品 · ${competitor.name}`}
                  items={competitor.evidence ?? []}
                />
              ))}
              <h4>事实核验与依据</h4>
              {!a.factual_findings?.length && (
                <p className="muted">
                  本版本没有事实核验发现；无模型时保留未知。
                </p>
              )}
              {(a.factual_findings ?? []).map((finding: Row, index: number) => (
                <div key={index} className="fact-finding">
                  <EvidenceQuotes
                    title={`事实 #${finding.fact_id} · ${statusLabel[finding.status] ?? finding.status}`}
                    items={finding.evidence ? [finding.evidence] : []}
                  />
                  <p>{finding.explanation}</p>
                </div>
              ))}
              <Json value={a} title="高级：完整分析记录与输入依据" />
            </details>
          ))}
          <Json
            value={state.data.raw}
            title="原始记录与 source / lineage 追溯"
          />
        </article>
      )}
    </Load>
  );
}
export function Overview({
  projectId,
  batches,
  revision,
  openAnswer,
  onStart,
}: {
  projectId: number;
  batches: Row[];
  revision: number;
  openAnswer: (id: number) => void;
  onStart: () => void;
}) {
  const [batch, setBatch] = useState(""),
    [filters, setFilters] = useState<Record<string, string>>({
      platform: "",
      region: "",
      intent: "",
    }),
    [drill, setDrill] = useState<Row | null>(null);
  const query = new URLSearchParams(
    Object.entries({ batch_id: batch, ...filters }).filter(([, v]) => v),
  );
  const state = useData(`projects/${projectId}/overview?${query}`, revision);
  if (
    !state.loading &&
    !state.error &&
    !batch &&
    !Object.values(filters).some(Boolean) &&
    !state.data?.groups?.some((g: Row) => g.sample_count > 0)
  ) {
    return (
      <Prelude
        compact
        title="档案已建立，等待第一批真实回答。"
        action={<button onClick={onStart}>建立问题与采集批次 ↗</button>}
      >
        先定义想观察的问题，再保存完整回答。这里仅呈现实际样本，不预设可见性分数。
      </Prelude>
    );
  }
  return (
    <>
      <div className="filters">
        <BatchPicker
          batches={batches}
          value={batch}
          onChange={(v) => {
            setBatch(v);
            setDrill(null);
          }}
          optional
        />
        {(["platform", "region", "intent"] as const).map((key, i) => (
          <label key={key}>
            {["平台", "地区", "意图"][i]}
            <select
              value={filters[key]}
              onChange={(e) => {
                setFilters({ ...filters, [key]: e.target.value });
                setDrill(null);
              }}
            >
              <option value="">全部</option>
              {(
                state.data?.filters?.[`${key}s`] ??
                (filters[key] ? [filters[key]] : [])
              ).map((v: string) => (
                <option key={v} value={v}>
                  {v || "未标注"}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
      <p className="notice">
        当前
        {filters.platform
          ? `平台：${filters.platform}`
          : "汇总全部平台（混合样本）"}
        。带品牌与不带品牌问题分别计算。有效回答≠任务完成；未知不计为零。点击指标查看命中、分母和未知回答。
      </p>
      <Load state={state}>
        {!state.data?.groups?.length && <Empty />}
        {state.data?.groups?.map((g: Row) => (
          <section key={String(g.branded)} className="observation-group">
            <h2>{g.branded ? "带品牌问题" : "不带品牌问题"}</h2>
            <p className="sample-composition">
              原始样本 {g.sample_count} · 有效 {g.valid_count} · 无效{" "}
              {g.invalid_count} · 有效性未知 {g.unknown_count} · 已分析{" "}
              {g.analyzed_count}
            </p>
            <div className="metrics">
              {[
                {
                  key: "brand_mentions",
                  label: "品牌提及",
                  value: rate(g.mention_rate),
                  count: g.brand_mentions,
                  denominator: g.mention_denominator,
                },
                {
                  key: "recommendation",
                  label: "明确推荐",
                  value: rate(g.recommendation_rate),
                  count: g.recommended_count,
                  denominator: g.recommendation_denominator,
                  unknown: g.recommendation_unknown_count,
                },
                {
                  key: "factual",
                  label: "事实错误",
                  value: rate(g.factual_error_rate),
                  count: g.factual_error_count,
                  denominator: g.factual_denominator,
                  unknown: g.factual_unknown_count,
                },
                {
                  key: "sources",
                  label: "引用信息已知",
                  value: g.source_known_count ?? "未知",
                  unknown: g.source_unknown_count,
                },
                {
                  key: "rank",
                  label: "明确排名均值",
                  value:
                    g.rank_mean == null
                      ? "未知"
                      : Number(g.rank_mean).toFixed(1),
                  denominator: g.rank_denominator,
                },
              ].map((m) => (
                <button
                  className={`metric ${m.value === "未知" ? "is-unknown" : ""}`}
                  key={m.key}
                  onClick={() =>
                    setDrill({
                      title: `${g.branded ? "带品牌" : "不带品牌"} · ${m.label}`,
                      ...(g.metrics?.[m.key] ?? {}),
                    })
                  }
                >
                  <span>{m.label}</span>
                  <strong>{m.value}</strong>
                  <small>
                    {m.count != null ? `命中 ${m.count} / ` : ""}
                    {m.denominator != null ? `分母 ${m.denominator}` : ""}
                    {m.unknown != null ? ` · 未知 ${m.unknown}` : ""}
                  </small>
                  <span className="metric-rule" aria-hidden="true" />
                </button>
              ))}
            </div>
            <p className="recommendation-summary">
              明确不建议：{g.not_recommended_count ?? "未知"} · 中性 /
              未明确推荐：{g.neutral_count ?? "未知"} · 无法判断：
              {g.recommendation_unknown_count ?? "未知"}
            </p>
            {g.competitors?.map((c: Row) => (
              <button
                className="secondary"
                key={c.name}
                onClick={() => setDrill({ title: `竞品 ${c.name} 推荐`, ...c })}
              >
                {c.name} 推荐 {rate(c.recommendation_rate)} ·{" "}
                {c.recommended_count}/{c.denominator} · 未知 {c.unknown_count}
              </button>
            ))}
          </section>
        ))}
      </Load>
      {drill && (
        <section className="card">
          <h2>{drill.title} · 样本明细</h2>
          {[
            ["answer_ids", "指标命中"],
            ["denominator_answer_ids", "指标分母"],
            ["unknown_answer_ids", "未知样本"],
          ].map(([key, label]) => (
            <div key={key}>
              <h3>{label}</h3>
              {!drill[key]?.length ? (
                <p>无记录</p>
              ) : (
                drill[key].map((id: number) => (
                  <button
                    className="secondary"
                    key={id}
                    onClick={() => openAnswer(id)}
                  >
                    回答 #{id}
                  </button>
                ))
              )}
            </div>
          ))}
        </section>
      )}
    </>
  );
}
export function Answers({
  batches,
  batchId,
  setBatchId,
  revision,
  refresh,
  answerId,
  setAnswerId,
}: {
  batches: Row[];
  batchId: string;
  setBatchId: (id: string) => void;
  revision: number;
  refresh: () => void;
  answerId: number | null;
  setAnswerId: (id: number | null) => void;
}) {
  const state = useData<Batch>(batchId ? `batches/${batchId}` : null, revision),
    [status, setStatus] = useState("");
  const [currentAliases, setCurrentAliases] = useState(false);
  const run = async (operation: string, body?: Row) => {
    await api(`batches/${batchId}/${operation}`, "POST", body);
    refresh();
  };
  return (
    <>
      <BatchPicker
        batches={batches}
        value={batchId}
        onChange={(id) => {
          setBatchId(id);
          setAnswerId(null);
        }}
      />
      {!batchId && (
        <Empty>在问题库创建批次后，在此人工导入回答或明确触发已有采集。</Empty>
      )}
      <Load state={state}>
        {state.data && (
          <>
            <section className="card">
              <h2>
                {state.data.name} · {state.data.status}
              </h2>
              <label>
                <span>使用当前品牌别名重算（保留旧版本）</span>
                <input
                  type="checkbox"
                  checked={currentAliases}
                  onChange={(event) => setCurrentAliases(event.target.checked)}
                />
              </label>
              <div className="toolbar">
                <Action run={() => run("collect")}>触发 Razormind 采集</Action>
                <Action run={() => run("sync")}>同步远端状态与记录</Action>
                <Action
                  run={() =>
                    run("analyze", {
                      use_model: false,
                      use_current_aliases: currentAliases,
                    })
                  }
                >
                  运行规则分析 / 新版本
                </Action>
                <Action
                  run={() =>
                    run("analyze", {
                      use_model: true,
                      use_current_aliases: currentAliases,
                    })
                  }
                >
                  运行模型分析 / 新版本
                </Action>
              </div>
              <p className="muted">
                所有调用均需明确点击。未配置模型时返回不可用，不伪造语义结论。采集任务完成不代表回答有效；不确定提交请先核查远端，勿盲目重试。
              </p>
              <Json
                value={state.data.jobs}
                title="采集任务状态 / 错误 / 远端任务 ID"
              />
              <Json
                value={state.data.snapshot}
                title="冻结的问题、事实和采样条件"
              />
            </section>
            <Form
              key={batchId}
              title="人工导入真实回答原文"
              fields={[
                {
                  key: "question_version_id",
                  label: "冻结问题版本",
                  required: true,
                  options: (state.data.snapshot?.questions ?? []).map(
                    (q: Row) => ({
                      value: String(q.id),
                      label: `版本 #${q.id} · ${q.text}`,
                    }),
                  ),
                },
                {
                  key: "platform",
                  label: "回答平台",
                  required: true,
                  options: (
                    state.data.snapshot?.sampling?.platforms ??
                    state.data.snapshot?.sources?.map((s: Row) => s.platform) ??
                    []
                  ).map((p: string) => ({ value: p, label: p })),
                },
                {
                  key: "text",
                  label: "回答原文（保存后不可修改）",
                  type: "textarea",
                  required: true,
                },
                {
                  key: "observed_at",
                  label: "实际回答观察时间（实验需要；不等同导入时间）",
                  type: "datetime-local",
                  hint: "按本地时间输入并转换UTC。无法确认时可留空，但不能用于要求时间窗口的实验结论。",
                },
                {
                  key: "task_status",
                  label: "任务状态",
                  options: [
                    { value: "completed", label: "已完成" },
                    { value: "failed", label: "失败" },
                    { value: "pending", label: "等待中" },
                  ],
                },
                {
                  key: "validity",
                  label: "回答有效性",
                  options: [
                    { value: "unknown", label: "未知（默认）" },
                    {
                      value: "valid",
                      label: "有效（须完整且非系统/错误文本）",
                    },
                    { value: "invalid", label: "无效" },
                  ],
                },
                {
                  key: "complete",
                  label: "我确认已复制完整回答（默认不确认）",
                  type: "checkbox",
                },
                { key: "invalid_reason", label: "无效原因 / 说明" },
                {
                  key: "sources_known",
                  label:
                    "已核对引用信息（未勾选=未知；勾选且下方为空=观察到无引用）",
                  type: "checkbox",
                },
                {
                  key: "source_urls",
                  label: "引用 URL（逗号或换行分隔）",
                  type: "list",
                },
              ]}
              submit="永久保存原文"
              onSubmit={async (body) => {
                const { sources_known, source_urls, ...answer } = body;
                if (answer.validity === "valid" && !answer.complete)
                  throw new Error("有效回答必须显式确认完整性。");
                if (
                  source_urls.some((url: string) => !/^https?:\/\//i.test(url))
                )
                  throw new Error("引用必须为 http(s) URL。");
                if (!sources_known && source_urls.length)
                  throw new Error("填写引用后请勾选已核对引用信息。");
                const imported = await api(
                  `batches/${batchId}/import`,
                  "POST",
                  {
                    answers: [
                      {
                        ...answer,
                        question_version_id: Number(answer.question_version_id),
                        ...(sources_known
                          ? {
                              sources: source_urls.map((url: string) => ({
                                url,
                                type: "reported",
                              })),
                            }
                          : {}),
                      },
                    ],
                  },
                );
                refresh();
                setAnswerId(imported[0]?.id ?? null);
              }}
            />
            <div className="answer-reading-grid">
              <div className="answer-list">
                <h2>批次回答</h2>
                <label className="picker">
                  有效性筛选
                  <select
                    value={status}
                    onChange={(e) => setStatus(e.target.value)}
                  >
                    <option value="">全部</option>
                    <option value="valid">有效</option>
                    <option value="invalid">无效</option>
                    <option value="unknown">未知</option>
                  </select>
                </label>
                {!state.data.answers?.length && <Empty />}
                {state.data.answers
                  ?.filter((a: Row) => !status || a.validity === status)
                  .map((a: Row) => (
                    <button
                      className={`answer-row ${answerId === a.id ? "selected" : ""}`}
                      key={a.id}
                      onClick={() => setAnswerId(a.id)}
                    >
                      <b>
                        #{a.id} · {a.platform} ·{" "}
                        {statusLabel[a.validity] ?? a.validity}
                      </b>
                      <span>{a.text?.slice(0, 160) || "（无原文）"}</span>
                      <small>
                        问题版本 #{a.question_version_id} · 任务 {a.task_status}
                      </small>
                    </button>
                  ))}
              </div>
              {answerId ? (
                <AnswerDetail id={answerId} revision={revision} />
              ) : (
                <Empty>选择一条回答，阅读不可变原文与分析证据。</Empty>
              )}
            </div>
          </>
        )}
      </Load>
      {!batchId && answerId && (
        <AnswerDetail id={answerId} revision={revision} />
      )}
    </>
  );
}
