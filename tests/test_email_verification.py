"""Email verification: single-purpose tokens, the AI gate, and the API flow."""

import logging
import os
import uuid
from datetime import datetime, timedelta

import jwt
import pytest
from fastapi import HTTPException

from app.api.routes.auth import require_verified_email
from app.core.config import settings
from app.services import email as email_service
from app.services.auth_service import auth_service


def test_verification_and_access_tokens_are_not_interchangeable():
    user_id = uuid.uuid4()
    verify = auth_service.create_email_verification_token(user_id, "a@example.com")
    access = auth_service.create_access_token({"sub": str(user_id), "email": "a@example.com"})

    assert auth_service.verify_token(verify, "email_verify").user_id == user_id
    assert auth_service.verify_token(verify, "access") is None
    assert auth_service.verify_token(access, "email_verify") is None


async def test_ai_gate_blocks_unverified_users_only_when_required(monkeypatch):
    unverified = {"id": "u", "is_verified": False}
    monkeypatch.setattr(settings, "REQUIRE_VERIFIED_EMAIL", True)
    with pytest.raises(HTTPException) as exc:
        await require_verified_email(unverified)
    assert exc.value.status_code == 403
    assert await require_verified_email({"id": "u", "is_verified": True})

    monkeypatch.setattr(settings, "REQUIRE_VERIFIED_EMAIL", None)
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    assert await require_verified_email(unverified)  # local dev: not required
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    assert settings.require_verified_email is True


async def test_production_never_logs_the_link_when_smtp_is_missing(monkeypatch, caplog):
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(settings, "SMTP_HOST", "")
    with caplog.at_level(logging.INFO):
        sent = await email_service.send_verification_email("a@example.com", "SECRET-VERIFY-TOKEN")
    assert sent is False
    assert "SECRET-VERIFY-TOKEN" not in caplog.text


# --- Integration --------------------------------------------------------------

# The throwaway integration stack signs with the compose default key; the test
# mints the link token itself instead of reading an email.
STACK_SECRET = os.getenv("TEST_SECRET_KEY", "local-dev-access-token-signing-key-not-for-prod")


def _link_token(user_id: str, email: str, **overrides) -> str:
    now = datetime.utcnow()
    claims = {"sub": user_id, "email": email, "type": "email_verify", "iat": now,
              "exp": now + timedelta(hours=1), "jti": uuid.uuid4().hex}
    claims.update(overrides)
    return jwt.encode(claims, STACK_SECRET, algorithm="HS256")


@pytest.mark.integration
async def test_verification_flow(api_client, user_factory):
    user = await user_factory()
    me = (await api_client.get("/api/auth/me", headers=user["headers"])).json()
    assert me["is_verified"] is False

    for bad in (
        _link_token(me["id"], "someone-else@example.com"),
        _link_token(me["id"], me["email"], type="access"),
        _link_token(me["id"], me["email"], exp=datetime.utcnow() - timedelta(minutes=1)),
        "not-a-token",
    ):
        r = await api_client.post("/api/auth/verify-email", json={"token": bad})
        assert r.status_code == 400, r.text

    token = _link_token(me["id"], me["email"])
    assert (await api_client.post("/api/auth/verify-email", json={"token": token})).status_code == 200
    assert (await api_client.post("/api/auth/verify-email", json={"token": token})).status_code == 200  # idempotent
    assert (await api_client.get("/api/auth/me", headers=user["headers"])).json()["is_verified"] is True

    resend = await api_client.post("/api/auth/resend-verification", headers=user["headers"])
    assert resend.json()["sent"] is False  # nothing to do once verified
