"""FastAPI application entry point."""

import logging
import os
import re
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes.ai_providers import router as ai_providers_router
from app.api.routes.auth import router as auth_router
from app.api.routes.documents import router as documents_router
from app.api.routes.transformation_presets import router as presets_router
from app.api.routes.transformations import router as transformations_router
from app.api.routes.websockets import router as websockets_router
from app.api.routes.workspaces import router as workspaces_router
from app.core.config import settings
from app.core.database import close_db, database_health_check
from app.core.websocket_manager import manager as websocket_manager
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.security import SecurityHeadersMiddleware
from app.services.redis_service import redis_service

logging.basicConfig(
    level=logging.INFO if settings.ENVIRONMENT == "production" else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class _RedactTokens(logging.Filter):
    """Browsers can't set headers on WebSocket handshakes, so the JWT travels in the
    query string; keep it out of the logs."""

    _pattern = re.compile(r"((?:access_)?token=)[^&\s\"]+")

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            record.args = tuple(
                self._pattern.sub(r"\1[redacted]", a) if isinstance(a, str) else a
                for a in record.args
            )
        return True


# uvicorn logs HTTP requests via uvicorn.access and WebSocket handshakes via uvicorn.error.
for _logger_name in ("uvicorn.access", "uvicorn.error"):
    logging.getLogger(_logger_name).addFilter(_RedactTokens())


API_VERSION = "3.0.0"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema is owned by Alembic (`alembic upgrade head`, run by start.sh / `make migrate`);
    # the app never creates tables itself, so RLS policies can't be skipped by accident.
    db = await database_health_check()
    logger.info("Database: %s", db["status"])
    logger.info("Redis: %s", "connected" if await redis_service.health_check() else "unavailable")
    await websocket_manager.start_redis_listener()
    yield
    await websocket_manager.stop_redis_listener()
    await close_db()


app = FastAPI(
    title="Content Repurpose API",
    description="Multi-tenant API that turns long-form content into summaries, "
    "social posts, email sequences and more using pluggable AI providers.",
    version=API_VERSION,
    lifespan=lifespan,
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{time.perf_counter() - start:.4f}"
    return response


# Middleware runs outermost-last-added. CORS is outermost so that preflights are
# answered before rate limiting and every response, including 429s, carries CORS headers.
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
    expose_headers=["X-Request-ID", "Retry-After"],
    max_age=3600,
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Last-resort 500.

    Starlette runs this in ServerErrorMiddleware, outside CORSMiddleware, so the
    CORS headers must be added here or browsers report a CORS error instead of the 500.
    """
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    content = {"detail": "Internal server error"}
    if settings.DEBUG:
        content["error"] = f"{type(exc).__name__}: {exc}"
    response = JSONResponse(status_code=500, content=content)
    origin = request.headers.get("origin")
    if origin and _origin_allowed(origin):
        response.headers["access-control-allow-origin"] = origin
        response.headers["access-control-allow-credentials"] = "true"
        response.headers["vary"] = "Origin"
    return response


def _origin_allowed(origin: str) -> bool:
    return origin in settings.CORS_ORIGINS or bool(
        settings.CORS_ORIGIN_REGEX and re.fullmatch(settings.CORS_ORIGIN_REGEX, origin)
    )


@app.get("/", include_in_schema=False)
async def root():
    return {"service": "content-repurpose-api", "version": API_VERSION, "docs": "/docs"}


@app.get("/api/health", tags=["health"])
async def health():
    """Liveness plus dependency status. Returns 200 while degraded so a platform
    healthcheck doesn't restart the API over an optional dependency."""
    checks = {}
    overall = "healthy"

    db = await database_health_check()
    checks["database"] = {"status": db["status"]}
    if db["status"] != "healthy":
        overall = "degraded"

    checks["redis"] = {"status": "healthy" if await redis_service.health_check() else "unavailable"}

    try:
        from app.services.ai_providers.manager import get_ai_provider_manager

        provider_manager = get_ai_provider_manager()
        providers = {
            name: {
                "enabled": provider_manager.provider_configs[name].enabled,
                "available": provider.is_available(),
            }
            for name, provider in provider_manager.providers.items()
        }
        real_provider = any(
            p["enabled"] and p["available"] for name, p in providers.items() if name != "mock"
        )
        checks["ai_provider"] = {
            "status": "healthy" if real_provider else "mock_only",
            "providers": providers,
        }
        if settings.ENVIRONMENT.lower() == "production" and not real_provider:
            overall = "degraded"
    except Exception:
        logger.exception("AI provider health check failed")
        checks["ai_provider"] = {"status": "error"}
        overall = "degraded"

    return {
        "status": overall,
        "service": "content-repurpose-api",
        "version": API_VERSION,
        "environment": settings.ENVIRONMENT,
        "timestamp": time.time(),
        "checks": checks,
    }


app.include_router(auth_router, prefix="/api/auth", tags=["auth"])
app.include_router(documents_router, prefix="/api", tags=["documents"])
app.include_router(transformations_router, prefix="/api/transformations", tags=["transformations"])
app.include_router(presets_router, prefix="/api/transformation-presets", tags=["presets"])
app.include_router(workspaces_router, prefix="/api", tags=["workspaces"])
app.include_router(websockets_router, prefix="/api", tags=["realtime"])
app.include_router(ai_providers_router, prefix="/api", tags=["ai-providers"])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=settings.DEBUG,
    )
