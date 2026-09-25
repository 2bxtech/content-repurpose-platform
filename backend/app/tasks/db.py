"""Event loop and database sessions for Celery tasks.

Celery task functions are synchronous. Each worker process runs its coroutines on
one long-lived event loop rather than a fresh asyncio.run() per task: the AI
provider manager is a process-wide singleton whose AsyncAnthropic/AsyncOpenAI
clients keep connection pools bound to the loop that created them, so closing the
loop after every task would break them from the second task on.
"""

import asyncio
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator, Awaitable, Optional, TypeVar

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings

T = TypeVar("T")

_loop: Optional[asyncio.AbstractEventLoop] = None
_engine: Optional[AsyncEngine] = None


def run_async(coro: Awaitable[T]) -> T:
    """Run a coroutine on this worker process's persistent event loop.

    Created lazily, so each prefork child gets its own loop after the fork."""
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop.run_until_complete(coro)


def _get_engine() -> AsyncEngine:
    # NullPool: every task gets a fresh connection that is closed afterwards, so
    # session-level settings (the RLS workspace) can never leak between tasks.
    global _engine
    if _engine is None:
        _engine = create_async_engine(settings.get_database_url(), poolclass=NullPool)
    return _engine


@asynccontextmanager
async def task_session(workspace_id: Optional[uuid.UUID] = None) -> AsyncIterator[AsyncSession]:
    """Yield a session pinned to a single connection.

    When workspace_id is given the connection is scoped for RLS with a
    session-level setting, which survives the several commits a task makes
    (SET LOCAL would reset at the first one).
    """
    async with _get_engine().connect() as conn:
        if workspace_id is not None:
            await conn.execute(
                text("SELECT set_config('app.workspace_id', :ws, false)"),
                {"ws": str(workspace_id)},
            )
            await conn.commit()
        async with AsyncSession(bind=conn, expire_on_commit=False) as session:
            yield session
