"""
Shared test configuration.

Unit tests run in-process (FastAPI TestClient with dependency overrides).
Integration tests talk to a running stack over HTTP/WebSocket and are skipped
unless TEST_API_URL is set (see `make test-integration`).
"""

import asyncio
import base64
import json
import os
import uuid
from typing import AsyncGenerator, Awaitable, Callable

import httpx
import pytest

os.environ["ENVIRONMENT"] = "testing"
# Unit tests import app.core.config, which requires signing keys; use throwaway values.
os.environ.setdefault("SECRET_KEY", "test-only-access-signing-key-0123456789abcdef")
os.environ.setdefault("REFRESH_SECRET_KEY", "test-only-refresh-signing-key-0123456789abcdef")
if not os.getenv("TEST_API_URL"):
    # Unit mode: in-process TestClient apps must never reach a developer's local Postgres
    # (the default component config points at localhost:5433). Port 9 is unreachable.
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://unit:unit@127.0.0.1:9/unit_tests"
os.environ["DEBUG"] = "true"

# Integration tests only run when TEST_API_URL is set explicitly (make test-integration),
# so a plain `pytest` never writes to whatever happens to be listening on :8000.
TEST_API_URL = os.getenv("TEST_API_URL")

TEST_PASSWORD = "TestPassword123!"  # meets the password policy


def decode_jwt_claims(token: str) -> dict:
    """Read a JWT payload without verifying it (tests only need the claims)."""
    payload = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))


@pytest.fixture
def jwt_claims() -> Callable[[str], dict]:
    return decode_jwt_claims


# ---------------------------------------------------------------------------
# Unit-mode fixtures (in-process app, no external services)
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_user() -> dict:
    """The user dict that get_current_active_user returns for an authenticated member."""
    user_id = str(uuid.uuid4())
    return {
        "id": user_id,
        "sub": user_id,
        "email": f"member_{uuid.uuid4().hex[:8]}@example.com",
        "username": "member",
        "is_active": True,
        "workspace_id": str(uuid.uuid4()),
    }


@pytest.fixture
def unit_client(fake_user):
    """In-process TestClient authenticated as `fake_user` with no database.

    Auth, workspace context and the DB session are replaced through
    app.dependency_overrides; routes that support it fall back to in-memory storage.
    Lifespan is not run, so Redis/Postgres are never contacted.
    """
    from fastapi.testclient import TestClient

    from app.api.routes.auth import get_current_active_user
    from app.api.routes.workspaces import get_current_workspace_context
    from app.core.database import get_db_session
    from main import app

    async def _no_db():
        return None

    app.dependency_overrides[get_current_active_user] = lambda: fake_user
    app.dependency_overrides[get_current_workspace_context] = lambda: {
        "workspace_id": uuid.UUID(fake_user["workspace_id"]),
        "workspace_slug": "unit-tests",
        "user_role": "owner",
    }
    app.dependency_overrides[get_db_session] = _no_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Integration fixtures (running stack)
# ---------------------------------------------------------------------------


@pytest.fixture
async def api_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """HTTP client for the stack at TEST_API_URL; skipped when it is unset."""
    if not TEST_API_URL:
        pytest.skip("Integration test: set TEST_API_URL or run `make test-integration`")

    async with httpx.AsyncClient(base_url=TEST_API_URL, timeout=httpx.Timeout(30.0)) as client:
        try:
            response = await client.get("/api/health")
        except httpx.TransportError as e:
            # TEST_API_URL was set on purpose, so an unreachable API is a failure, not a skip.
            pytest.fail(f"Cannot reach test API at {TEST_API_URL}: {e}")
        if response.status_code != 200:
            pytest.fail(f"API health check failed: {response.status_code}")

        yield client


@pytest.fixture
def user_factory(api_client: httpx.AsyncClient) -> Callable[[], Awaitable[dict]]:
    """Register and log in a brand-new user; returns credentials, tokens and tenant claims."""

    async def create() -> dict:
        suffix = uuid.uuid4().hex[:8]
        creds = {
            "username": f"testuser_{suffix}",
            "email": f"test_{suffix}@example.com",
            "password": TEST_PASSWORD,
        }
        r = await api_client.post("/api/auth/register", json=creds)
        if r.status_code != 201:
            pytest.fail(f"Failed to register test user: {r.status_code} - {r.text}")

        # OAuth2 password flow: form-encoded, email in the "username" field.
        r = await api_client.post(
            "/api/auth/token",
            data={"username": creds["email"], "password": creds["password"]},
        )
        if r.status_code != 200:
            pytest.fail(f"Failed to authenticate test user: {r.status_code} - {r.text}")

        tokens = r.json()
        claims = decode_jwt_claims(tokens["access_token"])
        return {
            **creds,
            "token": tokens["access_token"],
            "refresh_token": tokens.get("refresh_token"),
            "headers": {"Authorization": f"Bearer {tokens['access_token']}"},
            "user_id": claims["sub"],
            "workspace_id": claims["workspace_id"],
        }

    return create


@pytest.fixture
async def auth_user(user_factory) -> dict:
    """The user behind `authenticated_client`."""
    return await user_factory()


@pytest.fixture
async def authenticated_client(
    api_client: httpx.AsyncClient, auth_user: dict
) -> AsyncGenerator[httpx.AsyncClient, None]:
    """`api_client` carrying a fresh user's bearer token."""
    api_client.headers.update(auth_user["headers"])
    yield api_client


@pytest.fixture
async def test_document(authenticated_client: httpx.AsyncClient) -> dict:
    """A text document owned by the authenticated user (plus the content it was created from)."""
    content = (
        "Remote teams ship faster when decisions are written down. A short design doc "
        "forces clarity, invites asynchronous review, and leaves a record for new hires."
    )
    r = await authenticated_client.post(
        "/api/documents/text", data={"title": "Test Document", "content": content}
    )
    assert r.status_code == 201, r.text
    return {**r.json(), "content": content}


@pytest.fixture
def sample_transformation_data() -> dict:
    """Body for POST /api/transformations, minus document_id."""
    return {"transformation_type": "SUMMARY", "parameters": {"length": "brief"}}


@pytest.fixture
def wait_for_transformation() -> Callable[..., Awaitable[dict]]:
    """Poll GET /api/transformations/{id} until the worker marks it COMPLETED or FAILED."""

    async def wait(client: httpx.AsyncClient, transformation_id: str, timeout: float = 60.0, headers=None):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            r = await client.get(f"/api/transformations/{transformation_id}", headers=headers)
            assert r.status_code == 200, r.text
            body = r.json()
            if body["status"] in ("COMPLETED", "FAILED"):
                return body
            assert loop.time() < deadline, f"transformation still {body['status']} after {timeout}s"
            await asyncio.sleep(0.5)

    return wait


# ---------------------------------------------------------------------------
# WebSocket fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def websocket_url(api_client: httpx.AsyncClient) -> str:
    return str(api_client.base_url).replace("http", "ws", 1).rstrip("/") + "/api/ws"


@pytest.fixture
async def websocket_client(auth_user: dict, websocket_url: str):
    """An open socket for `auth_user`, bound to the workspace in their token."""
    import websockets

    url = f"{websocket_url}?token={auth_user['token']}&workspace_id={auth_user['workspace_id']}"
    async with websockets.connect(url) as ws:
        yield ws


class WebSocketTestHelper:
    """Receive helpers that skip unrelated events (presence updates etc.)."""

    @staticmethod
    async def wait_for_message_type(websocket, message_type: str, timeout: float = 10.0) -> dict:
        async def receive():
            while True:
                try:
                    message = json.loads(await websocket.recv())
                except json.JSONDecodeError:
                    continue
                if message.get("type") == message_type:
                    return message

        return await asyncio.wait_for(receive(), timeout)

    @classmethod
    async def send_and_wait_for_response(
        cls, websocket, message, expected_type: str, timeout: float = 5.0
    ) -> dict:
        await websocket.send(message if isinstance(message, str) else json.dumps(message))
        return await cls.wait_for_message_type(websocket, expected_type, timeout)


@pytest.fixture
def ws_helper() -> WebSocketTestHelper:
    return WebSocketTestHelper()
