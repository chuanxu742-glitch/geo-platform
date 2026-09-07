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
  LinkURL,
} from "./ui";
import { Actions } from "./actions";
import type { Fact, Question, Batch } from "./types";
import {
  opsLabels,
  type OpsContext,
  type SitePage,
  type PageSnapshot,
  type Content,
} from "./operations-types";
const pageFields: Field[] = [
  { key: "title", label: "页面名称", required: true },
  { key: "url", label: "官网页面 URL", type: "url", required: true },
  {
    key: "page_type",
    label: "页面用途",
    hint: "例如：服务页、产品页、帮助页；不是平台评分。",
  },
  { key: "owner", label: "页面负责人", required: true },
  { key: "next_review_at", label: "下一次维护时间", type: "datetime-local" },
  {
    key: "review_interval_days",
    label: "维护间隔（天）",
    type: "number",
    required: true,
  },
];
export function PageOperations({
  projectId,
  revision,
  refresh,
  navigate,
}: OpsContext) {
  const pages = useData<SitePage[]>(`projects/${projectId}/pages`, revision),
    facts = useData<Fact[]>(`projects/${projectId}/facts`, revision),
    questions = useData<Question[]>(
      `projects/${projectId}/questions`,
      revision,
    ),
    contents = useData<Content[]>(`projects/${projectId}/contents`, revision),
    batches = useData<Batch[]>(`projects/${projectId}/batches`, revision);
  const [pageId, setPageId] = useState(""),
    [snapshotId, setSnapshotId] = useState(""),
    [task, setTask] = useState<Row | null>(null),
    [maintenance, setMaintenance] = useState<Row | null>(null);
  const page = pages.data?.find((p) => String(p.id) === pageId);
  const snapshots = useData<PageSnapshot[]>(
    pageId ? `pages/${pageId}/snapshots` : null,
    revision,
  );
  const currentSnapshotId =
    snapshotId ||
    String(snapshots.data?.[0]?.id ?? page?.latest_snapshot?.id ?? "");
  const snapshot = useData<PageSnapshot>(
    currentSnapshotId ? `page-snapshots/${currentSnapshotId}` : null,
    revision,
  );
  const mutate = async (path: string, method: string, body?: Row) => {
    const result = await api(path, method, body);
    refresh();
    return result;
  };
  const validFacts = (facts.data ?? []).filter(
    (f) =>
      (!f.valid_from || new Date(f.valid_from) <= new Date()) &&
      (!f.valid_to || new Date(f.valid_to) > new Date()),
  );
  const titleGroups = new Map<string, SitePage[]>();
  for (const p of pages.data ?? []) {
    const s = p.latest_snapshot;
    if (!s || s.status !== "success" || !s.title.trim()) continue;
    const title = s.title.trim().replace(/\s+/g, " ").toLocaleLowerCase();
    titleGroups.set(title, [...(titleGroups.get(title) ?? []), p]);
  }
  const duplicateTitles = [...titleGroups.values()].filter(group => group.length > 1);
  return (
    <>
      <div className="section-toolbar">
        <h2>SEO 检查与页面内容优化</h2>
        <Action
          run={async () => {
            setMaintenance(
              await api(`projects/${projectId}/operations/check-due`, "POST"),
            );
            refresh();
          }}
        >
          显式检查到期页面与事实
        </Action>
      </div>
      <p className="notice">
        抓取与维护检查会访问已登记
        URL；不会自动爬站或调用模型。页面核验只说明正文匹配，不意味着 AI
        已索引、引用或产生优化效果。
      </p>
      {maintenance && (
        <section className="card">
          <h3>本次维护检查</h3>
          <p>
            检查 {maintenance.checked?.length ?? 0} 个页面；安排 / 复用{" "}
            {maintenance.actions?.length ?? 0} 项维护任务。
          </p>
          <Json value={maintenance} title="检查记录与任务依据" />
          <button className="secondary" onClick={() => navigate("plans")}>
            处理维护任务 ↗
          </button>
        </section>
      )}
      <Load state={pages}>
        {duplicateTitles.length > 0 && (
          <section className="card">
            <h3>跨页面重复标题</h3>
            <p className="muted">仅比较本项目已登记页面的最新成功快照标题；不代表全站审计或实际收录结果。不同用途的页面应有独立标题，语言版本或重复页需人工核对。</p>
            {duplicateTitles.map(group => (
              <div key={group[0].id}>
                <h4>{group[0].latest_snapshot?.title}</h4>
                <ul>{group.map(p => <li key={p.id}><button className="secondary" onClick={() => { setPageId(String(p.id)); setSnapshotId(""); setTask(null); }}>{p.url}</button></li>)}</ul>
              </div>
            ))}
          </section>
        )}
        {!pages.data?.length && (
          <Empty>
            先在品牌资料登记官网，再登记一个真实目标页面。没有采集账号时可人工导入
            HTML，来源会明确标注。
          </Empty>
        )}
        <div className="page-register">
          {pages.data?.map((p) => (
            <button
              key={p.id}
              className={`page-register-row ${pageId === String(p.id) ? "selected" : ""}`}
              onClick={() => {
                setPageId(String(p.id));
                setSnapshotId("");
                setTask(null);
              }}
            >
              <span>
                <strong>{p.title || p.url}</strong>
                <small>{p.url}</small>
              </span>
              <span>
                <small>
                  {p.owner || "未分配"} ·{" "}
                  {p.next_review_at
                    ? new Date(p.next_review_at).toLocaleDateString("zh-CN")
                    : "未安排维护"}
                </small>
                <small>
                  {p.maintenance_reasons.join("；") ||
                    (p.latest_publication?.status === "verified"
                      ? "批准正文已核验"
                      : "尚未完成正文核验")}
                </small>
              </span>
            </button>
          ))}
        </div>
      </Load>
      <Form
        title="登记需要优化的页面"
        fields={pageFields}
        initial={{ review_interval_days: 30, page_type: "service" }}
        submit="登记页面"
        onSubmit={async (body) => {
          const p = await mutate(`projects/${projectId}/pages`, "POST", body);
          setPageId(String(p.id));
          setSnapshotId("");
        }}
      />
      {page && (
        <section className="page-dossier" key={page.id}>
          <div className="section-toolbar">
            <div>
              <p className="eyebrow">页面优化档案</p>
              <h2>{page.title}</h2>
              <LinkURL url={page.url} />
            </div>
            <Action
              run={async () => {
                const s = await mutate(`pages/${page.id}/fetch`, "POST");
                setSnapshotId(String(s.id));
              }}
            >
              明确授权：抓取此官网页面
            </Action>
          </div>
          <Form
            title="编辑页面与维护计划"
            fields={pageFields}
            initial={page}
            submit="保存维护计划"
            onSubmit={(body) => mutate(`pages/${page.id}`, "PATCH", body)}
          />
          <Form
            title="人工导入页面 HTML（不会伪装成HTTP抓取）"
            fields={[
              {
                key: "html",
                label: "完整页面 HTML",
                type: "textarea",
                required: true,
              },
              {
                key: "source_note",
                label: "导入来源与时间说明",
                type: "textarea",
                required: true,
              },
            ]}
            submit="保存不可变人工快照"
            onSubmit={async (body) => {
              const s = await mutate(
                `pages/${page.id}/import-html`,
                "POST",
                body,
              );
              setSnapshotId(String(s.id));
            }}
          />
          <label className="picker">
            观察快照
            <select
              value={currentSnapshotId}
              onChange={(e) => setSnapshotId(e.target.value)}
            >
              <option value="">尚无快照</option>
              {snapshots.data?.map((s) => (
                <option key={s.id} value={s.id}>
                  {new Date(s.created_at).toLocaleString("zh-CN")} ·{" "}
                  {opsLabels[s.source_kind] ?? s.source_kind} ·{" "}
                  {opsLabels[s.status] ?? s.status}
                </option>
              ))}
            </select>
          </label>
          <Load state={snapshot}>
            {snapshot.data && (
              <>
                <section className="snapshot-sheet">
                  <div>
                    <p className="eyebrow">不可变页面观察</p>
                    <h3>{snapshot.data.title || "未观察到页面标题"}</h3>
                    <p>
                      {opsLabels[snapshot.data.source_kind]} ·{" "}
                      {opsLabels[snapshot.data.status]} · HTTP{" "}
                      {snapshot.data.http_status ?? "未知 / 非HTTP导入"}
                    </p>
                    {snapshot.data.error && (
                      <p role="alert" className="error">
                        {snapshot.data.error}
                      </p>
                    )}
                    <p className="muted">
                      无评分承诺。抓取失败不记零分，robots未知不推断允许或拒绝，llms.txt不是必要条件。
                    </p>
                    <dl className="readable-dl">
                      <dt>描述</dt>
                      <dd>{snapshot.data.meta_description || "未观察到"}</dd>
                      <dt>Canonical</dt>
                      <dd>{snapshot.data.canonical || "未观察到"}</dd>
                      <dt>标题结构</dt>
                      <dd>
                        {snapshot.data.headings.map((h, i) => (
                          <p key={i}>
                            H{h.level} · {h.text}
                          </p>
                        ))}
                      </dd>
                      <dt>搜索抓取</dt>
                      <dd>
                        {snapshot.data.robots_txt?.agents?.["OAI-SearchBot"] ==
                        null
                          ? "未知"
                          : snapshot.data.robots_txt.agents["OAI-SearchBot"]
                            ? "允许"
                            : "禁止"}
                      </dd>
                      <dt>训练抓取</dt>
                      <dd>
                        {snapshot.data.robots_txt?.agents?.["GPTBot"] == null
                          ? "未知"
                          : snapshot.data.robots_txt.agents["GPTBot"]
                            ? "允许"
                            : "禁止"}
                      </dd>
                    </dl>
                  </div>
                  <aside>
                    <h3>可见正文</h3>
                    <pre className="answer-text">
                      {snapshot.data.visible_text || "当前没有可观察正文"}
                    </pre>
                    <Json
                      value={{
                        hash: snapshot.data.content_hash,
                        html: snapshot.data.html,
                        fetch: snapshot.data.fetch_evidence,
                        robots: snapshot.data.robots_txt,
                      }}
                      title="高级：原始HTML / 哈希 / 抓取依据"
                    />
                  </aside>
                </section>
                <h2>真实可观测发现</h2>
                {!snapshot.data.findings.length && (
                  <Empty>
                    本次没有可展示的检查发现；不代表页面能够获得排名或推荐。
                  </Empty>
                )}
                {snapshot.data.findings.map((f) => (
                  <article className="finding-row" key={f.id}>
                    <p className="eyebrow">
                      {f.severity === "warning" ? "待检查" : "观察说明"} /{" "}
                      {f.kind}
                    </p>
                    <h3>{f.title}</h3>
                    <div className="finding-evidence">
                      <small>
                        定位：{String(f.evidence.location ?? "页面观察")}
                      </small>
                      <p>
                        {typeof f.evidence.observed === "string"
                          ? f.evidence.observed
                          : JSON.stringify(f.evidence.observed ?? f.evidence)}
                      </p>
                    </div>
                    <p>{f.recommendation}</p>
                    {f.evidence.execution === "website_code" && (
                      <p className="notice">
                        处理方式：修改网站代码或页面模板。正文改稿与发布不会修复此项。
                        验收：重新抓取并核对页面声明，实际收录需另行确认。
                      </p>
                    )}
                    <button
                      className="secondary"
                      onClick={() => {
                        setTask({
                          title: f.title,
                          finding_id: f.id,
                          page_id: page.id,
                          target_page: page.url,
                          owner: page.owner,
                        });
                        requestAnimationFrame(() =>
                          document
                            .getElementById("finding-action")
                            ?.scrollIntoView({ behavior: "smooth" }),
                        );
                      }}
                    >
                      以此发现创建优化任务
                    </button>
                  </article>
                ))}
                {task && (
                  <div id="finding-action">
                    <Actions
                      key={JSON.stringify(task)}
                      mode="tasks"
                      initialTask={task}
                      projectId={projectId}
                      revision={revision}
                      refresh={refresh}
                      batches={batches.data ?? []}
                    />
                  </div>
                )}
                <h2>优化简报与改稿</h2>
                <p className="notice">
                  基于当前有效事实、目标问题与这一页的观察快照修订，不默认批量生成文章。手工改稿始终可用；模型未配时明确不可用，生成结果仍待人工审核。
                </p>
                <details className="card">
                  <summary>准备内容条目：创建 / 选择同 URL 的内容</summary>
                  <p>
                    新内容的目标 URL 必须为 <LinkURL url={page.url} />
                    ；此处复用同一内容与版本库。
                  </p>
                  <Actions
                    mode="contents"
                    projectId={projectId}
                    revision={revision}
                    refresh={refresh}
                    batches={batches.data ?? []}
                  />
                </details>
                <Form
                  title="保存基于页面证据的修订版本"
                  fields={[
                    {
                      key: "content_id",
                      label: "目标内容条目（同页面URL）",
                      type: "number",
                      required: true,
                      options: (contents.data ?? [])
                        .filter((c) => c.target_url === page.url)
                        .map((c) => ({ value: String(c.id), label: c.title })),
                    },
                    {
                      key: "fact_ids",
                      label: "当前有效事实依据",
                      type: "ids",
                      multiple: true,
                      required: true,
                      options: validFacts.map((f) => ({
                        value: String(f.id),
                        label: f.claim,
                      })),
                    },
                    {
                      key: "question_ids",
                      label: "需要回答的目标问题",
                      type: "ids",
                      multiple: true,
                      required: true,
                      options: (questions.data ?? []).map((q) => ({
                        value: String(q.id),
                        label: q.current_version.text,
                      })),
                    },
                    {
                      key: "instructions",
                      label: "优化简报：用户决策障碍、主要改变与边界",
                      type: "textarea",
                      required: true,
                    },
                    {
                      key: "mode",
                      label: "改稿方式",
                      options: [
                        { value: "manual", label: "手工编辑（不调用模型）" },
                        {
                          value: "model",
                          label: "显式调用已配置模型（可能计费，仍待审核）",
                        },
                      ],
                    },
                    {
                      key: "after_text",
                      label: "修订后的完整正文（手工模式必填）",
                      type: "textarea",
                    },
                  ]}
                  submit="保存新的待审核内容版本"
                  onSubmit={(body) =>
                    mutate(`pages/${page.id}/draft`, "POST", {
                      ...body,
                      snapshot_id: snapshot.data!.id,
                    })
                  }
                />
                <button
                  className="secondary"
                  onClick={() => navigate("content")}
                >
                  进入内容审核与发布 ↗
                </button>
              </>
            )}
          </Load>
        </section>
      )}
    </>
  );
}
