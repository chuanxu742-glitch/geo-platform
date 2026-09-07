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
import type { Batch } from "./types";
import {
  opsLabels,
  type OpsContext,
  type ResearchSourceSnapshot,
  type Research,
  type Experiment,
  type OperatingRule,
  type SitePage,
  type Content,
} from "./operations-types";
function ExperimentRecord({ id, revision }: { id: number; revision: number }) {
  const state = useData<Experiment>(`experiments/${id}`, revision);
  return (
    <Load state={state}>
      {state.data && (
        <>
          <Json
            value={state.data.conclusion_gate}
            title="结论证据门禁：支持 / 反驳所缺条件"
          />
          <Json
            value={
              state.data.evidence_snapshot ??
              state.data.compare_snapshot ??
              state.data.comparison
            }
            title="冻结比较、分析版本、处理组与对照证据"
          />
          <Json value={state.data} title="高级：完整实验档案" />
        </>
      )}
    </Load>
  );
}
function ResearchHistory({ id, revision }: { id: number; revision: number }) {
  const state = useData<Research>(`research/${id}`, revision);
  return (
    <Load state={state}>
      <Json
        value={state.data?.revisions}
        title="研究主张的不可变修订与审阅记录"
      />
    </Load>
  );
}
export function ResearchOperations({
  projectId,
  revision,
  refresh,
  navigate,
}: OpsContext) {
  const research = useData<Research[]>(
      `projects/${projectId}/research`,
      revision,
    ),
    experiments = useData<Experiment[]>(
      `projects/${projectId}/experiments`,
      revision,
    ),
    rules = useData<OperatingRule[]>(
      `projects/${projectId}/operations/rules`,
      revision,
    ),
    pages = useData<SitePage[]>(`projects/${projectId}/pages`, revision),
    contents = useData<Content[]>(`projects/${projectId}/contents`, revision),
    batches = useData<Batch[]>(`projects/${projectId}/batches`, revision);
  const sources = useData<ResearchSourceSnapshot[]>(
    `projects/${projectId}/research-sources`,
    revision,
  );
  const [evidenceBatch, setEvidenceBatch] = useState(""),
    [experimentId, setExperimentId] = useState<number | null>(null);
  const batch = useData<Batch>(
    evidenceBatch ? `batches/${evidenceBatch}` : null,
    revision,
  );
  const versions = (contents.data ?? []).flatMap((c) =>
    c.versions.map((v) => ({ ...v, title: `${c.title} · v${v.version}` })),
  );
  const fields: Field[] = [
    { key: "platform", label: "平台", required: true },
    { key: "channel", label: "渠道", required: true },
    { key: "mode", label: "模式", required: true },
    { key: "scenario", label: "适用场景", required: true },
    { key: "source_type", label: "信源类型", required: true },
    {
      key: "claim",
      label: "研究主张（不是平台算法定律）",
      type: "textarea",
      required: true,
    },
    {
      key: "status",
      label: "当前证据状态",
      options: ["hypothesis", "supported", "inconclusive", "refuted"].map(
        (value) => ({ value, label: opsLabels[value] }),
      ),
    },
    { key: "conditions", label: "适用条件", type: "textarea", required: true },
    {
      key: "limitations",
      label: "局限与不可外推范围",
      type: "textarea",
      required: true,
    },
    {
      key: "research_source_id",
      label: "引用已抓取外部研究来源",
      type: "number",
      options: [
        { value: "", label: "不引用外部来源" },
        ...(sources.data ?? [])
          .filter((s) => s.status === "success")
          .map((s) => ({
            value: String(s.id),
            label: `${s.title || s.url} · ${new Date(s.created_at).toLocaleString("zh-CN")}`,
          })),
      ],
    },
    { key: "evidence_url", label: "来源 URL", type: "url" },
    { key: "evidence_quote", label: "精确证据摘录", type: "textarea" },
    {
      key: "answer_id",
      label: "引用有效回答（来自下方所选批次）",
      type: "number",
      options: [
        { value: "", label: "不引用回答" },
        ...(batch.data?.answers ?? [])
          .filter((a) => a.validity === "valid")
          .map((a) => ({
            value: String(a.id),
            label: `${a.platform} · ${a.text.slice(0, 100)}`,
          })),
      ],
    },
    {
      key: "snapshot_id",
      label: "引用HTTP成功页面快照",
      type: "number",
      options: [
        { value: "", label: "不引用页面快照" },
        ...(pages.data ?? [])
          .filter(
            (p) =>
              p.latest_snapshot?.source_kind === "http" &&
              p.latest_snapshot.status === "success",
          )
          .map((p) => ({
            value: String(p.latest_snapshot!.id),
            label: `${p.title || p.url} · ${new Date(p.latest_snapshot!.created_at).toLocaleString("zh-CN")}`,
          })),
      ],
    },
    { key: "reviewer", label: "证据审阅人（非假设必填）" },
    { key: "review_note", label: "审阅说明（非假设必填）", type: "textarea" },
  ];
  const mutate = async (path: string, body: Row, method = "POST") => {
    const r = await api(path, method, body);
    refresh();
    return r;
  };
  const saveResearch = async (body: Row, id?: number) => {
    const {
      evidence_url,
      evidence_quote,
      answer_id,
      snapshot_id,
      research_source_id,
      ...rest
    } = body;
    return mutate(
      id ? `research/${id}` : `projects/${projectId}/research`,
      {
        ...rest,
        evidence:
          evidence_url ||
          evidence_quote ||
          answer_id ||
          snapshot_id ||
          research_source_id
            ? [
                {
                  url: evidence_url,
                  quote: evidence_quote,
                  ...(answer_id ? { answer_id } : {}),
                  ...(snapshot_id ? { snapshot_id } : {}),
                  ...(research_source_id ? { research_source_id } : {}),
                },
              ]
            : [],
      },
      id ? "PATCH" : "POST",
    );
  };
  return (
    <>
      <p className="notice">
        研究要转为可复用的运营经验，必须有可追溯证据与适用边界。不绘制虚构算法权重；页面正文已核验不等于
        AI 已引用。支持 /
        反驳需要实际有效回答或HTTP页面证据，URL或人工导入本身不够。
      </p>
      <details className="card">
        <summary>外部官方来源：明确抓取并保留可核验证据</summary>
        <p className="notice">
          会访问你输入的公开URL并保存不可变正文。来源内容不自动成为平台规律；引用必须精确且保留条件与局限。
        </p>
        <Form
          title="抓取一份外部研究来源"
          fields={[
            {
              key: "url",
              label: "官方文档 / 公开研究来源 URL",
              type: "url",
              required: true,
            },
          ]}
          submit="明确访问并保存来源快照"
          onSubmit={(body) =>
            mutate(`projects/${projectId}/research-sources/fetch`, body)
          }
        />
        <Load state={sources}>
          {sources.data?.map((s) => (
            <article className="margin-note" key={s.id}>
              <h3>{s.title || s.url}</h3>
              <a href={s.final_url || s.url} target="_blank" rel="noreferrer">
                {s.final_url || s.url}
              </a>
              <p>
                {opsLabels[s.status] ?? s.status} · HTTP{" "}
                {s.http_status ?? "未知"}
              </p>
              {s.error && (
                <p className="error" role="alert">
                  {s.error}
                </p>
              )}
              <details>
                <summary>阅读已保存的来源正文</summary>
                <pre className="answer-text">
                  {s.visible_text || "没有可核验正文"}
                </pre>
              </details>
            </article>
          ))}
        </Load>
      </details>
      <div className="section-toolbar">
        <h2>平台与渠道研究</h2>
        <button className="secondary" onClick={() => navigate("observation")}>
          采集证据与验收 ↗
        </button>
      </div>
      <label className="picker">
        为研究选择回答证据批次
        <select
          value={evidenceBatch}
          onChange={(e) => setEvidenceBatch(e.target.value)}
        >
          <option value="">不使用回答证据</option>
          {batches.data?.map((b) => (
            <option key={b.id} value={b.id}>
              {b.name}
            </option>
          ))}
        </select>
      </label>
      <Load state={research}>
        {!research.data?.length && (
          <Empty>
            先记录一个明确范围的假设，再用原始回答或抓取快照检验。没有证据时不升级为经验规则。
          </Empty>
        )}
        {research.data?.map((r) => (
          <article className="research-note" key={r.id}>
            <p className="eyebrow">
              {r.platform} / {r.channel} / {opsLabels[r.status]}
            </p>
            <h3>{r.claim}</h3>
            <p>
              {r.scenario} · {r.mode}
            </p>
            <dl className="readable-dl">
              <dt>适用条件</dt>
              <dd>{r.conditions}</dd>
              <dt>局限</dt>
              <dd>{r.limitations}</dd>
              <dt>审阅</dt>
              <dd>
                {r.reviewer || "待审阅"} · {r.review_note || "未填写"}
              </dd>
            </dl>
            {r.evidence.map((e, i) => (
              <figure className="evidence-notes" key={i}>
                <blockquote>{e.quote}</blockquote>
                <figcaption>
                  {e.url && (
                    <a href={e.url} target="_blank" rel="noreferrer">
                      {e.url}
                    </a>
                  )}
                </figcaption>
              </figure>
            ))}
            <Form
              title="修订研究主张与证据状态"
              fields={fields}
              initial={{
                ...r,
                evidence_url: r.evidence[0]?.url ?? "",
                evidence_quote: r.evidence[0]?.quote ?? "",
                answer_id: r.evidence[0]?.answer_id,
                snapshot_id: (r.evidence[0] as Row)?.snapshot_id,
                research_source_id: (r.evidence[0] as Row)?.research_source_id,
              }}
              submit="保存研究修订"
              onSubmit={(body) => saveResearch(body, r.id)}
            />
            <ResearchHistory id={r.id} revision={revision} />
          </article>
        ))}
      </Load>
      <Form
        title="登记平台研究或待验证假设"
        fields={fields}
        submit="保存研究记录"
        onSubmit={(body) => saveResearch(body)}
      />
      <h2>把改动放入可检验的实验</h2>
      <p className="muted">
        先在观测与验收中建立关联内容版本的基线 /
        复测与真实对照组，再登记观察窗口。窗口必须覆盖实际回答时间；新增实验冻结比较与分析版本。
      </p>
      <Load state={experiments}>
        {!experiments.data?.length && (
          <Empty>
            没有预设实验成功结论。样本、覆盖、分析口径或对照不足时，只能保留证据不足。
          </Empty>
        )}
        {experiments.data?.map((e) => (
          <article className="work-item" key={e.id}>
            <p className="eyebrow">
              {opsLabels[String(e.status)] ??
                String(e.status ?? "尚未形成结论")}
            </p>
            <h3>{e.title}</h3>
            <p>假设：{e.hypothesis}</p>
            <p>主要改变：{e.primary_change}</p>
            <p className="muted">
              {e.conditions} · 局限：{e.limitations}
            </p>
            <div className="toolbar">
              <button
                className="secondary"
                onClick={() =>
                  setExperimentId(experimentId === e.id ? null : e.id)
                }
              >
                查看冻结比较与结论门禁
              </button>
            </div>
            {experimentId === e.id && (
              <ExperimentRecord id={e.id} revision={revision} />
            )}
            <Form
              title="人工审阅实验结论（后端证据门禁）"
              fields={[
                {
                  key: "status",
                  label: "观察结论",
                  options: ["inconclusive", "supported", "refuted"].map(
                    (value) => ({ value, label: opsLabels[value] }),
                  ),
                },
                { key: "reviewer", label: "审阅人", required: true },
                {
                  key: "note",
                  label: "观察说明与局限",
                  type: "textarea",
                  required: true,
                },
              ]}
              submit="提交证据约束的结论"
              onSubmit={(body) => mutate(`experiments/${e.id}/conclude`, body)}
            />
          </article>
        ))}
      </Load>
      <Form
        title="登记真实页面优化实验"
        fields={[
          { key: "title", label: "实验名称", required: true },
          {
            key: "hypothesis",
            label: "实验假设",
            type: "textarea",
            required: true,
          },
          {
            key: "primary_change",
            label: "本次主要改变（避免多重改动混淆）",
            type: "textarea",
            required: true,
          },
          {
            key: "page_id",
            label: "目标页面",
            type: "number",
            required: true,
            options: (pages.data ?? []).map((p) => ({
              value: String(p.id),
              label: p.title || p.url,
            })),
          },
          {
            key: "content_version_id",
            label: "已关联复测的内容版本",
            type: "number",
            required: true,
            options: versions.map((v) => ({
              value: String(v.id),
              label: v.title,
            })),
          },
          {
            key: "baseline_batch_id",
            label: "基线批次",
            type: "number",
            required: true,
            options: (batches.data ?? []).map((b) => ({
              value: String(b.id),
              label: b.name,
            })),
          },
          {
            key: "retest_batch_id",
            label: "匹配复测批次",
            type: "number",
            required: true,
            options: (batches.data ?? [])
              .filter((b) => b.baseline_batch_id)
              .map((b) => ({ value: String(b.id), label: b.name })),
          },
          {
            key: "window_start",
            label: "观察窗口开始（本地时间）",
            type: "datetime-local",
            required: true,
          },
          {
            key: "window_end",
            label: "观察窗口结束（本地时间）",
            type: "datetime-local",
            required: true,
          },
          {
            key: "metric",
            label: "主要指标",
            options: [
              { value: "mention_rate", label: "品牌提及率" },
              { value: "recommendation_rate", label: "明确推荐率" },
              { value: "factual_error_rate", label: "事实错误率" },
            ],
          },
          {
            key: "direction",
            label: "预期方向",
            options: [
              { value: "increase", label: "提高" },
              { value: "decrease", label: "降低" },
            ],
          },
          {
            key: "conditions",
            label: "条件控制说明",
            type: "textarea",
            required: true,
          },
          {
            key: "limitations",
            label: "不可外推的局限",
            type: "textarea",
            required: true,
          },
        ]}
        submit="冻结证据并建立实验"
        onSubmit={(body) => mutate(`projects/${projectId}/experiments`, body)}
      />
      <h2>有来源的运营经验</h2>
      <Load state={rules}>
        {!rules.data?.length && (
          <Empty>
            尚无经证据支持和人工审阅的经验。不要把待验证假设当成通用优化方法。
          </Empty>
        )}
        {rules.data?.map((rule) => (
          <article className="research-note" key={rule.id}>
            <h3>{rule.title}</h3>
            <p>{rule.instruction}</p>
            <p className="muted">
              条件：{rule.conditions} · 局限：{rule.limitations}
            </p>
            <small>
              审阅：{rule.reviewer} · {rule.review_note}
            </small>
          </article>
        ))}
      </Load>
      <Form
        title="将已支持结论转为有边界的运营经验"
        fields={[
          { key: "title", label: "经验标题", required: true },
          {
            key: "instruction",
            label: "可执行运营方法",
            type: "textarea",
            required: true,
          },
          {
            key: "conditions",
            label: "适用条件",
            type: "textarea",
            required: true,
          },
          {
            key: "limitations",
            label: "局限与不适用场景",
            type: "textarea",
            required: true,
          },
          {
            key: "research_id",
            label: "依据研究（须当前支持）",
            type: "number",
            options: [
              { value: "", label: "不引用研究" },
              ...(research.data ?? [])
                .filter((r) => r.status === "supported")
                .map((r) => ({ value: String(r.id), label: r.claim })),
            ],
          },
          {
            key: "experiment_id",
            label: "依据实验（须当前支持）",
            type: "number",
            options: [
              { value: "", label: "不引用实验" },
              ...(experiments.data ?? [])
                .filter((e) => e.status === "supported")
                .map((e) => ({ value: String(e.id), label: e.title })),
            ],
          },
          { key: "reviewer", label: "经验审阅人", required: true },
          {
            key: "review_note",
            label: "转化依据与边界核对",
            type: "textarea",
            required: true,
          },
        ]}
        submit="保存有依据的运营经验"
        onSubmit={(body) =>
          mutate(`projects/${projectId}/operations/rules`, body)
        }
      />
    </>
  );
}
