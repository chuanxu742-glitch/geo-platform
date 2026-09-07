"use client";
import {
  api,
  Form,
  Action,
  Json,
  Empty,
  Load,
  useData,
  type Field,
  type Row,
} from "./ui";
import type { Project, Question, Source, Fact } from "./types";
export const projectFields: Field[] = [
  { key: "name", label: "项目名称", required: true },
  { key: "brand", label: "品牌名称", required: true },
  { key: "aliases", label: "品牌别名（逗号分隔）", type: "list" },
  { key: "website_url", label: "品牌官网", type: "url" },
  { key: "region", label: "品牌地区" },
];
const competitorFields: Field[] = [
  { key: "name", label: "竞品名称", required: true },
  { key: "aliases", label: "别名（逗号分隔）", type: "list" },
];
const factFields: Field[] = [
  { key: "claim", label: "可核验事实", type: "textarea", required: true },
  { key: "source_url", label: "出处 URL", type: "url", required: true },
  {
    key: "valid_from",
    label: "有效起始时间",
    type: "datetime-local",
    hint: "留空以创建时间为起点；输入按本地时间转换为 UTC。",
  },
  { key: "valid_to", label: "有效截止时间", type: "datetime-local" },
];
export const questionFields: Field[] = [
  { key: "text", label: "问题原文", type: "textarea", required: true },
  {
    key: "branded",
    label: "问题包含品牌（不勾选即不带品牌）",
    type: "checkbox",
  },
  { key: "intent", label: "意图", hint: "例如：比较、选购、使用方法" },
  { key: "region", label: "提问地区" },
];
const sourceFields: Field[] = [
  { key: "name", label: "配置名称", required: true },
  { key: "platform", label: "平台", required: true },
  { key: "source_id", label: "Razormind source_id", required: true },
  { key: "mode", label: "运行 mode", required: true },
  {
    key: "parameter_mapping",
    label: "问题参数映射 JSON",
    type: "json",
    hint: '例如 {"question":"prompt"}，值为已有 source 的实际参数名。',
  },
  { key: "parameters", label: "固定参数 JSON（不填凭据）", type: "json" },
  {
    key: "result_mapping",
    label: "结果字段映射 JSON",
    type: "json",
    hint: "text / sources / status / role / complete 对应返回结果的点分隔路径。",
  },
  {
    key: "answer_complete",
    label: "确认此 source 返回完整回答（否则有效性未知）",
    type: "checkbox",
  },
];
export function Catalog({
  project,
  revision,
  refresh,
}: {
  project: Row;
  revision: number;
  refresh: () => void;
}) {
  const competitors = useData(`projects/${project.id}/competitors`, revision),
    facts = useData(`projects/${project.id}/facts`, revision);
  const mutate = async (path: string, method: string, body?: Row) => {
    await api(path, method, body);
    refresh();
  };
  return (
    <>
      <section className="brand-sheet">
        <div>
          <p className="eyebrow">品牌档案 / BRAND DOSSIER</p>
          <h2>{project.brand}</h2>
          <dl>
            <dt>项目</dt>
            <dd>{project.name}</dd>
            <dt>别名</dt>
            <dd>{project.aliases?.join("、") || "尚未登记"}</dd>
            <dt>官网</dt>
            <dd>
              {project.website_url ? (
                <a href={project.website_url} target="_blank" rel="noreferrer">
                  {project.website_url}
                </a>
              ) : (
                "尚未登记"
              )}
            </dd>
            <dt>地区</dt>
            <dd>{project.region || "尚未登记"}</dd>
          </dl>
        </div>
        <aside className="brand-annotation">
          <span className="eyebrow">事实是观察的起点</span>
          <strong>{facts.data?.length ?? "—"}</strong>
          <span>条已登记事实</span>
          <p>每条声明保留出处与有效期。后续修改，不重写历史批次的判断依据。</p>
        </aside>
      </section>
      <Form
        key={project.id}
        title="编辑品牌档案"
        fields={projectFields}
        initial={project}
        submit="保存品牌"
        onSubmit={(body) => mutate(`projects/${project.id}`, "PATCH", body)}
      />
      <div className="catalog-columns">
        <section className="catalog-competitors">
          <h2>竞品</h2>
          <Load state={competitors}>
            {!competitors.data?.length && <Empty />}
            {competitors.data?.map((item: Row) => (
              <details className="card" key={item.id}>
                <summary>
                  #{item.id} {item.name}
                </summary>
                <Form
                  title="编辑竞品"
                  fields={competitorFields}
                  initial={item}
                  submit="保存竞品"
                  onSubmit={(body) =>
                    mutate(`competitors/${item.id}`, "PATCH", body)
                  }
                />
                <Action
                  danger
                  run={() => mutate(`competitors/${item.id}`, "DELETE")}
                >
                  删除竞品
                </Action>
              </details>
            ))}
          </Load>
          <Form
            title="新增竞品"
            fields={competitorFields}
            submit="新增竞品"
            onSubmit={(body) =>
              mutate(`projects/${project.id}/competitors`, "POST", body)
            }
          />
        </section>
        <section className="catalog-facts">
          <h2>事实库</h2>
          <p className="muted">
            事实修改只影响后续批次；历史批次保留冻结事实，便于审计。
          </p>
          <Load state={facts}>
            {!facts.data?.length && <Empty />}
            {facts.data?.map((item: Row) => (
              <details className="card" key={item.id} open>
                <summary>
                  {item.claim} <small>事实 #{item.id}</small>
                </summary>
                <div className="fact-provenance">
                  <a href={item.source_url} target="_blank" rel="noreferrer">
                    {item.source_url}
                  </a>
                  <p>
                    有效期：
                    {item.valid_from
                      ? new Date(item.valid_from).toLocaleDateString("zh-CN")
                      : "自登记起"}{" "}
                    —{" "}
                    {item.valid_to
                      ? new Date(item.valid_to).toLocaleDateString("zh-CN")
                      : "未设截止"}
                  </p>
                </div>
                <Form
                  title="编辑事实"
                  fields={factFields}
                  initial={item}
                  submit="保存事实"
                  onSubmit={(body) => mutate(`facts/${item.id}`, "PATCH", body)}
                />
                <Action danger run={() => mutate(`facts/${item.id}`, "DELETE")}>
                  删除事实
                </Action>
              </details>
            ))}
          </Load>
          <Form
            title="新增事实"
            fields={factFields}
            submit="新增事实"
            onSubmit={(body) =>
              mutate(`projects/${project.id}/facts`, "POST", body)
            }
          />
        </section>
      </div>
    </>
  );
}
function Versions({ id, revision }: { id: number; revision: number }) {
  const data = useData(`questions/${id}/versions`, revision);
  return (
    <Load state={data}>
      <Json value={data.data} title="不可变问题版本记录" />
    </Load>
  );
}
export function Questions({
  projectId,
  revision,
  refresh,
  onBatch,
}: {
  projectId: number;
  revision: number;
  refresh: () => void;
  onBatch: (id: number) => void;
}) {
  const questions = useData<Question[]>(
      `projects/${projectId}/questions`,
      revision,
    ),
    sources = useData<Source[]>(`projects/${projectId}/sources`, revision);
  const questionOptions = (questions.data ?? [])
    .filter((q) => !q.archived)
    .map((q) => ({
      value: String(q.id),
      label: `${q.current_version.text} · v${q.current_version.version}`,
    }));
  const sourceOptions = (sources.data ?? []).map((s) => ({
    value: String(s.id),
    label: `${s.name} · ${s.platform}`,
  }));
  const mutate = async (path: string, method: string, body?: Row) => {
    await api(path, method, body);
    refresh();
  };
  return (
    <>
      <h2>问题与版本</h2>
      <Load state={questions}>
        {!questions.data?.length && <Empty />}
        {questions.data?.map((q: Row) => (
          <details className="card" key={q.id}>
            <summary>
              #{q.id} · {q.current_version.branded ? "带品牌" : "不带品牌"} ·{" "}
              {q.current_version.text} {q.archived && "（已归档）"}
              <small>
                v{q.current_version.version} ·{" "}
                {q.current_version.intent || "意图未标注"} ·{" "}
                {q.current_version.region || "地区未标注"}
              </small>
            </summary>
            <p>
              版本 v{q.current_version.version} · 版本 ID {q.current_version.id}
            </p>
            <Form
              title="编辑并建立新版本"
              fields={questionFields}
              initial={q.current_version}
              submit="保存新版本"
              onSubmit={(body) => mutate(`questions/${q.id}`, "PATCH", body)}
            />
            <Versions id={q.id} revision={revision} />
            {!q.archived && (
              <Action danger run={() => mutate(`questions/${q.id}`, "DELETE")}>
                归档问题
              </Action>
            )}
          </details>
        ))}
      </Load>
      <Form
        title="新增问题"
        fields={questionFields}
        submit="新增问题"
        onSubmit={(body) =>
          mutate(`projects/${projectId}/questions`, "POST", body)
        }
      />
      <h2>建立基线批次</h2>
      <Form
        title="冻结问题、品牌、事实与采样条件"
        fields={[
          { key: "name", label: "批次名称", required: true },
          {
            key: "question_ids",
            label: "选择问题",
            type: "ids",
            multiple: true,
            options: questionOptions,
            required: true,
          },
          {
            key: "source_ids",
            label: "选择采集配置（人工导入可不选）",
            type: "ids",
            multiple: true,
            options: sourceOptions,
          },
          {
            key: "mode",
            label: "批次模式",
            options: [
              { value: "manual", label: "人工导入" },
              { value: "collector", label: "Razormind 采集" },
            ],
          },
          {
            key: "platforms",
            label: "冻结平台列表（逗号分隔，人工批次必填）",
            type: "list",
            required: true,
            hint: "导入与复测只允许这些平台。",
          },
          {
            key: "sampling",
            label: "其他采样条件 JSON",
            type: "json",
            hint: "记录语言、模型、时间窗口等；复测原样冻结复用。",
          },
          {
            key: "control_question_ids",
            label: "选择对照问题（须属于本批次）",
            type: "ids",
            multiple: true,
            options: questionOptions,
          },
        ]}
        submit="创建批次并进入回答"
        onSubmit={async (body) => {
          const { platforms, ...batchBody } = body;
          const batch = await api(`projects/${projectId}/batches`, "POST", {
            ...batchBody,
            sampling: { ...batchBody.sampling, platforms },
          });
          refresh();
          onBatch(batch.id);
        }}
      />
      <h2>已有采集源映射</h2>
      <p className="notice">
        这里连接现有 Razormind source，不修改 opencli、不读取浏览器
        cookie。服务地址和 token
        仅由后端环境变量配置。创建批次不会自动采集，需在回答区明确触发。
      </p>
      <Load state={sources}>
        {!sources.data?.length && <Empty>无采集配置也可使用人工导入。</Empty>}
        {sources.data?.map((s: Row) => (
          <details className="card" key={s.id}>
            <summary>
              #{s.id} {s.name} · {s.platform} · source_id {s.source_id}
            </summary>
            <Form
              title="编辑采集映射"
              fields={sourceFields}
              initial={s}
              submit="保存映射"
              onSubmit={(body) => mutate(`sources/${s.id}`, "PATCH", body)}
            />
            <Action danger run={() => mutate(`sources/${s.id}`, "DELETE")}>
              删除配置
            </Action>
          </details>
        ))}
      </Load>
      <Form
        title="新增采集源"
        fields={sourceFields}
        initial={{
          mode: "browser",
          parameter_mapping: { question: "question" },
          result_mapping: {
            text: "normalized_data.response",
            sources: "normalized_data.sources",
            status: "normalized_data.status",
          },
        }}
        submit="新增采集配置"
        onSubmit={(body) =>
          mutate(`projects/${projectId}/sources`, "POST", body)
        }
      />
    </>
  );
}
