"""Refresh-session bookkeeping in Redis (real command semantics via fakeredis)."""

import fakeredis
import pytest

from app.core.config import settings
from app.services.redis_service import RedisService


@pytest.fixture
def service(monkeypatch):
    svc = RedisService.__new__(RedisService)
    svc.redis_client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(settings, "MAX_SESSIONS_PER_USER", 3)
    return svc


def _login(svc, user, jti):
    assert svc.create_user_session(user, jti, {"device_type": "test"})


def test_sessions_are_listed_from_the_index_without_scanning(service):
    _login(service, "u1", "a")
    _login(service, "u1", "b")
    _login(service, "u2", "z")

    assert sorted(s["refresh_token_jti"] for s in service.get_user_sessions("u1")) == ["a", "b"]
    assert service.redis_client.smembers("sessions:u1") == {"a", "b"}


def test_a_user_keeps_exactly_the_maximum_number_of_sessions(service):
    for jti in ["a", "b", "c"]:
        _login(service, "u1", jti)
    assert len(service.get_user_sessions("u1")) == 3  # at the limit: nothing revoked

    _login(service, "u1", "d")
    remaining = {s["refresh_token_jti"] for s in service.get_user_sessions("u1")}
    assert len(remaining) == 3 and "d" in remaining


def test_expired_sessions_are_pruned_from_the_index(service):
    _login(service, "u1", "a")
    _login(service, "u1", "b")
    service.redis_client.delete("session:u1:a")  # as if its TTL ran out

    assert [s["refresh_token_jti"] for s in service.get_user_sessions("u1")] == ["b"]
    assert service.redis_client.smembers("sessions:u1") == {"b"}


def test_consuming_and_revoking_keep_the_index_in_step(service):
    _login(service, "u1", "a")
    _login(service, "u1", "b")

    assert service.consume_user_session("u1", "a") is True
    assert service.consume_user_session("u1", "a") is False
    assert service.redis_client.smembers("sessions:u1") == {"b"}

    assert service.invalidate_all_user_sessions("u1") is True
    assert service.get_user_sessions("u1") == []
    assert not service.redis_client.exists("session:u1:b", "sessions:u1")


def test_sessions_from_before_the_index_are_backfilled_once(service):
    # A session written by the previous version: key only, no index entry.
    service.redis_client.setex("session:u9:legacy", 3600, '{"refresh_token_jti": "legacy", "last_activity": "x"}')

    assert service.backfill_session_index() == 1
    assert [s["refresh_token_jti"] for s in service.get_user_sessions("u9")] == ["legacy"]
    assert service.backfill_session_index() == 0  # once per deployment

    assert service.invalidate_all_user_sessions("u9") is True
    assert not service.redis_client.exists("session:u9:legacy")
