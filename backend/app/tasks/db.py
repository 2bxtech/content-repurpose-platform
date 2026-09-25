"""Database sessions for Celery tasks.

Each task body runs under its own asyncio.run() loop. asyncpg connections are
bound to the loop that opened them, so a module-level pooled engine breaks from
the second task on. Tasks get a fresh NullPool engine per run instead.
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings


@asynccontextmanager
async def task_session(workspace_id: uuid.UUID | None = None) -> AsyncIterator[AsyncSession]:
    """Yield a session; when workspace_id is given, scope it for RLS.

    The setting is session-level (not SET LOCAL) so it survives the commits a
    task makes; the connection is discarded afterwards, so it can't leak.
    """
    engine = create_async_engine(settings.get_database_url(), poolclass=NullPool)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            if workspace_id is not None:
                await session.execute(
                    text("SELECT set_config('app.workspace_id', :ws, false)"),
                    {"ws": str(workspace_id)},
                )
            yield session
    finally:
        await engine.dispose()
