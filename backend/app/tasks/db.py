"""Event loop and database sessions for Celery tasks.

Celery task functions are synchronous. Each worker process runs its coroutines on
one long-lived event loop rather than a fresh asyncio.run() per task: the AI
provider manager is a process-wide singleton whose AsyncAnthropic/AsyncOpenAI
clients keep connection pools bound to the loop that created them, so closing the
loop after every task would break them from the second task on.
"""

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator, Awaitable, Optional, TypeVar

from celery.signals import worker_process_init
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.tenancy import check_rls_enforced, enforce_app_role

T = TypeVar("T")
logger = logging.getLogger(__name__)

_loop: Optional[asyncio.AbstractEventLoop] = None
_engine: Optional[AsyncEngine] = None
# Set when the startup RLS check fails in production. Celery swallows exceptions
# raised from signal handlers, so the block is enforced here, on every session.
_rls_block_reason: Optional[str] = None


def run_async(coro: Awaitable[T]) -> T:
    """Run a coroutine on this worker process's persistent event loop.

    Created lazily, so each prefork child gets its own loop after the fork."""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    task = _loop.create_task(coro)
    try:
        return _loop.run_until_complete(task)
    except BaseException:
        # Interrupted from outside the loop (e.g. Celery's soft time limit fires while
        # awaiting I/O): cancel and drain the task so it can't resume during the next one.
        task.cancel()
        _loop.run_until_complete(asyncio.gather(task, return_exceptions=True))
        raise


def _get_engine() -> AsyncEngine:
    # NullPool: every task gets a fresh connection that is closed afterwards, so
    # session-level settings (the RLS workspace) can never leak between tasks.
    global _engine
    if _engine is None:
        _engine = create_async_engine(settings.get_database_url(), poolclass=NullPool)
        enforce_app_role(_engine.sync_engine)
    return _engine


@asynccontextmanager
async def task_session(
    workspace_id: Optional[uuid.UUID] = None, *, bypass_rls: bool = False
) -> AsyncIterator[AsyncSession]:
    """Yield a session pinned to one connection, running as the app role.

    RLS context comes from the session's info and is applied at the start of
    every transaction (app.core.tenancy), so it survives the task's commits.
    Pass bypass_rls only for maintenance that spans workspaces.
    """
    if _rls_block_reason:
        raise RuntimeError(_rls_block_reason)
    async with _get_engine().connect() as conn:
        async with AsyncSession(bind=conn, expire_on_commit=False) as session:
            if workspace_id is not None:
                session.sync_session.info["workspace_id"] = str(workspace_id)
            if bypass_rls:
                session.sync_session.info["rls_bypass"] = True
            yield session


@worker_process_init.connect
def _check_rls_on_start(**_kwargs) -> None:
    """Refuse to run tasks in production if Postgres wouldn't apply row-level security."""

    async def check():
        async with task_session() as session:
            await check_rls_enforced(session, "worker")

    global _rls_block_reason
    try:
        run_async(check())
    except RuntimeError as e:
        # Raising here wouldn't stop the worker; refuse every task instead.
        _rls_block_reason = str(e)
        logger.critical("%s; this worker will refuse all tasks", e)
    except Exception as e:  # DB not reachable yet: tasks will fail loudly on their own
        logger.warning("Could not verify row-level security at worker start: %s", e)
