"""End-to-end checks against a running stack (API + worker + Postgres + Redis).

Run with `make test-integration`; skipped when TEST_API_URL is unset.
The stack uses the mock AI provider, so no API keys are needed.
"""

import asyncio
import base64
import json
import uuid

import httpx
import pytest
import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatusCode

pytestmark = pytest.mark.integration

SAMPLE = (
    "Remote teams ship faster when decisions are written down. A short design doc "
    "forces clarity, invites asynchronous review, and leaves a record for new hires."
)


async def _register_and_login(client: httpx.AsyncClient) -> dict:
    suffix = uuid.uuid4().hex[:8]
    creds = {
        "email": f"it_{suffix}@example.com",
        "username": f"it_{suffix}",
        "password": "IntegrationPass123!",
    }
    r = await client.post("/api/auth/register", json=creds)
    assert r.status_code == 201, r.text
    r = await client.post(
        "/api/auth/token",
        data={"username": creds["email"], "password": creds["password"]},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert r.status_code == 200, r.text
    token = r.json()["access_token"]
    payload = token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    return {
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
        "workspace_id": claims["workspace_id"],
    }


async def _create_document(client: httpx.AsyncClient, user: dict) -> str:
    r = await client.post(
        "/api/documents/text",
        data={"title": "Design docs", "content": SAMPLE},
        headers=user["headers"],
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _wait_for_terminal(client, user, transformation_id, timeout=60.0) -> dict:
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        r = await client.get(f"/api/transformations/{transformation_id}", headers=user["headers"])
        assert r.status_code == 200, r.text
        body = r.json()
        if body["status"] in ("COMPLETED", "FAILED"):
            return body
        assert asyncio.get_event_loop().time() < deadline, f"still {body['status']}"
        await asyncio.sleep(0.5)


async def test_transformation_runs_on_worker_and_notifies_over_websocket(api_client):
    user = await _register_and_login(api_client)
    document_id = await _create_document(api_client, user)

    ws_url = str(api_client.base_url).replace("http", "ws", 1).rstrip("/") + "/api/ws"
    workspace_id = user["workspace_id"]
    async with websockets.connect(f"{ws_url}?token={user['token']}&workspace_id={workspace_id}") as ws:
        async def until(event_type):
            while True:
                msg = json.loads(await ws.recv())
                if msg["type"] == event_type:
                    return msg
        await asyncio.wait_for(until("connection_established"), 10)

        r = await api_client.post(
            "/api/transformations",
            json={"document_id": document_id, "transformation_type": "SUMMARY", "parameters": {}},
            headers=user["headers"],
        )
        assert r.status_code == 201, r.text
        created = r.json()
        # Returned without waiting for the AI call, which runs on the Celery worker
        # (task_id). A fast worker may already be done when the response is built.
        assert created["task_id"]
        assert created["status"] in ("PENDING", "PROCESSING", "COMPLETED")

        events = []
        async def collect():
            while True:
                msg = json.loads(await ws.recv())
                events.append(msg["type"])
                if msg["type"] in ("transformation_completed", "transformation_failed"):
                    return msg
        done = await asyncio.wait_for(collect(), 60)

    assert done["type"] == "transformation_completed", done
    assert done["data"]["transformation_id"] == created["id"]
    assert "transformation_started" in events

    final = await _wait_for_terminal(api_client, user, created["id"])
    assert final["status"] == "COMPLETED"
    assert final["result"]


async def test_tenants_cannot_read_each_others_transformations(api_client):
    alice = await _register_and_login(api_client)
    bob = await _register_and_login(api_client)
    assert alice["workspace_id"] != bob["workspace_id"]

    document_id = await _create_document(api_client, alice)
    r = await api_client.post(
        "/api/transformations",
        json={"document_id": document_id, "transformation_type": "SUMMARY", "parameters": {}},
        headers=alice["headers"],
    )
    transformation_id = r.json()["id"]

    assert (await api_client.get(f"/api/transformations/{transformation_id}", headers=bob["headers"])).status_code == 404
    assert (await api_client.get(f"/api/documents/{document_id}", headers=bob["headers"])).status_code == 404
    # Bob can't start work against Alice's document either.
    r = await api_client.post(
        "/api/transformations",
        json={"document_id": document_id, "transformation_type": "SUMMARY", "parameters": {}},
        headers=bob["headers"],
    )
    assert r.status_code == 404


async def test_websocket_rejects_foreign_workspace(api_client):
    alice = await _register_and_login(api_client)
    bob = await _register_and_login(api_client)
    ws_url = str(api_client.base_url).replace("http", "ws", 1).rstrip("/") + "/api/ws"
    # Rejected before accept, so the handshake itself fails (HTTP 403).
    with pytest.raises((InvalidStatusCode, ConnectionClosed)):
        async with websockets.connect(
            f"{ws_url}?token={alice['token']}&workspace_id={bob['workspace_id']}"
        ) as ws:
            await asyncio.wait_for(ws.recv(), 10)


async def test_operator_endpoints_require_platform_admin(api_client):
    user = await _register_and_login(api_client)
    for path in ("/api/providers/status", "/api/providers/costs", "/api/ws/stats"):
        assert (await api_client.get(path, headers=user["headers"])).status_code == 403, path
    assert (await api_client.get("/api/providers/models", headers=user["headers"])).status_code == 200


async def test_security_headers_present(api_client):
    r = await api_client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-request-id"]
