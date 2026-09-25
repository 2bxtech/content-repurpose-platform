from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
import time
from app.services.redis_service import redis_service
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)


class RateLimitMiddleware:
    """Rate limiting middleware for API endpoints"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)

        # Skip rate limiting for certain paths
        path = request.url.path
        if self._should_skip_rate_limiting(path):
            await self.app(scope, receive, send)
            return

        # Apply appropriate rate limit
        try:
            self._apply_rate_limit(request)
        except HTTPException as e:
            response = JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail},
                headers=e.headers or {},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    def _should_skip_rate_limiting(self, path: str) -> bool:
        """Determine if rate limiting should be skipped for this path"""
        skip_paths = ["/docs", "/redoc", "/openapi.json", "/api/health", "/favicon.ico"]
        return any(path.startswith(skip_path) for skip_path in skip_paths)

    def _apply_rate_limit(self, request: Request):
        """Apply rate limiting based on the request path"""
        path = request.url.path
        ip_address = self._get_client_ip(request)

        # Determine rate limit based on endpoint - be more specific
        if path in [
            "/api/auth/token",
            "/api/auth/register",
            "/api/auth/refresh",
            "/api/auth/change-password",
        ]:
            # Only apply strict auth rate limiting to authentication endpoints
            limit = settings.RATE_LIMIT_AUTH_ATTEMPTS
            limit_type = "auth"
        elif "/transformations" in path and request.method in {"POST", "PUT", "PATCH"}:
            limit = settings.RATE_LIMIT_TRANSFORMATIONS
            limit_type = "transformations"
        else:
            # More relaxed rate limiting for other API endpoints
            limit = settings.RATE_LIMIT_API_CALLS
            limit_type = "api"

        key = f"rate_limit:{limit_type}:{ip_address}"
        allowed, remaining, reset_time = redis_service.check_rate_limit(key, limit)

        if not allowed:
            # Determine appropriate error message
            if limit_type == "auth":
                message = "Too many authentication attempts. Please try again later."
            elif limit_type == "transformations":
                message = "Transformation rate limit exceeded. Please wait before requesting more transformations."
            else:
                message = "API rate limit exceeded. Please slow down your requests."

            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "message": message,
                    "limit_type": limit_type,
                    "retry_after": reset_time,
                    "remaining": 0,
                },
                headers={
                    "Retry-After": str(reset_time),
                    "X-RateLimit-Limit": limit.split("/")[0],
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + reset_time),
                },
            )

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address, handling proxies"""
        # Check for forwarded IP first (common in production)
        forwarded_for = request.headers.get("x-forwarded-for")
        if settings.TRUST_PROXY_HEADERS and forwarded_for:
            return forwarded_for.split(",")[0].strip()

        # Check for real IP header
        real_ip = request.headers.get("x-real-ip")
        if settings.TRUST_PROXY_HEADERS and real_ip:
            return real_ip

        # Fall back to direct connection IP
        return request.client.host if request.client else "unknown"


def create_rate_limit_dependency(limit_type: str):
    """Create a dependency for specific rate limiting"""

    async def rate_limit_dependency(request: Request):
        ip_address = request.client.host if request.client else "unknown"

        # Get the appropriate limit
        limits = {
            "auth": settings.RATE_LIMIT_AUTH_ATTEMPTS,
            "api": settings.RATE_LIMIT_API_CALLS,
            "transformations": settings.RATE_LIMIT_TRANSFORMATIONS,
        }

        limit = limits.get(limit_type, "100/1m")
        key = f"rate_limit:{limit_type}:{ip_address}"

        allowed, remaining, reset_time = redis_service.check_rate_limit(key, limit)

        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "message": f"{limit_type.title()} rate limit exceeded",
                    "retry_after": reset_time,
                },
                headers={"Retry-After": str(reset_time)},
            )

        return {"remaining": remaining, "reset_time": reset_time}

    return rate_limit_dependency


# Pre-configured dependencies
auth_rate_limit = create_rate_limit_dependency("auth")
api_rate_limit = create_rate_limit_dependency("api")
transformation_rate_limit = create_rate_limit_dependency("transformations")
