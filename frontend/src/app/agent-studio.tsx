"use client";
import { useEffect, useRef, useState } from "react";
import { api, Empty, Json, LinkURL, Load, type Row } from "./ui";
import type { Project } from "./types";

type Capability = { ready: boolean; model_ready: boolean; website_ready: boolean; publishing_ready: boolean; sampling_ready: boolean; worker_ready: boolean; reasons: string[]; publishing_reasons: string[]; sampling_reasons: string[] };
type Draft = { page_id: number; content_version_id: number; target_url: string; title: string; before_text: string; after_text: string; body_hash: string; facts_snapshot: Row[]; generation: Row; source_url: string; expected_change: string; acceptance_method: string; publishing_blocked_reason: string; wp_baseline: Row | null };
type Proposal = { id: number; kind: string; revision: number; status: string; summary: string; plan: { summary: string; targets: Row[]; limitations: string[]; sampling: { requested: boolean; reason: string } } | null; drafts: Draft[]; created_at: string };
type Run = { id: number; project_id: number; goal: string; policy: { max_pages: number; max_model_requests: number; review_interval_days: number; sample: boolean; continuous_maintenance: boolean }; status: string; phase: string; blocked_reason: string; can_resume: boolean; updated_at: string; steps: Row[]; proposals: Proposal[]; approvals: Row[]; current_proposal: Proposal | null; outcomes: Row[] };
const labels: Record<string, string> = { queued: "已排队", running: "执行中", awaiting_review: "等待你审核", blocked: "需要处理阻碍", failed: "执行失败", cancelled: "已取消", completed: "已完成", verified: "页面全文已核验", pending: "待审核", approved: "已批准", request_changes: "已退回修改", rejected: "已拒绝", superseded: "已被新版替代", approve: "批准计划", approve_only: "仅批准内容", approve_and_publish: "批准并授权发布", publication_authorization: "等待发布授权", plan: "计划", drafts: "改稿" };
const phases: Record<string, string> = { context: "读取官网与发现相关页面", plan: "整理依据并提出计划", materialize: "按已批准计划安排任务与事实", draft: "生成待审改稿", authorization: "准备当前资源基准，等待发布授权", publish: "执行已授权发布与全文核验", finish: "整理成果与维护安排" };
const label = (value: string) => labels[value] ?? value;
const date = (value: string) => new Date(value).toLocaleString("zh-CN", { hour12: false });

export function AgentStudio({ project, view, navigate }: { project: Project; view: string; navigate: (view: string) => void }) {
  const [runs, setRuns] = useState<Run[] | null>(null), [cap, setCap] = useState<Capability | null>(null), [error, setError] = useState(""), [selected, setSelected] = useState<number | null>(null), [detail, setDetail] = useState<Run | null>(null), [revision, setRevision] = useState(0), [busy, setBusy] = useState(false), [goal, setGoal] = useState("");
  const [mutationError, setMutationError] = useState("");
  const [maxPages, setMaxPages] = useState(2), [sample, setSample] = useState(false), [maintenance, setMaintenance] = useState(false), [interval, setInterval] = useState(30);
  const active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);
  useEffect(() => { try { setGoal(localStorage.getItem(`geo-goal-${project.id}`) || ""); } catch { /* Optional draft recovery. */ } }, [project.id]);
  useEffect(() => {
    const controller = new AbortController();
    let timer: number;
    const poll = async () => {
      try {
        const [next, capability] = await Promise.all([api(`projects/${project.id}/agent-runs`, "GET", undefined, controller.signal), api(`projects/${project.id}/agent-capabilities`, "GET", undefined, controller.signal)]);
        if (controller.signal.aborted) return;
        setRuns(next); setCap(capability); setError("");
        timer = window.setTimeout(poll, next.some((r: Run) => ["queued", "running"].includes(r.status)) ? 2500 : 15000);
      } catch (e) {
        if (!controller.signal.aborted) { setError(e instanceof Error ? e.message : String(e)); timer = window.setTimeout(poll, 15000); }
      }
    };
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [project.id, revision]);
  const visible = (runs ?? []).filter((run) => view === "reviews" ? run.status === "awaiting_review" : view === "results" ? run.outcomes.length > 0 || ["completed", "cancelled", "failed"].includes(run.status) : true);
  const selectedRun = visible.find((r) => r.id === selected) ?? visible[0];
  useEffect(() => {
    setDetail(null);
    if (!selectedRun) return;
    const controller = new AbortController();
    let timer: number;
    const poll = async () => {
      try {
        const value = await api(`agent-runs/${selectedRun.id}`, "GET", undefined, controller.signal);
        if (controller.signal.aborted) return;
        setDetail(value); setError("");
        timer = window.setTimeout(poll, ["queued", "running"].includes(value.status) ? 2000 : 12000);
      } catch (e) { if (!controller.signal.aborted) { setError(e instanceof Error ? e.message : String(e)); timer = window.setTimeout(poll, 12000); } }
    };
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [selectedRun?.id, selectedRun?.status, revision]);
  const refresh = () => setRevision((v) => v + 1);
  const mutate = async (path: string, body?: unknown) => {
    setBusy(true); setMutationError("");
    try {
      const result = await api(path, "POST", body);
      if (active.current) { setDetail(result); setSelected(result.id); refresh(); }
      return result;
    } catch (e) { if (active.current) setMutationError(e instanceof Error ? e.message : String(e)); throw e; }
    finally { if (active.current) setBusy(false); }
  };
  return <div className="agent-studio">
    {view === "studio" && <details className="agent-goal" open={runs?.length === 0 || undefined}>
      <summary>{runs?.length ? "给 Agent 一个新目标" : "从一个业务目标开始"}</summary>
      <div><p className="eyebrow">你的方向 / AGENT 的工作</p><h2>下一步，想让客户更理解什么？</h2><p>Agent 将阅读 {project.brand} 的官网，提出有出处的计划。你审核后，它继续改稿；未经发布授权，不会改动站点。</p><LinkURL url={project.website_url} /></div>
      <form onSubmit={async (e) => { e.preventDefault(); if (busy || !cap?.ready) return; try { await mutate(`projects/${project.id}/agent-runs`, { goal, policy: { max_pages: maxPages, sample: cap.sampling_ready && sample, continuous_maintenance: maintenance, review_interval_days: interval } }); setGoal(""); try { localStorage.removeItem(`geo-goal-${project.id}`); } catch { /* Optional preference. */ } } catch { /* Error displayed below. */ } }}>
        <label htmlFor="agent-goal">业务目标</label><textarea id="agent-goal" required minLength={3} value={goal} onChange={(e) => setGoal(e.target.value)} placeholder="例如：让采购者从服务页看懂我们的适用场景和服务边界，减少售前反复解释。" rows={3} />
        <details className="agent-scope"><summary>本轮范围与授权</summary>
          <label>本轮优化页面<select value={maxPages} onChange={(e) => setMaxPages(Number(e.target.value))}><option value={1}>聚焦 1 页</option><option value={2}>最多 2 页（默认）</option><option value={3}>最多 3 页</option></select></label>
          <p className="muted">仅在当前品牌官网范围内发现页面，不递归整站抓取。每轮最多 8 次真实模型请求；不自动重试不确定的计费请求。</p>
          {cap?.sampling_ready ? <label className="agent-check"><input type="checkbox" checked={sample} onChange={(e) => setSample(e.target.checked)} />申请发布前后采样验收（计划审核后才采集，可能产生费用）</label> : <p className="muted">采样验收未就绪：{cap?.sampling_reasons.join("；") || "需先配置可用的回答采集来源。"}</p>}
          <label className="agent-check"><input type="checkbox" checked={maintenance} onChange={(e) => setMaintenance(e.target.checked)} />申请持续维护：到期自动读取页面，生成新的待审计划，不自动发布</label>
          {maintenance && <label>维护间隔（天）<input type="number" min={1} max={365} required value={interval} onChange={(e) => setInterval(Number(e.target.value))} /></label>}
          <p className="muted">采样与周期访问默认关闭；以上申请会在计划审核时再次展示，由你授权。</p>
        </details>
        <div className="agent-goal-submit"><small>自动阅读与规划 → 你审计划 → 自动改稿 → 你审成果</small><button disabled={busy || !cap?.ready}>{busy ? "正在提交目标…" : "交给 Agent ↗"}</button></div>
      </form>
    </details>}
    {cap && !cap.ready && <section className="agent-blocked" role="status"><strong>Agent 未就绪</strong><p>{cap.reasons.join("；") || "需服务器配置模型与官网后再开始。"}</p><p>请由服务器管理员完成配置，再<button className="ghost" onClick={refresh}>检查就绪状态</button>。无需在浏览器输入模型密钥。</p>{!cap.website_ready && <button className="secondary" onClick={() => navigate("catalog")}>完善品牌官网</button>}</section>}
    {error && <div role="alert" className="error">{error} <button className="secondary" onClick={refresh}>重新读取状态</button></div>}
    {mutationError && <div role="alert" className="error">本次操作未确认成功：{mutationError}。请先读取服务器状态，避免重复提交。<button className="secondary" onClick={refresh}>读取服务器状态</button></div>}
    <Load state={{ data: runs, error: "", loading: runs === null }}>
      {!visible.length && <Empty>{view === "reviews" ? "目前没有需要审核的提案。Agent 完成计划或改稿后会停在这里等你，不会越过授权。" : view === "results" ? "还没有交付记录。完成审核后，这里保留内容、发布核验与维护安排，不把目标当成效果。" : "这里还没有 Agent 任务。给出一个目标后，真实执行步骤和下一个审核点会出现在这里。"}</Empty>}
      {visible.length > 0 && <div className="agent-workspace">
        {visible.length > 1 && <label className="agent-mobile-picker">切换目标<select value={selectedRun?.id} onChange={(e) => setSelected(Number(e.target.value))}>{visible.map((run) => <option key={run.id} value={run.id}>{label(run.status)} · {run.goal}</option>)}</select></label>}
        <section className="agent-run-list" aria-label="Agent 任务"><p className="eyebrow">{view === "reviews" ? "等你决定" : view === "results" ? "交付档案" : "执行中的目标与历史"}</p>{visible.map((run) => <button key={run.id} className="agent-run" aria-current={selectedRun?.id === run.id ? "true" : undefined} onClick={() => setSelected(run.id)}><span className={`agent-status ${run.status}`}>{label(run.status)}</span><strong>{run.goal}</strong><small>{date(run.updated_at)}</small></button>)}</section>
        <section className="agent-run-detail" aria-label="任务详情">{detail && detail.id === selectedRun?.id ? <>
          {detail.status === "awaiting_review" ? <div className="agent-review-context"><span className="agent-status awaiting_review">等待你审核</span><p>目标：{detail.goal}</p></div> : <><div className="section-toolbar"><div><p className="eyebrow">持久执行 / 可随时离开</p><h2>{detail.goal}</h2></div><span className={`agent-status ${detail.status}`}>{label(detail.status)}</span></div><p className="agent-current"><strong>当前步骤</strong> {detail.steps.findLast((s) => s.status === "running")?.summary || detail.steps.at(-1)?.summary || phases[detail.phase] || "等待后台开始下一步骤"}</p></>}
          {detail.blocked_reason && <div className="agent-blocked"><strong>{label(detail.status)}</strong><p>{detail.blocked_reason}</p><p>不会伪造成果或自动重试不确定的外部写入。请先处理原因。</p><button className="secondary" onClick={() => navigate("content")}>查看发布配置与外部发布工具</button>{detail.can_resume && <button disabled={busy} onClick={() => { void mutate(`agent-runs/${detail.id}/resume`).catch(() => {}); }}>原因已处理，安全继续</button>}</div>}
          {detail.can_resume && !detail.blocked_reason && <p className="notice">配置修复后，可重新读取资源基准并生成新的授权提案。<button disabled={busy} onClick={() => { void mutate(`agent-runs/${detail.id}/resume`).catch(() => {}); }}>配置已就绪，继续准备提案</button></p>}
          {detail.current_proposal && (view === "results" ? <details className="agent-history"><summary>查看本次完整提案与改稿</summary><ProposalBody proposal={detail.current_proposal} /></details> : <Review key={detail.current_proposal.id} run={detail} proposal={detail.current_proposal} busy={busy} submit={(body) => mutate(`agent-runs/${detail.id}/approvals`, body)} />)}
          {detail.outcomes.length > 0 && <section className="agent-outcomes"><p className="eyebrow">交付 / 不把执行当效果</p><h3>成果与维护安排</h3>{detail.outcomes.map((outcome, i) => <article key={i}><span className="agent-status">{label(outcome.status)}</span><p><LinkURL url={outcome.target_url} /></p><p>{outcome.reason}</p><dl><dt>正文核验</dt><dd>{outcome.verified_at ? date(outcome.verified_at) : "尚未完成"}</dd><dt>下次维护</dt><dd>{outcome.next_review_at ? date(outcome.next_review_at) : "尚未安排"}</dd></dl></article>)}<p className="muted">页面全文核验只证明采集时的可见正文。索引、AI 引用与业务效果仍需后续真实观测。</p></section>}
          <details className="agent-history"><summary>执行记录与审核历史 · {detail.steps.length} 个步骤</summary><ol className="agent-timeline">{detail.steps.map((step) => <li key={step.id}><strong>{step.summary || step.kind}</strong><span>{label(step.status)}</span>{step.error && <p className="error">{step.error}</p>}<Json value={step.output} title="查看执行依据（非内部思考）" /></li>)}</ol>{detail.approvals.map((approval) => <article className="margin-note" key={approval.id}><strong>{label(approval.decision)} · {approval.reviewer}</strong><p>{approval.feedback}</p><small>{date(approval.created_at)}</small></article>)}{detail.proposals.filter((p) => p.id !== detail.current_proposal?.id).map((p) => <details key={p.id}><summary>{label(p.kind)} · 修订 {p.revision} · {label(p.status)}</summary><ProposalBody proposal={p} /></details>)}</details>
          {!["completed", "cancelled", "failed"].includes(detail.status) && <details className="agent-cancel"><summary>停止后续执行</summary><p>取消会阻止后续步骤，但不能回滚已经开始或完成的外部发布。</p><button className="danger" disabled={busy} onClick={() => { void mutate(`agent-runs/${detail.id}/cancel`).catch(() => {}); }}>确认取消后续步骤</button></details>}
        </> : <p role="status">正在读取此任务的持久状态…</p>}</section>
      </div>}
    </Load>
  </div>;
}

function ProposalBody({ proposal }: { proposal: Proposal }) {
  return <>{proposal.plan && <><p className="agent-proposal-summary">{proposal.summary}</p>
    {proposal.plan.targets.map((target, i) => <article className="agent-target" key={i}><p className="eyebrow">计划 / {String(i + 1).padStart(2, "0")}</p><h3>{target.title}</h3><LinkURL url={target.target_url} /><p><strong>客户问题</strong> {target.question}</p><p><strong>内容缺口</strong> {target.content_gap}</p><p><strong>预期改动</strong> {target.expected_change}</p><p><strong>验收方式</strong> {target.acceptance_method}</p>{target.hypothesis && <p className="notice">待验证假设：{target.hypothesis}</p>}
      {target.judgment_basis && <details><summary>模型主观判断，非实测</summary><p>业务价值 {target.business_value}/5 · 业务适配 {target.business_fit}/5</p><p>{target.judgment_basis}</p><p>问题意图：{target.intent} · {target.branded ? "带品牌问题" : "不带品牌问题"}</p></details>}
      <div className="evidence-notes"><h4>精确来源</h4>{target.evidence.map((item: Row, j: number) => <figure key={j}><blockquote>{item.quote}</blockquote><figcaption><LinkURL url={item.url} /> · 原文字符 {item.start}–{item.end}</figcaption></figure>)}</div>
      {target.fact_candidates.length > 0 && <div className="agent-candidates"><h4>请确认的新事实候选</h4><p>网站宣称尚未核实；批准计划即确认采纳以下事实候选。</p>{target.fact_candidates.map((fact: Row, j: number) => <article key={j}><blockquote>{fact.quote}</blockquote><LinkURL url={fact.source_url} /><small>原文字符 {fact.start}–{fact.end}</small></article>)}</div>}</article>)}
    <div className="margin-note"><strong>边界与风险</strong><ul>{proposal.plan.limitations.map((item, i) => <li key={i}>{item}</li>)}</ul>{proposal.plan.sampling.requested && <p>本计划申请采样授权：{proposal.plan.sampling.reason}。批准计划会触发真实采集。</p>}</div>
  </>}{proposal.drafts.map((draft) => <article className="agent-target" key={draft.content_version_id}><p className="eyebrow">不可变改稿 / 逐页审核</p><h3>{draft.title}</h3><LinkURL url={draft.target_url} /><p>{draft.expected_change}</p>
    <p className="muted">以下比较采集到的页面可见正文与拟更新内容，不是 CMS 完整源代码或结构差异。</p>
    <div className="agent-comparison"><section><h4>采集时页面正文</h4><pre className="answer-text">{draft.before_text}</pre></section><section><h4>拟更新正文</h4><pre className="answer-text">{draft.after_text}</pre></section></div>
    <div className="review-facts"><h4>本稿事实与出处</h4>{draft.facts_snapshot.map((fact, i) => <article key={i}><p>{fact.claim}</p><LinkURL url={fact.source_url} /></article>)}<p>页面快照来源：<LinkURL url={draft.source_url} /></p></div><p><strong>验收方式</strong> {draft.acceptance_method}</p>{draft.publishing_blocked_reason && <p className="agent-blocked">发布阻碍：{draft.publishing_blocked_reason}。可以仅批准内容；外部人工发布后仍须核验。</p>}<Json value={{ content_version_id: draft.content_version_id, body_hash: draft.body_hash, generation: draft.generation }} title="高级：不可变版本、正文哈希与引文定位" /></article>)}</>;
}

function Review({ run, proposal, busy, submit }: { run: Run; proposal: Proposal; busy: boolean; submit: (body: unknown) => Promise<unknown> }) {
  const [reviewer, setReviewer] = useState("本地审核人"), [feedback, setFeedback] = useState(""), [mode, setMode] = useState("");
  useEffect(() => { try { setReviewer(localStorage.getItem("geo-reviewer") || "本地审核人"); } catch { /* Local identity is optional. */ } }, []);
  const approve = async (decision: string) => {
    if (busy) return;
    const publishing = decision === "approve_and_publish";
    try {
      await submit({
        proposal_id: proposal.id, decision, reviewer: reviewer.trim() || "本地审核人",
        feedback: ["request_changes", "reject"].includes(decision) ? feedback.trim() : decision === "approve" ? "已审阅完整计划、精确来源及新事实候选，批准计划并授权自动改稿；不授权发布。" : publishing ? "已审阅完整正文、标题、来源与全部目标 URL，明确授权发布本次不可变修订并自动核验全文。" : "已审阅完整正文与来源，仅批准当前内容，不授权对外发布。",
        allow_publish: publishing,
        bindings: publishing ? proposal.drafts.map((d) => ({ page_id: d.page_id, content_version_id: d.content_version_id, target_url: d.target_url, body_hash: d.body_hash, title: d.title })) : [],
      });
    } catch { /* Server failure remains visible in workspace. */ }
  };
  const scope = proposal.kind === "plan" && <p className="notice">本轮最多 {run.policy.max_pages} 页、{run.policy.max_model_requests} 次模型请求。{run.policy.continuous_maintenance ? `批准计划还将授权每 ${run.policy.review_interval_days} 天自动访问官网并生成新待审计划；不自动发布。` : "未申请持续维护，不授权周期访问。"}</p>;
  return <section className="agent-proposal"><div className="agent-review-caption"><span>{proposal.kind === "plan" ? "核对计划与事实候选，批准后自动改稿。" : proposal.kind === "publication_authorization" ? "内容已批准，等待明确发布授权。" : "核对正文与来源，再决定是否授权发布。"}</span><small>修订 {proposal.revision}</small></div><ProposalBody proposal={proposal} />
    {scope}
    {run.status === "awaiting_review" && proposal.status === "pending" && <section className="agent-decision">
      <p className="muted">以「{reviewer || "本地审核人"}」记录本次审核。旧批准不授权新修订。</p>
      <div className="agent-decision-buttons">
        {proposal.kind === "plan" ? <button disabled={busy} onClick={() => void approve("approve")}>批准计划，继续改稿</button> : <>{proposal.kind !== "publication_authorization" && <button className="secondary" disabled={busy} onClick={() => void approve("approve_only")}>仅批准内容</button>}<button disabled={busy || proposal.drafts.some((d) => !d.wp_baseline || Boolean(d.publishing_blocked_reason))} onClick={() => setMode("publish")}>批准并授权发布</button></>}
        <button className="secondary" disabled={busy} onClick={() => setMode("request_changes")}>退回修改</button><button className="ghost" disabled={busy} onClick={() => setMode("reject")}>拒绝</button>
      </div>
      {proposal.drafts.some((d) => !d.wp_baseline) && <p className="notice">尚未取得 WordPress 原资源基准，不能授权覆盖。请在高级发布工具配置对应资源；仅批准内容不会外发。</p>}
      {mode === "publish" && <div className="agent-consent"><strong>明确授权外部写入</strong><p>将以上 {proposal.drafts.length} 页的标题与拟更新正文写入对应目标 URL 的既有 WordPress 资源，再自动 GET 全文核验；不会创建新页面。若原站内容已变化或缺少配置，后端会阻塞，而不是覆盖或假报成功。</p><button disabled={busy} onClick={() => void approve("approve_and_publish")}>{busy ? "正在提交…" : "确认授权本次修订并自动发布"}</button><button className="ghost" disabled={busy} onClick={() => setMode("")}>暂不发布</button></div>}
      {["request_changes", "reject"].includes(mode) && <form onSubmit={(e) => { e.preventDefault(); if (feedback.trim()) void approve(mode); }}><label>{mode === "request_changes" ? "给 Agent 的修改意见" : "拒绝原因"}<textarea required value={feedback} onChange={(e) => setFeedback(e.target.value)} rows={3} /></label><p className="muted">{mode === "request_changes" ? "Agent 将依据反馈产生新的不可变提案，旧版本可追溯，新稿仍需审核。" : "拒绝停止后续执行，不能撤回已开始或完成的发布。"}</p><button disabled={busy || !feedback.trim()}>{busy ? "正在提交…" : mode === "request_changes" ? "发送反馈，生成新提案" : "提交拒绝意见"}</button></form>}
      <details><summary>审核身份设置</summary><label>本地审核人<input value={reviewer} onChange={(e) => { setReviewer(e.target.value); try { localStorage.setItem("geo-reviewer", e.target.value); } catch { /* Optional preference. */ } }} /></label><small>身份仅作本地审计标记，不代表登录认证。</small></details>
    </section>}
  </section>;
}
