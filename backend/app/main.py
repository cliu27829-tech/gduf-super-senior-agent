from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from uuid import uuid4
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.router import api_router
from app.core.config import get_settings
from app.core.database import SessionLocal, create_schema
from app.models.entities import SystemLog
from app.services.seed_service import seed_database


settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("gduf-api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_create_schema:
        create_schema()
    if settings.seed_demo_data:
        with SessionLocal() as db:
            seed_database(db)
    yield


app = FastAPI(
    title=settings.app_name,
    description=settings.app_subtitle,
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Authorization", "Content-Type", "X-Request-ID"],
)


def _origin(value: str) -> str:
    parsed = urlsplit(value)
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/") if parsed.scheme and parsed.netloc else ""


def _csp() -> str:
    return "; ".join(
        [
            "default-src 'self'",
            "base-uri 'self'",
            "object-src 'none'",
            "frame-ancestors 'none'",
            "form-action 'self'",
            "script-src 'self' 'unsafe-inline' https://webapi.amap.com https://*.amap.com",
            "style-src 'self' 'unsafe-inline' https://*.amap.com",
            "font-src 'self' data:",
            "img-src 'self' data: blob: https://*.amap.com https://*.autonavi.com",
            "connect-src 'self' https://*.amap.com https://*.autonavi.com https://restapi.amap.com",
            "worker-src 'self' blob:",
        ]
    )


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid4()))[:64]
    if request.url.path.startswith(settings.api_prefix) and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = _origin(request.headers.get("origin", ""))
        referer = _origin(request.headers.get("referer", ""))
        allowed = set(settings.cors_origins)
        fetch_site = request.headers.get("sec-fetch-site", "").lower()
        if fetch_site == "cross-site" or (origin and origin not in allowed) or (not origin and referer and referer not in allowed):
            return JSONResponse(
                status_code=403,
                content={"detail": "请求来源校验失败", "request_id": request_id},
                headers={"X-Request-ID": request_id},
            )
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.exception("Unhandled request error request_id=%s path=%s", request_id, request.url.path)
        try:
            with SessionLocal() as db:
                db.add(SystemLog(level="error", event="unhandled_request", message=type(exc).__name__, request_id=request_id))
                db.commit()
        except Exception:
            logger.exception("Unable to persist system error")
        return JSONResponse(status_code=500, content={"detail": "服务器暂时无法处理请求", "request_id": request_id})
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(self)"
    response.headers["Content-Security-Policy"] = _csp()
    return response


@app.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok", "service": "gduf-super-senior-api"}


@app.get("/ready", tags=["system"], response_model=None)
def ready() -> JSONResponse | dict:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "not_ready"})


app.include_router(api_router, prefix=settings.api_prefix)
