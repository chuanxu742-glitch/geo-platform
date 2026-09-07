import hmac
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from .db import migrate, get_db
from . import catalog, monitoring, content, operations, website, publishing, research, agent_runtime
from . import measurement


@asynccontextmanager
async def lifespan(app):
    migrate()
    worker = agent_runtime.start_worker()
    try:
        yield
    finally:
        worker.stop()


async def authorize(authorization: str | None = Header(default=None)):
    token = os.getenv("GEO_BACKEND_TOKEN", "")
    if token and not hmac.compare_digest(authorization or "", "Bearer " + token):
        raise HTTPException(401, "未授权，请配置正确的服务端访问令牌")


app = FastAPI(title="GEO Optimization Operations", version="2.0.0", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=[s.strip() for s in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if s.strip()], allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Authorization", "Content-Type"])
app.include_router(catalog.router, prefix="/api", dependencies=[Depends(authorize)])
app.include_router(monitoring.router, prefix="/api", dependencies=[Depends(authorize)])
app.include_router(content.router, prefix="/api", dependencies=[Depends(authorize)])
app.include_router(operations.router, prefix="/api", dependencies=[Depends(authorize)])
app.include_router(website.router, prefix="/api", dependencies=[Depends(authorize)])
app.include_router(publishing.router, prefix="/api", dependencies=[Depends(authorize)])
app.include_router(research.router, prefix="/api", dependencies=[Depends(authorize)])
app.include_router(agent_runtime.router, prefix="/api", dependencies=[Depends(authorize)])
app.include_router(measurement.router, prefix="/api", dependencies=[Depends(authorize)])


@app.get("/api/health")
def health(db=Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    # Do not echo invalid input: it can contain credentials or confidential drafts.
    fields = [".".join(str(part) for part in error["loc"]) for error in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": "请求参数不正确，请检查字段：" + "、".join(fields)})


@app.exception_handler(IntegrityError)
async def conflict_error(request: Request, exc: IntegrityError):
    return JSONResponse(status_code=409, content={"detail": "操作与现有记录或并发更新冲突，请刷新后重试；源任务不会自动重新触发"})


@app.exception_handler(OperationalError)
async def database_error(request: Request, exc: OperationalError):
    return JSONResponse(status_code=503, content={"detail": "数据库暂时不可用，请稍后重试；请勿重复触发未知状态的源任务"})
