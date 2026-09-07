import { NextRequest } from "next/server";
export const dynamic = "force-dynamic";
async function proxy(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
) {
  const { path } = await context.params;
  if (path.some((segment) => !/^[a-zA-Z0-9_-]+$/.test(segment)))
    return Response.json({ detail: "无效 API 路径" }, { status: 400 });
  if (!["GET", "HEAD"].includes(request.method)) {
    const origin = request.headers.get("origin");
    const expectedOrigin = `${request.nextUrl.protocol}//${request.headers.get("host")}`;
    if (origin && origin !== expectedOrigin)
      return Response.json({ detail: "不允许跨站操作" }, { status: 403 });
  }
  const base = process.env.GEO_API_URL || "http://127.0.0.1:8000";
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (process.env.GEO_BACKEND_TOKEN)
    headers.Authorization = `Bearer ${process.env.GEO_BACKEND_TOKEN}`;
  try {
    const response = await fetch(
      `${base.replace(/\/$/, "")}/api/${path.join("/")}${request.nextUrl.search}`,
      {
        method: request.method,
        headers,
        cache: "no-store",
        body: ["GET", "HEAD"].includes(request.method)
          ? undefined
          : await request.text(),
        signal: AbortSignal.timeout(180000),
      },
    );
    return new Response(await response.text(), {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("content-type") || "application/json",
      },
    });
  } catch {
    return Response.json(
      {
        detail:
          "后端连接失败或超时。请确认 8000 端口服务与 GEO_API_URL 配置；超时操作请先刷新检查，避免重复提交。",
      },
      { status: 502 },
    );
  }
}
export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
