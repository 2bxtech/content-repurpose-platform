"""Focused regression tests for authentication and tenant security boundaries."""

import inspect
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException, WebSocketException
from starlette.requests import Request

from app.api.routes.auth import change_password
from app.api.routes.documents import _validate_url_ssrf, get_user_documents
from app.models.auth import PasswordChangeRequest
from app.api.routes.websockets import websocket_endpoint
from app.core.config import settings
from app.core.websocket_auth import authenticate_websocket_token
from app.middleware.rate_limit import RateLimitMiddleware
from app.services.auth_service import AuthService
from app.services.ai_providers.base import AIProviderError
from app.services.ai_providers.manager import AIProviderManager
from app.services.ai_providers.openai_provider import OpenAIProvider
from app.services.ai_providers.anthropic_provider import AnthropicProvider
from app.services.redis_service import RedisService


def make_request(headers=None, client=("203.0.113.10", 1234)):
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/auth/token",
            "headers": [
                (key.lower().encode(), value.encode())
                for key, value in (headers or {}).items()
            ],
            "client": client,
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )


def test_access_token_round_trip_includes_tenant_claims():
    service = AuthService()
    user_id = uuid.uuid4()
    workspace_id = uuid.uuid4()

    with patch(
        "app.services.auth_service.redis_service.is_token_blacklisted",
        return_value=False,
    ):
        token = service.create_access_token(
            {
                "sub": str(user_id),
                "email": "member@example.com",
                "username": "member",
                "workspace_id": str(workspace_id),
            }
        )
        data = service.verify_token(token)

    assert data.user_id == user_id
    assert data.workspace_id == workspace_id
    assert data.username == "member"


@pytest.mark.asyncio
async def test_websocket_auth_preserves_policy_errors_without_leaking_details():
    with patch(
        "app.core.websocket_auth.auth_service.verify_token", return_value=None
    ):
        with pytest.raises(WebSocketException) as exc:
            await authenticate_websocket_token("bad-token")

    assert exc.value.code == 1008
    assert exc.value.reason == "Invalid authentication token"


@pytest.mark.asyncio
async def test_websocket_rejects_cross_workspace_connection():
    user_workspace = uuid.uuid4()
    websocket = AsyncMock()
    websocket.headers = {}

    with patch(
        "app.api.routes.websockets.get_websocket_user",
        AsyncMock(
            return_value={
                "id": uuid.uuid4(),
                "email": "member@example.com",
                "username": "member",
                "workspace_id": user_workspace,
            }
        ),
    ), patch("app.api.routes.websockets.manager.connect", AsyncMock()) as connect:
        await websocket_endpoint(
            websocket=websocket,
            token="signed-token",
            workspace_id=str(uuid.uuid4()),
        )

    connect.assert_not_awaited()
    websocket.close.assert_awaited_once()
    assert websocket.close.await_args.kwargs["code"] == 1008


def test_untrusted_forwarded_header_cannot_evade_ip_rate_limit(monkeypatch):
    middleware = RateLimitMiddleware(Mock())
    request = make_request({"x-forwarded-for": "198.51.100.99"})
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", False)

    assert middleware._get_client_ip(request) == "203.0.113.10"


def test_trusted_proxy_header_uses_first_forwarded_address(monkeypatch):
    middleware = RateLimitMiddleware(Mock())
    request = make_request(
        {"x-forwarded-for": "198.51.100.99, 192.0.2.1"}
    )
    monkeypatch.setattr(settings, "TRUST_PROXY_HEADERS", True)

    assert middleware._get_client_ip(request) == "198.51.100.99"


def test_rate_limit_uses_atomic_redis_script():
    service = RedisService.__new__(RedisService)
    service.redis_client = Mock()
    service.redis_client.ping.return_value = True
    service.redis_client.eval.return_value = [1, 3, 60_000]

    result = service.check_rate_limit("rate:test", "5/1m")

    assert result == (True, 3, 60)
    service.redis_client.eval.assert_called_once()
    script = service.redis_client.eval.call_args.args[0]
    assert "ZREMRANGEBYSCORE" in script
    assert "ZADD" in script


def test_session_existence_distinguishes_outage_from_revocation():
    service = RedisService.__new__(RedisService)
    service.redis_client = None
    assert service.user_session_exists("user", "jti") is None

    service.redis_client = Mock()
    service.redis_client.ping.return_value = True
    service.redis_client.exists.return_value = 0
    assert service.user_session_exists("user", "jti") is False


def test_document_listing_declares_authenticated_user_dependency():
    parameters = inspect.signature(get_user_documents).parameters
    assert "current_user" in parameters
    assert parameters["current_user"].default.dependency is not None


def test_ssrf_validation_rejects_if_any_dns_answer_is_private():
    answers = [
        (2, 1, 6, "", ("93.184.216.34", 443)),
        (2, 1, 6, "", ("127.0.0.1", 443)),
    ]
    with patch("app.api.routes.documents.socket.getaddrinfo", return_value=answers):
        with pytest.raises(HTTPException) as exc:
            _validate_url_ssrf("https://example.com/article")

    assert exc.value.status_code == 422
    assert "non-public" in exc.value.detail


@pytest.mark.asyncio
async def test_password_change_persists_hash_in_database(monkeypatch):
    user_id = uuid.uuid4()
    db_user = SimpleNamespace(id=user_id, hashed_password="old-hash")
    result = Mock()
    result.scalar_one_or_none.return_value = db_user
    db = AsyncMock()
    db.execute.return_value = result
    current_user = {
        "id": str(user_id),
        "email": "member@example.com",
        "hashed_password": "old-hash",
    }
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")

    with patch(
        "app.api.routes.auth.auth_service.verify_password",
        side_effect=[True, False],
    ), patch(
        "app.api.routes.auth.auth_service.validate_password_strength",
        return_value=(True, "strong"),
    ), patch(
        "app.api.routes.auth.auth_service.get_password_hash",
        return_value="new-hash",
    ), patch(
        "app.api.routes.auth.auth_service.invalidate_all_sessions",
        return_value=True,
    ):
        await change_password(
            PasswordChangeRequest(
                current_password="OldPassword123!",
                new_password="NewPassword456!",
            ),
            current_user,
            make_request(),
            db,
        )

    assert db_user.hashed_password == "new-hash"
    db.commit.assert_awaited_once()


def test_provider_rate_limit_supports_limits_above_sixty():
    manager = AIProviderManager()
    config = manager.provider_configs["mock"]
    assert config.max_requests_per_minute > 60
    now = __import__("time").time()
    manager.usage_trackers["mock"].requests_per_minute.extend(
        [now] * config.max_requests_per_minute
    )

    assert manager._can_use_provider("mock") is False


@pytest.mark.asyncio
async def test_unknown_preferred_provider_fails_fast():
    manager = AIProviderManager()
    with pytest.raises(AIProviderError) as exc:
        await manager.generate_text("test", preferred_provider="does-not-exist")

    assert exc.value.error_code == "unknown_provider"


@pytest.mark.parametrize(
    ("client_path", "provider_class"),
    [
        ("app.services.ai_providers.openai_provider.openai.AsyncOpenAI", OpenAIProvider),
        (
            "app.services.ai_providers.anthropic_provider.anthropic.AsyncAnthropic",
            AnthropicProvider,
        ),
    ],
)
def test_provider_clients_have_bounded_retries_and_timeouts(
    client_path, provider_class
):
    with patch(client_path) as client:
        provider_class(api_key="test-key")

    assert client.call_args.kwargs["timeout"] == settings.AI_REQUEST_TIMEOUT_SECONDS
    assert client.call_args.kwargs["max_retries"] == settings.AI_MAX_RETRIES
