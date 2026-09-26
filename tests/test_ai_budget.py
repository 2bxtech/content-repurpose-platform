"""Per-workspace monthly AI limits."""

import base64
import json
import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text

from app.services.ai_budget import AIBudgetStatus, month_start


def _status(**overrides):
    values = dict(
        requests_used=0, requests_limit=10, spend_usd=0.0, budget_usd=5.0,
        period_start=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    values.update(overrides)
    return AIBudgetStatus(**values)


def test_under_both_limits_is_allowed():
    assert _status(requests_used=9, spend_usd=4.99).exhausted_reason is None


def test_request_limit_blocks():
    assert "request limit" in _status(requests_used=10).exhausted_reason


def test_spend_limit_blocks():
    assert "budget" in _status(spend_usd=5.0).exhausted_reason


def test_month_starts_at_utc_midnight_on_the_first():
    assert month_start(datetime(2026, 9, 25, 23, 59, tzinfo=timezone.utc)) == datetime(
        2026, 9, 1, tzinfo=timezone.utc
    )


# --- Integration: enforced through the API ---------------------------------------


@pytest.fixture
def superuser_db():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Needs TEST_DATABASE_URL (make test-integration)")
    engine = create_engine(url)
    yield engine
    engine.dispose()


async def _user_with_document(api_client):
    suffix = uuid.uuid4().hex[:8]
    creds = {"email": f"budget_{suffix}@example.com", "username": f"budget_{suffix}", "password": f"Bdg-{uuid.uuid4().hex}-A1"}
    assert (await api_client.post("/api/auth/register", json=creds)).status_code == 201
    token = (
        await api_client.post("/api/auth/token", data={"username": creds["email"], "password": creds["password"]})
    ).json()["access_token"]
    payload = token.split(".")[1]
    workspace_id = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))["workspace_id"]
    headers = {"Authorization": f"Bearer {token}"}
    doc = await api_client.post(
        "/api/documents/text", data={"title": "Budget", "content": "Some text to transform for the budget test."}, headers=headers
    )
    return {"headers": headers, "workspace_id": workspace_id, "document_id": doc.json()["id"]}


def _set_limits(engine, workspace_id, **limits):
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE workspaces SET settings = settings || CAST(:patch AS jsonb) WHERE id = :id"),
            {"patch": json.dumps(limits), "id": workspace_id},
        )


@pytest.mark.integration
async def test_request_limit_returns_402_once_reached(api_client, superuser_db):
    user = await _user_with_document(api_client)
    _set_limits(superuser_db, user["workspace_id"], ai_requests_per_month=1)
    body = {"document_id": user["document_id"], "transformation_type": "SUMMARY", "parameters": {}}

    first = await api_client.post("/api/transformations", json=body, headers=user["headers"])
    assert first.status_code == 201, first.text
    second = await api_client.post("/api/transformations", json=body, headers=user["headers"])
    assert second.status_code == 402
    assert "request limit" in second.json()["detail"]


@pytest.mark.integration
async def test_spend_budget_blocks_quick_transform_and_usage_reports_it(api_client, superuser_db):
    user = await _user_with_document(api_client)
    _set_limits(superuser_db, user["workspace_id"], ai_monthly_budget_usd=0)

    r = await api_client.post(
        "/api/transformations/quick",
        json={"content": "Enough words here to satisfy the minimum length.", "transformation_type": "SUMMARY"},
        headers=user["headers"],
    )
    assert r.status_code == 402
    assert "budget" in r.json()["detail"]

    usage = (await api_client.get(f"/api/workspaces/{user['workspace_id']}/usage", headers=user["headers"])).json()
    assert usage["limits"]["ai_monthly_budget_usd"] == 0
    assert "ai_spend_this_month_usd" in usage["current_usage"]
