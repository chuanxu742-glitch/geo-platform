"use client";
import { useState } from "react";
import {
  Action,
  api,
  Empty,
  Form,
  Json,
  Load,
  useData,
  type Field,
  type Row,
} from "./ui";
import { BatchPicker, rate } from "./answers";
import { statusLabel } from "./types";
import { opsLabels } from "./operations-types";
const actionFields: Field[] = [
  { key: "title", label: "任务标题", required: true },
  { key: "owner", label: "负责人" },
  { key: "due_at", label: "到期时间", type: "datetime-local" },
  { key: "blocked_reason", label: "受阻原因（受阻时必填）", type: "textarea" },
  { key: "target_page", label: "目标页面 URL", type: "url" },
  { key: "question_ids", label: "关联问题 ID", type: "ids" },
  { key: "fact_ids", label: "事实依据 ID", type: "ids" },
  { key: "diagnosis_ids", label: "证据诊断 ID", type: "ids" },
  {
    key: "acceptance_method",
    label: "验收方法（不能承诺排名或因果）",
    type: "textarea",
    required: true,
  },
  {
    key: "status",
    label: "任务状态",
    options: [
      { value: "todo", label: "待办" },
      { value: "in_progress", label: "进行中" },
      { value: "done", label: "完成" },
      { value: "cancelled", label: "取消" },
      { value: "blocked", label: "受阻" },
      { value: "awaiting_review", label: "待审核" },
    ],
  },
];
export function Actions({
  projectId,
  batches,
  revision,
  refresh,
  mode = "all",
  initialTask = {},
}: {
  projectId: number;
  batches: Row[];
  revision: number;
  refresh: () => void;
  mode?: "all" | "tasks" | "contents" | "diagnoses";
  initialTask?: Row;
}) {
  const [batch, setBatch] = useState(""),
    [evidence, setEvidence] = useState<Row>(initialTask);
  const diagnoses = useData(`projects/${projectId}/diagnoses`, revision),
    actions = useData(`projects/${projectId}/actions`, revision),
    contents = useData(`projects/${projectId}/contents`, revision),
    facts = useData(`projects/${projectId}/facts`, revision);
  const questions = useData(`projects/${projectId}/questions`, revision);
  const factOptions = (facts.data ?? []).map((f: Row) => ({
    value: String(f.id),
    label: f.claim,
  }));
  const relationOptions: Record<string, { value: string; label: string }[]> = {
    question_ids: (questions.data ?? []).map((q: Row) => ({
      value: String(q.id),
      label: q.current_version.text,
    })),
    fact_ids: factOptions,
    diagnosis_ids: (diagnoses.data ?? []).map((d: Row) => ({
      value: String(d.id),
      label: d.title,
    })),
  };
  const taskFields = actionFields.map((f) =>
    relationOptions[f.key]
      ? {
          ...f,
          label: f.label.replace(" ID", ""),
          multiple: true,
          options: relationOptions[f.key],
        }
      : f,
  );
  const mutate = async (path: string, method: string, body?: Row) => {
    await api(path, method, body);
    refresh();
  };
  return (
    <>
      {(mode === "all" || mode === "diagnoses") && (
        <>
          <h2>证据诊断</h2>
          <BatchPicker batches={batches} value={batch} onChange={setBatch} />
          {batch && (
            <Action run={() => mutate(`batches/${batch}/diagnose`, "POST")}>
              生成可复核诊断
            </Action>
          )}
          <p className="notice">
            诊断是基于回答证据的工作假设，不是因果结论。请先核验原文，再接受诊断并创建行动。
          </p>
          <Load state={diagnoses}>
            {!diagnoses.data?.length && <Empty />}
            {diagnoses.data?.map((d: Row) => (
              <article className="card" key={d.id}>
                <h3>
                  诊断 #{d.id} · {d.title}
                </h3>
                <p>
                  批次 #{d.batch_id} · 回答 #{d.answer_id} · 复核{" "}
                  {statusLabel[d.review_status] ?? d.review_status}
                </p>
                <p>{d.hypothesis}</p>
                <Json value={d.evidence} title="查看证据片段" />
                <div className="toolbar">
                  {[
                    ["accepted", "接受"],
                    ["rejected", "拒绝"],
                    ["pending", "待复核"],
                  ].map(([value, label]) => (
                    <Action
                      key={value}
                      run={() =>
                        mutate(`diagnoses/${d.id}`, "PATCH", {
                          review_status: value,
                        })
                      }
                    >
                      {label}
                    </Action>
                  ))}
                  <button
                    className="secondary"
                    onClick={() => {
                      setEvidence({ title: d.title, diagnosis_ids: [d.id] });
                      requestAnimationFrame(() =>
                        document
                          .querySelector<HTMLInputElement>(
                            '#create-action input[name="title"]',
                          )
                          ?.focus(),
                      );
                      document
                        .getElementById("create-action")
                        ?.scrollIntoView({ behavior: "smooth" });
                    }}
                  >
                    携此证据创建任务
                  </button>
                </div>
              </article>
            ))}
          </Load>
        </>
      )}
      {(mode === "all" ||
        mode === "tasks" ||
        (mode === "diagnoses" && evidence.diagnosis_ids?.length)) && (
        <>
          <h2>行动任务</h2>
          <Load state={actions}>
            {!actions.data?.length && <Empty />}
            {actions.data?.map((a: Row) => (
              <details className="card" key={a.id} open>
                <summary>
                  任务 #{a.id} · {a.title} · {opsLabels[a.status] ?? a.status} ·{" "}
                  {a.owner || "未分配"}
                </summary>
                <small>
                  到期：
                  {a.due_at
                    ? new Date(a.due_at).toLocaleString("zh-CN")
                    : "未安排"}
                  {a.blocked_reason ? ` · 受阻：${a.blocked_reason}` : ""}
                </small>
                <p className="task-acceptance">
                  <span className="workflow-label">验收依据 / </span>
                  {a.acceptance_method}
                </p>
                <Form
                  title="编辑任务"
                  fields={taskFields}
                  initial={a}
                  submit="保存任务"
                  onSubmit={(body) => mutate(`actions/${a.id}`, "PATCH", body)}
                />
                <Action danger run={() => mutate(`actions/${a.id}`, "DELETE")}>
                  删除任务
                </Action>
              </details>
            ))}
          </Load>
          <div id="create-action">
            {/* Mount defaults only after relation options exist, so preset IDs stay selected. */}
            <Load state={questions}><Load state={facts}><Load state={diagnoses}>
            {questions.data && facts.data && diagnoses.data && <Form
              key={JSON.stringify(evidence)}
              title="创建证据驱动任务"
              expanded={Boolean(
                evidence.diagnosis_ids?.length ||
                evidence.opportunity_id ||
                evidence.finding_id,
              )}
              fields={taskFields.map((field) =>
                (evidence.opportunity_id || evidence.page_id || evidence.finding_id) &&
                ["owner", "due_at"].includes(field.key)
                  ? { ...field, required: true }
                  : field,
              )}
              initial={evidence}
              submit="创建任务"
              onSubmit={(body) =>
                mutate(`projects/${projectId}/actions`, "POST", {
                  ...evidence,
                  ...body,
                })
              }
            />}
            </Load></Load></Load>
          </div>
        </>
      )}
      {(mode === "all" || mode === "contents") && (
        <>
          <h2>内容草稿与发布记录</h2>
          <p className="muted">
            内容手动编辑始终可用。每次保存建立不可变版本；记录发布不等于系统代为发布到网站。
          </p>
          <Load state={facts}>
            <details>
              <summary>可用事实 ID 参考</summary>
              {facts.data?.map((f: Row) => (
                <p key={f.id}>
                  #{f.id} · {f.claim}
                </p>
              ))}
            </details>
          </Load>
          <Load state={contents}>
            {!contents.data?.length && <Empty />}
            {contents.data?.map((c: Row) => (
              <details className="card" key={c.id}>
                <summary>
                  内容 #{c.id} · {c.title} · {c.versions?.length ?? 0} 个版本
                </summary>
                {c.versions?.map((v: Row) => (
                  <article className="version" key={v.id}>
                    <h4>
                      版本 v{v.version} · ID #{v.id}
                    </h4>
                    <p>
                      {v.published_at
                        ? `人工发布记录：${v.published_at}（不等于页面核验）`
                        : "尚无人工发布记录"}
                    </p>
                    <pre className="answer-text">{v.after_text}</pre>
                    <Json value={v.facts_snapshot} title="版本事实依据快照" />
                    <Json value={v.before_text} title="修改前内容" />
                  </article>
                ))}
                <Form
                  title="编辑内容元信息"
                  fields={[
                    { key: "title", label: "内容标题", required: true },
                    { key: "target_url", label: "页面 URL", type: "url" },
                  ]}
                  initial={c}
                  submit="保存元信息"
                  onSubmit={(body) => mutate(`contents/${c.id}`, "PATCH", body)}
                />
                <Form
                  title="保存内容新版本"
                  fields={[
                    {
                      key: "before_text",
                      label: "修改前内容",
                      type: "textarea",
                    },
                    {
                      key: "after_text",
                      label: "修改后草稿",
                      type: "textarea",
                      required: true,
                    },
                    {
                      key: "fact_ids",
                      label: "选择引用事实",
                      type: "ids",
                      multiple: true,
                      options: factOptions,
                      required: true,
                    },
                  ]}
                  submit="保存草稿版本"
                  onSubmit={(body) =>
                    mutate(`contents/${c.id}/versions`, "POST", body)
                  }
                />
                <details>
                  <summary>可选：调用模型生成新版本</summary>
                  <p className="notice">
                    需要后端配置 OpenAI-compatible 模型
                    key；未配置时明确不可用。生成稿始终待人工审核，引用片段校验不等于语义保真；不会自动调用或发布。
                  </p>
                  <Form
                    title="模型生成"
                    fields={[
                      {
                        key: "instructions",
                        label: "生成要求",
                        type: "textarea",
                        required: true,
                      },
                      {
                        key: "before_text",
                        label: "当前内容",
                        type: "textarea",
                      },
                      {
                        key: "fact_ids",
                        label: "选择事实依据",
                        type: "ids",
                        multiple: true,
                        options: factOptions,
                        required: true,
                      },
                    ]}
                    submit="显式调用模型生成"
                    onSubmit={(body) =>
                      mutate(`contents/${c.id}/generate`, "POST", body)
                    }
                  />
                </details>
                <Action danger run={() => mutate(`contents/${c.id}`, "DELETE")}>
                  删除内容
                </Action>
              </details>
            ))}
          </Load>
          <Form
            title="新建内容"
            fields={[
              { key: "title", label: "内容标题", required: true },
              { key: "target_url", label: "目标页面 URL", type: "url" },
              {
                key: "action_id",
                label: "关联任务",
                type: "number",
                options: [
                  { value: "", label: "不关联" },
                  ...(actions.data ?? []).map((a: Row) => ({
                    value: String(a.id),
                    label: a.title,
                  })),
                ],
              },
            ]}
            submit="创建内容"
            onSubmit={(body) =>
              mutate(`projects/${projectId}/contents`, "POST", body)
            }
          />
        </>
      )}
    </>
  );
}
export function Retest({
  projectId,
  batches,
  revision,
  refresh,
  onBatch,
}: {
  projectId: number;
  batches: Row[];
  revision: number;
  refresh: () => void;
  onBatch: (id: number) => void;
}) {
  const [baseline, setBaseline] = useState(""),
    [retest, setRetest] = useState("");
  const state = useData(retest ? `batches/${retest}/compare` : null, revision);
  const actions = useData(`projects/${projectId}/actions`, revision);
  const contents = useData(`projects/${projectId}/contents`, revision);
  return (
    <>
      <p className="notice">
        复测复用基线冻结的问题版本、来源与采样条件；保留对照组。两批差异只描述观察，不证明行动产生效果，不保证品牌排名。
      </p>
      {!batches.some((b) => b.baseline_batch_id) && (
        <Empty>
          还没有复测报告。先选择已完成观察的基线，建立相同条件的第二批回答。
        </Empty>
      )}
      <h2>两批对比</h2>
      <BatchPicker
        batches={batches.filter((b) => b.baseline_batch_id)}
        value={retest}
        onChange={setRetest}
      />
      <Load state={state}>
        {state.data && (
          <section className="card">
            <h3>
              基线 #{state.data.baseline_batch_id} → 复测 #
              {state.data.retest_batch_id}
            </h3>
            <p>
              条件匹配：{state.data.conditions_match ? "是" : "否"} · 可比较：
              {state.data.comparable ? "是" : "否"} · 不作因果宣称
            </p>
            {state.data.warnings?.map((w: string, i: number) => (
              <p className="notice" key={i}>
                {w}
              </p>
            ))}
            {state.data.groups?.map((g: Row) => (
              <section key={String(g.branded)}>
                <h3>{g.branded ? "带品牌" : "不带品牌"}</h3>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>指标</th>
                        <th>基线</th>
                        <th>复测</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[
                        ["sample_count", "原始样本"],
                        ["valid_count", "有效回答"],
                        ["invalid_count", "无效回答"],
                        ["unknown_count", "有效性未知"],
                        ["mention_rate", "品牌提及率"],
                        ["recommendation_rate", "明确推荐率"],
                        ["recommendation_unknown_count", "推荐未知"],
                        ["factual_error_rate", "事实错误率"],
                        ["factual_unknown_count", "事实未知"],
                        ["source_unknown_count", "引用未知"],
                      ].map(([key, label]) => (
                        <tr key={key}>
                          <th>{label}</th>
                          <td>
                            {key.endsWith("rate")
                              ? rate(g.baseline?.[key])
                              : (g.baseline?.[key] ?? "未知")}
                          </td>
                          <td>
                            {key.endsWith("rate")
                              ? rate(g.retest?.[key])
                              : (g.retest?.[key] ?? "未知")}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p>
                  提及率差（百分点）：
                  {g.mention_rate_delta == null
                    ? "未知"
                    : (g.mention_rate_delta * 100).toFixed(1)}{" "}
                  · 推荐率差（百分点）：
                  {g.recommendation_rate_delta == null
                    ? "未知"
                    : (g.recommendation_rate_delta * 100).toFixed(1)}
                </p>
                <Json value={g.uncertainty} title="不确定性区间与局限" />
                <Json
                  value={{ baseline: g.baseline, retest: g.retest }}
                  title="两批指标分母与样本 ID"
                />
              </section>
            ))}
            <h3>保留对照组</h3>
            <p>
              对照问题 ID：
              {state.data.control_question_ids?.join(", ") ||
                "基线未指定对照问题；请谨慎解释差异。"}
            </p>
            <Json
              value={state.data.control_groups}
              title="对照组样本、指标与不确定性"
            />
          </section>
        )}
      </Load>
      <h2>从基线创建匹配复测</h2>
      <BatchPicker batches={batches} value={baseline} onChange={setBaseline} />
      {baseline && (
        <Form
          key={baseline}
          title={`基线 #${baseline} 的复测`}
          fields={[
            { key: "name", label: "复测批次名称", required: true },
            {
              key: "action_ids",
              label: "关联行动任务",
              type: "ids",
              multiple: true,
              options: (actions.data ?? []).map((a: Row) => ({
                value: String(a.id),
                label: a.title,
              })),
            },
            {
              key: "content_version_ids",
              label: "关联内容版本",
              type: "ids",
              multiple: true,
              options: (contents.data ?? []).flatMap((c: Row) =>
                (c.versions ?? []).map((v: Row) => ({
                  value: String(v.id),
                  label: `${c.title} · v${v.version} · ${v.published_at ? "已登记发布" : "草稿"}`,
                })),
              ),
            },
          ]}
          submit="创建匹配复测并导入第二批"
          onSubmit={async (body) => {
            const b = await api(`projects/${projectId}/batches`, "POST", {
              ...body,
              baseline_batch_id: Number(baseline),
            });
            refresh();
            onBatch(b.id);
          }}
        />
      )}
    </>
  );
}
