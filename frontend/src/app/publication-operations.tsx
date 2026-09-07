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
  LinkURL,
  type Field,
  type Row,
} from "./ui";
import { Actions } from "./actions";
import type { Batch } from "./types";
import {
  opsLabels,
  type OpsContext,
  type Content,
  type Publisher,
  type SitePage,
  type PublicationJob,
} from "./operations-types";
const publisherFields: Field[] = [
  { key: "name", label: "WordPress 发布配置名称", required: true },
  {
    key: "site_url",
    label: "WordPress 官网地址（须与品牌官网同源）",
    type: "url",
    required: true,
  },
  {
    key: "resource",
    label: "更新既有资源类型",
    options: [
      { value: "pages", label: "页面 pages" },
      { value: "posts", label: "文章 posts" },
    ],
  },
  {
    key: "post_id",
    label: "WordPress 既有页面 / 文章 ID",
    type: "number",
    required: true,
    hint: "来自你管理的 WordPress；提交前后端核对资源 ID 与实际 URL，不创建新文章。",
  },
  { key: "enabled", label: "启用此配置（不自动发布）", type: "checkbox" },
];
function PublicationEvidence({
  id,
  revision,
}: {
  id: number;
  revision: number;
}) {
  const state = useData<PublicationJob>(`publication-jobs/${id}`, revision);
  return (
    <Load state={state}>
      {state.data && (
        <>
          <h4>核验历史</h4>
          {!state.data.verifications?.length && (
            <p className="muted">
              尚无页面正文核验。HTTP 200 或 WordPress 更新响应均不构成正文核验。
            </p>
          )}
          {state.data.verifications?.map((v) => (
            <article className="margin-note" key={v.id}>
              <strong>{opsLabels[v.status] ?? v.status}</strong>
              <p>{v.summary}</p>
              <small>
                {v.verified_at} · 匹配依据：{v.matched_by || "未匹配"}
              </small>
            </article>
          ))}
          <Json
            value={{
              execution: state.data.execution_evidence,
              config: state.data.config_snapshot,
              expected_hash: state.data.expected_hash,
            }}
            title="高级：冻结发布配置、正文哈希与脱敏执行依据"
          />
        </>
      )}
    </Load>
  );
}
export function PublicationOperations({
  projectId,
  revision,
  refresh,
  navigate,
}: OpsContext) {
  const contents = useData<Content[]>(
      `projects/${projectId}/contents`,
      revision,
    ),
    pages = useData<SitePage[]>(`projects/${projectId}/pages`, revision),
    publishers = useData<Publisher[]>(
      `projects/${projectId}/publishers`,
      revision,
    ),
    jobs = useData<PublicationJob[]>(
      `projects/${projectId}/publication-jobs`,
      revision,
    ),
    batches = useData<Batch[]>(`projects/${projectId}/batches`, revision);
  const [versionId, setVersionId] = useState(""),
    [jobId, setJobId] = useState<number | null>(null);
  const versions = (contents.data ?? []).flatMap((c) =>
    c.versions.map((v) => ({ ...v, content: c })),
  );
  const version = versions.find((v) => String(v.id) === versionId);
  const mutate = async (path: string, body: Row, method = "POST") => {
    const result = await api(path, method, body);
    refresh();
    return result;
  };
  return (
    <>
      <div className="ops-intro">
        <div>
          <p className="eyebrow">人工把关 / 显式发布 / 正文核验</p>
          <h2>审核通过，才走向站点。</h2>
          <p>
            草稿与已发布页面不是同一件事。执行完成后仍需核验批准正文；不宣称 AI
            已索引、引用或优化有效。
          </p>
        </div>
        <button className="secondary" onClick={() => navigate("pages")}>
          先优化已有页面 ↗
        </button>
      </div>
      <Load state={contents}>
        <label className="picker">
          选择审核 / 发布的内容版本
          <select
            value={versionId}
            onChange={(e) => setVersionId(e.target.value)}
          >
            <option value="">请选择内容版本</option>
            {versions.map((v) => (
              <option key={v.id} value={v.id}>
                {v.content.title} · v{v.version} ·{" "}
                {opsLabels[v.review_status] ?? v.review_status}
              </option>
            ))}
          </select>
        </label>
        {!versions.length && (
          <Empty>
            还没有内容版本。先对现有页面形成优化简报并保存改稿，或展开下方内容库手动建立版本。
          </Empty>
        )}
      </Load>
      {version && (
        <section className="review-sheet" key={version.id}>
          <div className="section-toolbar">
            <div>
              <p className="eyebrow">
                版本 v{version.version} /{" "}
                {opsLabels[version.review_status] ?? version.review_status}
              </p>
              <h2>{version.content.title}</h2>
              <LinkURL url={version.content.target_url} />
            </div>
            <span className="status-tag">
              {version.published_at
                ? "存在人工历史发布记录，仍以正文核验为准"
                : "待完成审核与发布流程"}
            </span>
          </div>
          <pre className="answer-text">{version.after_text}</pre>
          <div className="review-facts">
            <h3>本版本事实依据</h3>
            {version.facts_snapshot.map((f) => (
              <article key={f.id}>
                <p>{f.claim}</p>
                <LinkURL url={f.source_url} />
                <small>
                  事实 #{f.id} · 有效至 {f.valid_to ?? "未设截止"}
                </small>
              </article>
            ))}
          </div>
          {version.reviewer && (
            <p className="notice">
              最近审核：{version.reviewer} · {opsLabels[version.review_status]}{" "}
              · {version.review_note}
            </p>
          )}
          <Form
            title="人工审核此不可变版本"
            fields={[
              {
                key: "status",
                label: "审核决定",
                options: [
                  { value: "approved", label: "审核通过" },
                  { value: "rejected", label: "退回修改" },
                ],
              },
              { key: "reviewer", label: "审核人", required: true },
              {
                key: "note",
                label: "审核说明：事实、范围与目标页面核对",
                type: "textarea",
                required: true,
              },
            ]}
            submit="保存人工审核决定"
            onSubmit={(body) =>
              mutate(`content-versions/${version.id}/review`, body)
            }
          />
          {version.review_status === "approved" ? (
            <>
              <Form
                title="明确授权：更新 WordPress 既有页面"
                fields={[
                  {
                    key: "publisher_id",
                    label: "选择 WordPress 发布配置",
                    type: "number",
                    required: true,
                    options: (publishers.data ?? [])
                      .filter((p) => p.enabled)
                      .map((p) => ({ value: String(p.id), label: p.name })),
                  },
                  {
                    key: "page_id",
                    label: "目标登记页面（须匹配内容URL）",
                    type: "number",
                    required: true,
                    options: (pages.data ?? [])
                      .filter((p) => p.url === version.content.target_url)
                      .map((p) => ({
                        value: String(p.id),
                        label: p.title || p.url,
                      })),
                  },
                  {
                    key: "authorize",
                    label:
                      "我确认将此批准正文写入指定 WordPress 既有页面；这是实际外站修改，不会自动重发",
                    type: "checkbox",
                    required: true,
                  },
                ]}
                submit="授权并执行一次发布"
                onSubmit={async (body) => {
                  if (!body.authorize)
                    throw Error("必须明确确认外部发布副作用。");
                  const job = await mutate(
                    `content-versions/${version.id}/publish-jobs`,
                    { publisher_id: body.publisher_id, page_id: body.page_id },
                  );
                  setJobId(job.id);
                }}
              />
              <Form
                title="人工外部发布记录（本系统不发出写请求）"
                fields={[
                  {
                    key: "page_id",
                    label: "已在外部发布的登记页面",
                    type: "number",
                    required: true,
                    options: (pages.data ?? [])
                      .filter((p) => p.url === version.content.target_url)
                      .map((p) => ({
                        value: String(p.id),
                        label: p.title || p.url,
                      })),
                  },
                  {
                    key: "note",
                    label: "外部操作说明与依据",
                    type: "textarea",
                    required: true,
                  },
                  {
                    key: "published_at",
                    label: "实际外部发布时间",
                    type: "datetime-local",
                  },
                  {
                    key: "confirm_external",
                    label: "我确认已在外部完成发布；此记录本身不证明正文正确",
                    type: "checkbox",
                    required: true,
                  },
                ]}
                submit="保存外部记录并等待核验"
                onSubmit={async (body) => {
                  if (!body.confirm_external)
                    throw Error("请确认外部操作已完成。");
                  const { confirm_external, published_at, ...rest } = body;
                  const job = await mutate(
                    `content-versions/${version.id}/external-publication`,
                    { ...rest, ...(published_at ? { published_at } : {}) },
                  );
                  setJobId(job.id);
                }}
              />
            </>
          ) : (
            <p className="notice">
              当前版本尚未审核通过，不能执行发布。修改内容请保存新版本，不覆盖旧稿；新版本重新进入待审核。
            </p>
          )}
          <Json
            value={{
              before_text: version.before_text,
              source_snapshot_id: version.source_snapshot_id,
              generation: version.generation,
            }}
            title="高级：修改前正文与页面简报来源"
          />
        </section>
      )}
      <h2>发布执行与页面核验</h2>
      <p className="notice">
        已发出 / WordPress 响应成功 /
        批准正文已核验分开记录。提交不确定时先检查目标正文或同步既有资源，不盲目重发；核验失败可修正目标页面后再次核验。
      </p>
      <Load state={jobs}>
        {!jobs.data?.length && (
          <Empty>
            没有发布任务。登记发布时间或导出草稿不会被计为页面已核验。
          </Empty>
        )}
        {jobs.data?.map((job) => (
          <article className="publication-row" key={job.id}>
            <p className="eyebrow">
              {opsLabels[job.source_kind] ?? job.source_kind}
            </p>
            <div className="section-toolbar">
              <h3>{opsLabels[job.status] ?? job.status}</h3>
              <span className="status-tag">
                {job.status === "verified"
                  ? "仅表示批准正文匹配"
                  : "尚不能确认正文发布正确"}
              </span>
            </div>
            <LinkURL url={job.target_url} />
            <small>
              内容版本{" "}
              {versions.find((v) => v.id === job.content_version_id)?.content
                .title ?? ""}{" "}
              v
              {versions.find((v) => v.id === job.content_version_id)?.version ??
                "—"}
            </small>
            {job.error && (
              <p role="alert" className="error">
                {job.error}
              </p>
            )}
            <div className="toolbar">
              {job.source_kind === "wordpress" && (
                <Action
                  run={() => mutate(`publication-jobs/${job.id}/sync`, {})}
                >
                  只读同步 WordPress 资源状态
                </Action>
              )}
              <Action
                run={() => mutate(`publication-jobs/${job.id}/verify`, {})}
              >
                访问目标页并核验批准全文
              </Action>
              <button
                className="ghost"
                onClick={() => setJobId(jobId === job.id ? null : job.id)}
              >
                {jobId === job.id ? "收起核验记录" : "查看核验与执行依据"}
              </button>
            </div>
            {jobId === job.id && (
              <PublicationEvidence id={job.id} revision={revision} />
            )}
          </article>
        ))}
      </Load>
      <details className="card">
        <summary>WordPress 发布配置（只更新官网既有页面 / 文章）</summary>
        <p className="notice">
          这里只保存官网地址与资源 ID，不调用外站。后端需配置
          WORDPRESS_URL、WORDPRESS_USERNAME、WORDPRESS_APPLICATION_PASSWORD；未配置时明确不可用，凭据不进入浏览器。其他网站使用人工外部发布记录与正文核验。
        </p>
        {publishers.data?.map((p) => (
          <Form
            key={p.id}
            title={`编辑发布配置 · ${p.name}`}
            fields={publisherFields}
            initial={p}
            submit="保存发布配置"
            onSubmit={(body) => mutate(`publishers/${p.id}`, body, "PATCH")}
          />
        ))}
        <Form
          title="新增 WordPress 发布配置"
          fields={publisherFields}
          initial={{
            resource: "pages",
            enabled: false,
          }}
          submit="保存配置（不执行发布）"
          onSubmit={(body) => mutate(`projects/${projectId}/publishers`, body)}
        />
      </details>
      <details className="card">
        <summary>内容库：手工编辑与版本管理</summary>
        <Actions
          projectId={projectId}
          revision={revision}
          refresh={refresh}
          batches={batches.data ?? []}
          mode="contents"
        />
      </details>
    </>
  );
}
