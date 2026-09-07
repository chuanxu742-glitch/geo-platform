"use client";
import { useEffect, useRef, useState, type ReactNode } from "react";
export type Row = Record<string, any>; // API records retain evolving analysis/evidence payloads.
export async function api(
  path: string,
  method = "GET",
  body?: unknown,
  signal?: AbortSignal,
): Promise<any> {
  const response = await fetch(`/api/backend/${path}`, {
    method,
    signal,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = response.status === 204 ? null : await response.json();
  if (!response.ok)
    throw new Error(
      typeof data?.detail === "string"
        ? data.detail
        : JSON.stringify(data?.detail ?? data),
    );
  return data;
}
export type DataState<T = Row> = {
  data: T | null;
  error: string;
  loading: boolean;
};
export function useData<T = Row>(
  path: string | null,
  revision = 0,
): DataState<T> {
  const [data, setData] = useState<T | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(false);
  const previousPath = useRef<string | null>(null);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    if (previousPath.current !== path) setData(null);
    previousPath.current = path;
    setError("");
    if (!path) {
      setLoading(false);
      return;
    }
    setLoading(true);
    api(path, "GET", undefined, controller.signal)
      .then((value) => {
        if (active) setData(value);
      })
      .catch((error) => {
        if (active) setError(error.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [path, revision]);
  return { data, error, loading };
}
export function Load({
  state,
  children,
}: {
  state: { data: unknown; error: string; loading: boolean };
  children: ReactNode;
}) {
  return state.loading && state.data == null ? (
    <p role="status">正在读取…</p>
  ) : state.error ? (
    <p role="alert" className="error">
      {state.error}
    </p>
  ) : (
    <>{children}</>
  );
}
export type Field = {
  key: string;
  label: string;
  type?:
    | "textarea"
    | "json"
    | "list"
    | "ids"
    | "url"
    | "datetime-local"
    | "number"
    | "checkbox";
  multiple?: boolean;
  required?: boolean;
  options?: { value: string; label: string }[];
  hint?: string;
};
export function Form({
  title,
  fields,
  initial = {},
  submit,
  onSubmit,
  expanded = false,
}: {
  title: string;
  fields: Field[];
  initial?: Row;
  submit: string;
  onSubmit: (body: Row) => Promise<unknown>;
  expanded?: boolean;
}) {
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState(""),
    [error, setError] = useState("");
  return (
    <details className="form-disclosure" open={expanded || undefined}>
      <summary>
        <span>{title}</span>
        <span className="disclosure-action disclosure-closed">
          展开操作 <span aria-hidden="true">＋</span>
        </span>
        <span className="disclosure-action disclosure-open">
          收起操作 <span aria-hidden="true">−</span>
        </span>
      </summary>
      <form
        className="form"
        onSubmit={async (event) => {
          event.preventDefault();
          const form = event.currentTarget;
          setBusy(true);
          setMessage("");
          setError("");
          try {
            const values = new FormData(form);
            const body: Row = {};
            for (const f of fields) {
              const raw = String(values.get(f.key) ?? "").trim();
              if (f.type === "checkbox") body[f.key] = values.has(f.key);
              else if (f.type === "json")
                body[f.key] = raw ? JSON.parse(raw) : {};
              else if (f.type === "list")
                body[f.key] = raw
                  .split(/[,，\n]/)
                  .map((s) => s.trim())
                  .filter(Boolean);
              else if (f.type === "ids") {
                body[f.key] = f.options
                  ? values.getAll(f.key).map(Number)
                  : raw
                    ? raw.split(/[,，\s]+/).map(Number)
                    : [];
                if (
                  body[f.key].some(
                    (n: number) => !Number.isInteger(n) || n <= 0,
                  )
                )
                  throw new Error(`${f.label}须为正整数 ID，以逗号分隔`);
              } else if (f.type === "number") {
                if (raw) body[f.key] = Number(raw);
              } else if (f.type === "datetime-local")
                body[f.key] = raw ? new Date(raw).toISOString() : null;
              else body[f.key] = raw;
            }
            await onSubmit(body);
            setMessage("已保存。");
          } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
          } finally {
            setBusy(false);
          }
        }}
      >
        <h3>{title}</h3>
        <div className="fields">
          {fields.map((f) => {
            const value = initial[f.key];
            const def =
              f.type === "json"
                ? JSON.stringify(value ?? {}, null, 2)
                : Array.isArray(value)
                  ? value.join(", ")
                  : f.type === "datetime-local" && value
                    ? new Date(
                        new Date(value).getTime() -
                          new Date(value).getTimezoneOffset() * 60000,
                      )
                        .toISOString()
                        .slice(0, 16)
                    : (value ?? "");
            return (
              <label
                key={f.key}
                className={
                  f.type === "textarea" || f.type === "json" ? "wide" : ""
                }
              >
                <span>
                  {f.label}
                  {f.required ? " *" : ""}
                </span>
                {f.options ? (
                  <>
                    <select
                      name={f.key}
                      multiple={f.multiple}
                      defaultValue={
                        f.multiple
                          ? Array.isArray(value)
                            ? value.map(String)
                            : []
                          : def
                      }
                      required={f.required}
                      size={
                        f.multiple
                          ? Math.min(6, Math.max(3, f.options.length))
                          : undefined
                      }
                    >
                      {f.options.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                    {f.multiple && (
                      <small>
                        可多选：按住 Ctrl / Command 点击；未选择表示不关联。
                      </small>
                    )}
                  </>
                ) : f.type === "textarea" || f.type === "json" ? (
                  <textarea
                    name={f.key}
                    defaultValue={def}
                    required={f.required}
                    rows={f.type === "json" ? 4 : 3}
                  />
                ) : f.type === "checkbox" ? (
                  <input
                    name={f.key}
                    type="checkbox"
                    defaultChecked={Boolean(value)}
                    required={f.required}
                  />
                ) : (
                  <input
                    name={f.key}
                    type={
                      ["url", "datetime-local", "number"].includes(f.type ?? "")
                        ? f.type
                        : "text"
                    }
                    defaultValue={def}
                    required={f.required}
                    min={f.type === "number" ? 1 : undefined}
                  />
                )}
                {f.hint && <small>{f.hint}</small>}
              </label>
            );
          })}
        </div>
        <button disabled={busy} type="submit">
          {busy ? "正在提交…" : submit}
        </button>
        {message && (
          <p role="status" className="success">
            {message}
          </p>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
      </form>
    </details>
  );
}
export function Action({
  children,
  run,
  danger = false,
}: {
  children: ReactNode;
  run: () => Promise<unknown>;
  danger?: boolean;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [done, setDone] = useState(false);
  return (
    <span className="action">
      <button
        className={danger ? "danger" : "secondary"}
        disabled={busy}
        onClick={async () => {
          if (danger && !window.confirm("确认删除？已有历史快照不会被重写。"))
            return;
          setBusy(true);
          setError("");
          setDone(false);
          try {
            await run();
            setDone(true);
          } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "处理中…" : children}
      </button>
      {done && <small role="status">完成</small>}
      {error && (
        <span role="alert" className="error">
          {error}
        </span>
      )}
    </span>
  );
}
export function Json({
  value,
  title = "查看结构化记录",
}: {
  value: unknown;
  title?: string;
}) {
  return (
    <details>
      <summary>{title}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}
export function Empty({
  children = "暂无记录。请先创建或导入真实数据。",
}: {
  children?: ReactNode;
}) {
  return (
    <div className="empty">
      <span className="empty-mark" aria-hidden="true">
        ＋
      </span>
      <div>
        <span className="eyebrow">尚待观察</span>
        <p>{children}</p>
      </div>
    </div>
  );
}
export function LinkURL({ url }: { url?: string }) {
  return url && /^https?:\/\//i.test(url) ? (
    <a href={url} target="_blank" rel="noreferrer">
      {url}
    </a>
  ) : (
    <span>{url || "未提供来源链接"}</span>
  );
}
