"use client";
import { useEffect, useState } from "react";
import { api, Empty, Form, Load, useData } from "./ui";
import { Catalog, Questions } from "./catalog";
import { Answers, Overview } from "./answers";
import { Actions, Retest } from "./actions";
import { OperationsHome, Opportunities } from "./operations";
import { PageOperations } from "./page-operations";
import { PublicationOperations } from "./publication-operations";
import { ResearchOperations } from "./research-operations";
import type { Project, Batch } from "./types";
import { Prelude } from "./visual";
import { AgentStudio } from "./agent-studio";
const areas = [
  { id: "studio", title: "工作室", note: "说清目标，交给 Agent；你只审核关键决定。" },
  { id: "reviews", title: "待我审核", note: "先读成果与依据，再决定是否授权下一步。" },
  { id: "results", title: "成果与复盘", note: "已交付什么、核验了什么，以及下一次维护。" },
  {
    id: "workbench",
    title: "运营工作台",
    note: "今日行动 · 待审版本 · 发布与维护",
  },
  {
    id: "plans",
    title: "机会与计划",
    note: "业务问题地图 · 优先机会 · 本周行动",
  },
  {
    id: "pages",
    title: "页面优化",
    note: "登记与抓取 · 定位问题 · 事实驱动改稿",
  },
  {
    id: "content",
    title: "内容与发布",
    note: "人工审核 · 明确授权 · 页面正文核验",
  },
  {
    id: "research",
    title: "研究与实验",
    note: "平台证据 · 匹配实验 · 有边界的运营经验",
  },
  {
    id: "catalog",
    title: "品牌与事实",
    note: "品牌资料 · 竞品 · 可追溯有效事实",
  },
  {
    id: "observation",
    title: "观测与验收",
    note: "问题采集 · 原文与分析 · 运营改变的观察验证",
  },
];
const observations = [
  { id: "metrics", title: "回答指标" },
  { id: "questions", title: "问题与采集" },
  { id: "answers", title: "回答原文" },
  { id: "diagnoses", title: "证据诊断" },
  { id: "retest", title: "效果复测" },
];
export default function Page() {
  const [area, setArea] = useState("studio"),
    [observation, setObservation] = useState("metrics"),
    [projectId, setProjectId] = useState(""),
    [revision, setRevision] = useState(0),
    [creating, setCreating] = useState(false),
    [onboardingError, setOnboardingError] = useState(""),
    [batchId, setBatchId] = useState(""),
    [answerId, setAnswerId] = useState<number | null>(null);
  const projects = useData<Project[]>("projects", revision),
    batches = useData<Batch[]>(
      projectId ? `projects/${projectId}/batches` : null,
      revision,
    );
  useEffect(() => {
    try {
      const saved = localStorage.getItem("geo-project");
      if (saved && projects.data?.some((p) => String(p.id) === saved)) setProjectId(saved);
    } catch { /* Storage is optional; project selection remains available. */ }
  }, [projects.data]);
  const selectProject = (id: string) => {
    setProjectId(id);
    try { localStorage.setItem("geo-project", id); } catch { /* Optional local preference. */ }
  };
  const project = projects.data?.find((p) => String(p.id) === projectId);
  const current = areas.find((a) => a.id === area)!;
  const refresh = () => setRevision((r) => r + 1);
  const navigate = (next: string) => {
    setArea(next);
  };
  const openCreate = () => {
    setCreating(true);
    requestAnimationFrame(() => {
      const form = document.querySelector<HTMLElement>(".create-project");
      form?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
        block: "start",
      });
      form
        ?.querySelector<HTMLInputElement>('input[name="name"]')
        ?.focus({ preventScroll: true });
    });
  };
  const onBatch = (id: number) => {
    setBatchId(String(id));
    setAnswerId(null);
    setArea("observation");
    setObservation("answers");
  };
  const context = { projectId: project?.id ?? 0, revision, refresh, navigate };
  return (
    <div className="shell">
      <a className="skip" href="#workspace">
        跳至工作区
      </a>
      <aside className="sidebar">
        <div className="wordmark">
          GEO <span>工作台</span>
        </div>
        <p className="side-note">
          人定方向，Agent 执行<span>GOAL / REVIEW / EVIDENCE</span>
        </p>
        <nav aria-label="主导航">
          {areas.slice(0, 3).map((a, i) => (
            <button
              key={a.id}
              aria-current={area === a.id ? "page" : undefined}
              onClick={() => navigate(a.id)}
            >
              <span className="nav-index">0{i + 1}</span>
              {a.title}
            </button>
          ))}
        </nav>
        <details className="nav-reference">
          <summary>资料与高级工具</summary>
          <nav aria-label="资料与高级工具">
            {areas.slice(3).map((a) => (
              <button
                key={a.id}
                aria-current={area === a.id ? "page" : undefined}
                onClick={() => navigate(a.id)}
              >
                <span className="nav-index">／</span>
                {a.title}
              </button>
            ))}
          </nav>
        </details>
        <div className="side-footer">
          人工审核，不必逐步搬运。
          <br />
          发布需授权，成功有实证。
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <label>
            当前项目
            <select
              aria-label="当前项目"
              value={projectId}
              onChange={(e) => {
                selectProject(e.target.value);
                setBatchId("");
                setAnswerId(null);
                setObservation("metrics");
              }}
            >
              <option value="">选择项目</option>
              {projects.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} · {p.brand}
                </option>
              ))}
            </select>
          </label>
          <button
            className="secondary"
            onClick={() => (creating ? setCreating(false) : openCreate())}
          >
            {creating ? "关闭新建" : "新建项目"}
          </button>
          <button className="ghost" onClick={refresh}>
            刷新
          </button>
        </header>
        <main id="workspace">
          <div className="heading">
            <div>
              <p className="eyebrow">GEO / AGENT STUDIO</p>
              <h1>{current.title}</h1>
              <p>{current.note}</p>
            </div>
            <span className="chapter-number" aria-hidden="true">
              {String(areas.indexOf(current) + 1).padStart(2, "0")}
            </span>
          </div>
          <Load state={projects}>
            {!projects.data?.length && (
              <>
                <Prelude
                  title={
                    <>
                      让优化，
                      <br />
                      只把决定留给你。
                    </>
                  }
                  action={
                    <button onClick={openCreate}>告诉 Agent 你的品牌 ↗</button>
                  }
                >
                  提交业务目标，Agent 阅读官网、整理依据、提出计划与改稿。
                  <br />
                  你审核计划和成果；只有明确授权，才会对外发布。
                </Prelude>
                <div className="method-strip">
                  <div>
                    <span>01 / 给出方向</span>
                    <h3>目标，而非操作清单</h3>
                    <p>从品牌官网与业务目标开始；缺少模型时如实说明。</p>
                  </div>
                  <div>
                    <span>02 / 审核关键决定</span>
                    <h3>读成果，核对依据</h3>
                    <p>先审计划，再读改稿。反馈会产生新的待审版本。</p>
                  </div>
                  <div>
                    <span>03 / 授权之后</span>
                    <h3>自动交付，真实核验</h3>
                    <p>后台持续执行；核对全文并留存发布与维护证据。</p>
                  </div>
                </div>
              </>
            )}
            {onboardingError && <p role="alert" className="error">{onboardingError}</p>}
            {creating && (
              <section className="create-project">
                <Form
                  title="品牌、官网与第一个目标"
                  expanded
                  fields={[
                    { key: "name", label: "品牌名称", required: true },
                    { key: "website_url", label: "品牌官网", type: "url", required: true },
                    { key: "goal", label: "希望 Agent 完成的业务目标", type: "textarea", required: true },
                  ]}
                  submit="建立项目并交给 Agent"
                  onSubmit={async (body) => {
                    setOnboardingError("");
                    const p = await api("projects", "POST", { name: body.name, brand: body.name, website_url: body.website_url });
                    selectProject(String(p.id));
                    try { localStorage.setItem(`geo-goal-${p.id}`, body.goal); } catch { /* Optional goal recovery. */ }
                    try {
                      const capability = await api(`projects/${p.id}/agent-capabilities`);
                      if (capability.ready) {
                        await api(`projects/${p.id}/agent-runs`, "POST", { goal: body.goal });
                        try { localStorage.removeItem(`geo-goal-${p.id}`); } catch { /* Optional preference. */ }
                      }
                    } catch (error) {
                      setOnboardingError(`项目已建立，但 Agent 尚未启动：${error instanceof Error ? error.message : String(error)}。目标已保留，可在工作室重新提交。`);
                    } finally {
                      setCreating(false);
                      setArea("studio");
                      refresh();
                    }
                  }}
                />
              </section>
            )}
            {!project && (projects.data?.length ?? 0) > 0 && (
              <Empty>请选择顶部项目，开始处理真实优化与运营工作。</Empty>
            )}
            {project && (
              <div key={`${project.id}-${area}`}>
                {["studio", "reviews", "results"].includes(area) && <AgentStudio key={project.id} project={project} view={area} navigate={navigate} />}
                {area === "workbench" && <OperationsHome {...context} />}
                {area === "plans" && <Opportunities {...context} />}
                {area === "pages" && <PageOperations {...context} />}
                {area === "content" && <PublicationOperations {...context} />}
                {area === "research" && <ResearchOperations {...context} />}
                {area === "catalog" && (
                  <Catalog
                    project={project}
                    revision={revision}
                    refresh={refresh}
                  />
                )}
                {area === "observation" && (
                  <>
                    <div
                      className="observation-tabs"
                      role="navigation"
                      aria-label="观测与验收子区"
                    >
                      {observations.map((o) => (
                        <button
                          key={o.id}
                          aria-current={
                            observation === o.id ? "page" : undefined
                          }
                          onClick={() => setObservation(o.id)}
                        >
                          {o.title}
                        </button>
                      ))}
                    </div>
                    <p className="muted">
                      观测用于给运营行动提供依据与验收，不替代页面优化、审核和发布。
                    </p>
                    <div key={`${project.id}-${observation}`}>
                      {observation === "metrics" && (
                        <Overview
                          projectId={project.id}
                          batches={batches.data ?? []}
                          revision={revision}
                          onStart={() => setObservation("questions")}
                          openAnswer={(id) => {
                            setAnswerId(id);
                            setObservation("answers");
                          }}
                        />
                      )}
                      {observation === "questions" && (
                        <Questions
                          projectId={project.id}
                          revision={revision}
                          refresh={refresh}
                          onBatch={onBatch}
                        />
                      )}
                      {observation === "answers" && (
                        <Answers
                          batches={batches.data ?? []}
                          batchId={batchId}
                          setBatchId={setBatchId}
                          revision={revision}
                          refresh={refresh}
                          answerId={answerId}
                          setAnswerId={setAnswerId}
                        />
                      )}
                      {observation === "diagnoses" && (
                        <Actions
                          projectId={project.id}
                          batches={batches.data ?? []}
                          revision={revision}
                          refresh={refresh}
                          mode="diagnoses"
                        />
                      )}
                      {observation === "retest" && (
                        <Retest
                          projectId={project.id}
                          batches={batches.data ?? []}
                          revision={revision}
                          refresh={refresh}
                          onBatch={onBatch}
                        />
                      )}
                    </div>
                  </>
                )}
              </div>
            )}
          </Load>
          {batches.error && (
            <p role="alert" className="error">
              批次读取失败：{batches.error}
            </p>
          )}
          <footer>
            GEO Agent 工作室 · 发布不等于索引 · 观察不等于因果 · 原始证据留存
          </footer>
        </main>
      </div>
    </div>
  );
}
