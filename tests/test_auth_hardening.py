"""Unit tests for the operator gate and email identity rules."""

import pytest
from fastapi import HTTPException

from app.api.routes.auth import require_platform_admin
from app.core.config import settings
from app.models.auth import UserCreate

ADMIN_ID = "7d1c2a4e-0000-4000-8000-000000000001"


async def test_platform_admin_is_granted_by_user_id(monkeypatch):
    monkeypatch.setattr(settings, "PLATFORM_ADMIN_USER_IDS", f" {ADMIN_ID.upper()} , other ")
    user = {"id": ADMIN_ID, "email": "ops@example.com", "is_active": True}
    assert await require_platform_admin(user) is user


@pytest.mark.parametrize("allowlist", ["", "ops@example.com", "someone-else"])
async def test_platform_admin_rejects_everyone_else(monkeypatch, allowlist):
    # An email on the list must not grant access: emails aren't verified at signup.
    monkeypatch.setattr(settings, "PLATFORM_ADMIN_USER_IDS", allowlist)
    with pytest.raises(HTTPException) as exc:
        await require_platform_admin({"id": ADMIN_ID, "email": "ops@example.com"})
    assert exc.value.status_code == 403


def test_registration_normalises_email_case():
    user = UserCreate(email="Ops.Admin@Example.COM", username="ops", password="Sufficient1!pass")
    assert user.email == "ops.admin@example.com"


def test_consume_reports_unavailable_store(monkeypatch):
    from app.services.redis_service import redis_service

    monkeypatch.setattr(redis_service, "redis_client", None)
    assert redis_service.consume_user_session("u1", "jti1") is None
