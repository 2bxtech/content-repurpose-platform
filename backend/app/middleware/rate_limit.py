"""Per-client rate limiting for the HTTP API (pure ASGI, fully async)."""

import time

from fastapi.responses import JSONResponse
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import settings
from app.services.rate_limiter import rate_limiter

_SKIP_PREFIXES = ("/docs", "/redoc", "/openapi.json", "/api/health", "/favicon.ico")
_AUTH_PATHS = {
    "/api/auth/token",
    "/api/auth/register",
    "/api/auth/refresh",
    "/api/auth/change-password",
}
_MESSAGES = {
    "auth": "Too many authentication attempts. Please try again later.",
    "transformations": "Transformation rate limit exceeded. Please wait before requesting more transformations.",
    "api": "API rate limit exceeded. Please slow down your requests.",
}


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"].startswith(_SKIP_PREFIXES):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        limit_type, limit = _classify(request)
        result = await rate_limiter.check(f"rate_limit:{limit_type}:{_client_ip(request)}", limit)

        if not result.allowed:
            retry = result.retry_after_seconds
            response = JSONResponse(
                status_code=429,
                content={
                    "detail": {
                        "message": _MESSAGES[limit_type],
                        "limit_type": limit_type,
                        "retry_after": retry,
                        "remaining": 0,
                    }
                },
                headers={
                    "Retry-After": str(retry),
                    "X-RateLimit-Limit": limit.split("/")[0],
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + retry),
                },
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


def _classify(request: Request) -> tuple[str, str]:
    path = request.url.path
    if path in _AUTH_PATHS:
        return "auth", settings.RATE_LIMIT_AUTH_ATTEMPTS
    if "/transformations" in path and request.method in {"POST", "PUT", "PATCH"}:
        return "transformations", settings.RATE_LIMIT_TRANSFORMATIONS
    return "api", settings.RATE_LIMIT_API_CALLS


def _client_ip(request: Request) -> str:
    # Forwarding headers are client-controlled unless a trusted proxy overwrites them.
    if settings.TRUST_PROXY_HEADERS:
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip
    return request.client.host if request.client else "unknown"
