"use client";

import { useMemo, useRef, useState } from "react";
import { api, Empty, LinkURL, Load, useData } from "./ui";

const metrics = ["impressions", "clicks", "leads", "orders"] as const;
const labels = { impressions: "曝光", clicks: "点击", leads: "线索", orders: "订单" };
const header = "date\tpage_url\tchannel\tquery\timpressions\tclicks\tleads\torders";
type Metric = (typeof metrics)[number];
type MeasurementRow = Record<Metric, number | null> & {
  date: string;
  page_url: string;
  channel: "seo" | "geo" | "other";
  query: string;
  id?: number;
  source_label?: string;
};
type MeasurementData = {
  rows: MeasurementRow[];
  summary: Record<Metric, number | null>;
  limitations: string[];
};

function parseTSV(input: string): { rows: MeasurementRow[]; errors: string[] } {
  const rows: MeasurementRow[] = [], errors: string[] = [];
  if (!input.trim()) return { rows, errors };
  const lines = input.replace(/^\uFEFF/, "").replace(/\r\n?/g, "\n").split("\n");
  while (lines.length && !lines[lines.length - 1].trim()) lines.pop();
  if (lines[0] !== header) {
    return { rows, errors: ["第 1 行表头不匹配：请使用下方完整表头，列之间必须为制表符（Tab），顺序不可更改。"] };
  }
  if (lines.length === 1) errors.push("请在表头后粘贴至少一条记录。");
  if (lines.length > 1001) return { rows, errors: ["每次最多导入 1000 条记录，请拆分后导入。"] };
  lines.slice(1).forEach((line, index) => {
    const lineNumber = index + 2;
    const cells = line.split("\t").map((cell) => cell.trim());
    const problems: string[] = [];
    if (cells.length !== 8) {
      errors.push(`第 ${lineNumber} 行：需要 8 列，实际 ${cells.length} 列；空指标也必须保留制表符。`);
      return;
    }
    const [date, page_url, channel, query] = cells;
    const parsedDate = new Date(`${date}T00:00:00Z`);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || date.startsWith("0000") ||
      !Number.isFinite(parsedDate.getTime()) || parsedDate.toISOString().slice(0, 10) !== date) {
      problems.push("date 必须是有效的 YYYY-MM-DD 日期");
    }
    try {
      const url = new URL(page_url);
      if (!/^https?:\/\//i.test(page_url) || !["http:", "https:"].includes(url.protocol)) throw new Error();
      if (url.username || url.password || /[\s\\]/.test(page_url) || page_url.length > 2048) throw new Error();
    } catch {
      problems.push("page_url 必须是完整的 http(s) 页面地址");
    }
    if (!["seo", "geo", "other"].includes(channel)) problems.push("channel 只能为 seo、geo 或 other（小写）");
    if (query.length > 2000) problems.push("query 最多 2000 字符");
    const values = {} as Record<Metric, number | null>;
    metrics.forEach((metric, metricIndex) => {
      const raw = cells[metricIndex + 4];
      if (raw === "") values[metric] = null;
      else if (!/^\d+$/.test(raw) || !Number.isSafeInteger(Number(raw))) {
        problems.push(`${metric} 必须留空或填写非负安全整数（不含逗号、小数、单位）`);
      } else values[metric] = Number(raw);
    });
    if (problems.length) errors.push(`第 ${lineNumber} 行：${problems.join("；")}。`);
    else rows.push({ date, page_url, channel: channel as MeasurementRow["channel"], query, ...values });
  });
  return { rows, errors };
}

const displayNumber = (value: number | null | undefined) => value == null ? "未知" : value.toLocaleString("zh-CN");

function Records({ rows, preview = false }: { rows: MeasurementRow[]; preview?: boolean }) {
  return (
    <div className="table-wrap" tabIndex={0} role="region" aria-label={preview ? "导入预览表" : "测量记录表"}>
      <table>
        <caption>{preview ? "待导入记录（尚未保存）" : "已保存的测量记录"}</caption>
        <thead><tr>
          <th scope="col">日期</th><th scope="col">页面</th><th scope="col">渠道</th><th scope="col">查询词</th>
          {metrics.map((metric) => <th scope="col" key={metric}>{labels[metric]}</th>)}
          {!preview && <th scope="col">数据来源</th>}
        </tr></thead>
        <tbody>{rows.map((row, index) => (
          <tr key={row.id ?? index}>
            <td>{row.date}</td><td><LinkURL url={row.page_url} /></td>
            <td>{row.channel === "other" ? "其他" : row.channel.toUpperCase()}</td><td>{row.query || "未提供"}</td>
            {metrics.map((metric) => <td key={metric}>{displayNumber(row[metric])}</td>)}
            {!preview && <td>{row.source_label || "未提供"}</td>}
          </tr>
        ))}</tbody>
      </table>
    </div>
  );
}

export function Measurement(props: { projectId: number; revision: number; refresh: () => void }) {
  return <MeasurementProject key={props.projectId} {...props} />;
}

function MeasurementProject({ projectId, revision, refresh }: { projectId: number; revision: number; refresh: () => void }) {
  const [reload, setReload] = useState(0);
  const state = useData<MeasurementData>(`projects/${projectId}/measurements`, revision + reload);
  const [source, setSource] = useState("");
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const submitting = useRef(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [channelFilter, setChannelFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const filteredRows = (state.data?.rows ?? []).filter(row =>
    (!channelFilter || row.channel === channelFilter) && (!sourceFilter || row.source_label === sourceFilter) &&
    (!dateFrom || row.date >= dateFrom) && (!dateTo || row.date <= dateTo));
  const filteredSummary = Object.fromEntries(metrics.map(metric => {
    const values = filteredRows.map(row => row[metric]);
    const total = values.reduce<number>((sum, value) => sum + (value ?? 0), 0);
    return [metric, values.length && values.every(value => value != null) && Number.isSafeInteger(total) ? total : null];
  })) as Record<Metric, number | null>;
  const parsed = useMemo(() => parseTSV(input), [input]);
  const ready = source.trim().length > 0 && parsed.rows.length > 0 && parsed.errors.length === 0;

  return (
    <>
      <section className="card">
        <h2>效果测量</h2>
        <p className="muted">汇集真实的 SEO、GEO 及其他渠道数据，按已导入记录查看曝光、点击、线索与订单。</p>
        <button type="button" className="secondary" disabled={state.loading} onClick={() => setReload((value) => value + 1)}>
          {state.loading ? "正在读取…" : "刷新测量数据"}
        </button>
        <Load state={state}>
          {state.data && <>
            <div className="fields">
              <label><span>渠道</span><select value={channelFilter} onChange={e => setChannelFilter(e.target.value)}><option value="">全部渠道</option><option value="seo">SEO</option><option value="geo">GEO</option><option value="other">其他</option></select></label>
              <label><span>来源</span><select value={sourceFilter} onChange={e => setSourceFilter(e.target.value)}><option value="">全部来源</option>{[...new Set(state.data.rows.map(r => r.source_label).filter(Boolean))].map(s => <option key={s} value={s}>{s}</option>)}</select></label>
              <label><span>开始日期</span><input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} /></label>
              <label><span>结束日期</span><input type="date" value={dateTo} min={dateFrom || undefined} onChange={e => setDateTo(e.target.value)} /></label>
            </div>
            <div className="metrics">
              {metrics.map((metric) => <div className={`metric ${filteredSummary[metric] == null ? "is-unknown" : ""}`} key={metric}>
                <span>{labels[metric]}合计</span>
                <strong>{displayNumber(filteredSummary[metric])}</strong>
                <small>当前筛选 · {filteredRows.filter(r => r[metric] != null).length}/{filteredRows.length} 条已知</small>
              </div>)}
            </div>
            <p className="muted">未知不等于 0；合计仅反映已提供的观测值，不代表完整流量或因果增长。请避免重复导入及统计口径重叠。</p>
            {state.data.limitations.length > 0 && <aside className="notice" aria-label="数据局限">
              <h3>数据局限</h3>
              <ul>{state.data.limitations.map((limitation, index) => <li key={index}>{limitation}</li>)}</ul>
            </aside>}
            <h3>测量记录 · {filteredRows.length} / {state.data.rows.length} 条</h3>
            {filteredRows.length ? <Records rows={filteredRows.slice(0, 200)} /> : <Empty>{state.data.rows.length ? "当前筛选没有记录。" : "尚未导入测量数据。请在下方粘贴真实记录并注明来源。"}</Empty>}
            {filteredRows.length > 200 && <p>表格展示前 200 条，指标按当前筛选的全部 {filteredRows.length} 条计算。</p>}
          </>}
        </Load>
      </section>

      <section className="card">
        <h2>粘贴导入 TSV</h2>
        <p>从表格复制以下 8 列，第一行必须与下方表头完全一致（列之间为 Tab，而非逗号）。每行一条记录，单元格内不能包含 Tab 或换行。</p>
        <pre aria-label="TSV 标准表头">{header}</pre>
        <p className="muted">date：YYYY-MM-DD；page_url：完整 http(s) 地址；channel：seo / geo / other；query：查询词，可留空。四项指标只接受非负整数；留空表示未知（null），明确观察到零才填 0，末尾空列也要保留 Tab。</p>
        <form className="form" onSubmit={async (event) => {
          event.preventDefault();
          if (submitting.current) return;
          setError("");
          setMessage("");
          if (!ready) {
            setError("请填写数据来源，并修正所有 TSV 错误后再提交。");
            return;
          }
          submitting.current = true;
          setBusy(true);
          try {
            const result = await api(`projects/${projectId}/measurements/import`, "POST", { source_label: source.trim(), rows: parsed.rows });
            setMessage(`新增 ${result.imported} 条，跳过 ${result.duplicates} 条重复记录。`);
            setInput("");
            setReload((value) => value + 1);
            refresh();
          } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
          } finally {
            submitting.current = false;
            setBusy(false);
          }
        }}>
          <label>
            <span>数据来源 / 报表口径 *</span>
            <input required maxLength={200} value={source} disabled={busy} placeholder="例如：Search Console · 站点A · 网页搜索 · 查询词维度" onChange={(event) => { setSource(event.target.value); setMessage(""); setError(""); }} />
            <small>同一来源与统计口径请保持名称一致，便于去重。不要填写密码或密钥；不同维度的合计可能重叠。</small>
          </label>
          <label>
            <span>TSV 内容（含表头）*</span>
            <textarea required rows={9} value={input} disabled={busy} spellCheck={false} placeholder={header} onChange={(event) => { setInput(event.target.value); setMessage(""); setError(""); }} />
          </label>
          {parsed.errors.length > 0 && <div className="error" role="alert">
            <p>发现 {parsed.errors.length} 项错误，整批不会提交：</p>
            <ul>{parsed.errors.map((problem, index) => <li key={index}>{problem}</li>)}</ul>
          </div>}
          {parsed.rows.length > 0 && <div>
            <h3>导入预览 · {parsed.rows.length} 条有效记录</h3>
            <p>来源：{source.trim() || "尚未填写（必填）"}。{parsed.errors.length ? "请先修正全部错误。" : "请核对内容后点击确认导入。"}</p>
            <Records rows={parsed.rows.slice(0, 100)} preview />
            {parsed.rows.length > 100 && <p className="muted">预览显示前 100 条；提交将导入全部 {parsed.rows.length} 条有效记录。</p>}
          </div>}
          <button type="submit" disabled={busy || !ready}>{busy ? "正在导入…" : `确认导入${parsed.rows.length ? ` ${parsed.rows.length} 条记录` : ""}`}</button>
          {error && <p className="error" role="alert">{error}</p>}
          {message && <p className="success" role="status">{message}</p>}
        </form>
      </section>
    </>
  );
}
