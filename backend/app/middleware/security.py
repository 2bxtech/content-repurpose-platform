"""Security response headers for a JSON API.

Pure ASGI (no BaseHTTPMiddleware) so it adds headers without buffering responses.
Swagger/ReDoc pages load scripts from a CDN, so they get no CSP; every other
response is JSON and gets a deny-everything policy.
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

_BASE_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=(), payment=()"),
    (b"cross-origin-opener-policy", b"same-origin"),
]
_API_CSP = (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'")
_HSTS = (b"strict-transport-security", b"max-age=31536000; includeSubDomains")
_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.hsts = settings.ENVIRONMENT.lower() == "production"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        extra = list(_BASE_HEADERS)
        if not scope["path"].startswith(_DOCS_PATHS):
            extra.append(_API_CSP)
        if self.hsts:
            extra.append(_HSTS)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                existing = {k.lower() for k, _ in message.get("headers", [])}
                message.setdefault("headers", [])
                message["headers"] = list(message["headers"]) + [
                    (k, v) for k, v in extra if k not in existing
                ]
            await send(message)

        await self.app(scope, receive, send_with_headers)
