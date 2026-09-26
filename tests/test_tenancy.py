"""rls_bypass must never leave a session bypassed, whatever fails."""

from types import SimpleNamespace

import pytest

from app.core.tenancy import rls_bypass


class _FakeSession:
    def __init__(self, fail_on_call=None):
        self.sync_session = SimpleNamespace(info={})
        self.calls = 0
        self.fail_on_call = fail_on_call

    async def execute(self, *_args, **_kwargs):
        self.calls += 1
        if self.calls == self.fail_on_call:
            raise ConnectionError("connection dropped")

    def in_transaction(self):
        return True


async def test_bypass_is_scoped_to_the_block():
    session = _FakeSession()
    async with rls_bypass(session):
        assert session.sync_session.info["rls_bypass"] is True
    assert session.sync_session.info["rls_bypass"] is False


async def test_bypass_is_cleared_when_entering_fails():
    session = _FakeSession(fail_on_call=1)  # applying the bypass itself fails
    with pytest.raises(ConnectionError):
        async with rls_bypass(session):
            pass
    assert session.sync_session.info["rls_bypass"] is False


async def test_bypass_is_cleared_and_error_kept_when_body_fails():
    session = _FakeSession(fail_on_call=2)  # the reset after the failure also fails
    with pytest.raises(ValueError, match="boom"):
        async with rls_bypass(session):
            raise ValueError("boom")
    assert session.sync_session.info["rls_bypass"] is False


async def test_failed_reset_on_a_healthy_transaction_is_not_swallowed():
    session = _FakeSession(fail_on_call=2)
    with pytest.raises(ConnectionError):
        async with rls_bypass(session):
            pass
    assert session.sync_session.info["rls_bypass"] is False


async def test_worker_refuses_tasks_when_the_startup_rls_check_fails(monkeypatch):
    import app.tasks.db as task_db

    def failing_check(coro):
        coro.close()
        raise RuntimeError("worker: Postgres row-level security is NOT enforced")

    monkeypatch.setattr(task_db, "run_async", failing_check)
    monkeypatch.setattr(task_db, "_rls_block_reason", None)

    task_db._check_rls_on_start()  # must not raise: Celery would swallow it anyway

    with pytest.raises(RuntimeError, match="NOT enforced"):
        async with task_db.task_session():
            pass
