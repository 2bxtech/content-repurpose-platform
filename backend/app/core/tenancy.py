"""Database-enforced tenant isolation (Postgres row-level security).

Every tenant table has a policy that only exposes rows whose workspace matches
`app.workspace_id`. Two things make those policies bite:

1. The app queries as an unprivileged role (settings.DB_APP_ROLE). Table owners
   and superusers skip RLS, so each new connection runs `SET ROLE` to it, while
   migrations keep running as the owner.
2. The workspace is re-applied at the start of *every* transaction from the
   session's `info`, so it survives the commits a request or task makes.

A few operations are cross-tenant by nature (finding a user by email at login,
registering, creating a workspace, the stuck-job sweeper). They opt out
explicitly with `rls_bypass`, which keeps every such place greppable.
"""

import logging
import re
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional, Union

from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import settings

logger = logging.getLogger(__name__)

ROLE_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")
_APPLY = text(
    "SELECT set_config('app.workspace_id', :ws, true), set_config('app.rls_bypass', :bypass, true)"
)


def enforce_app_role(sync_engine: Engine) -> None:
    """Make every new connection of this engine act as the unprivileged app role."""
    role = settings.DB_APP_ROLE
    if not role:
        return
    if not ROLE_NAME.match(role):  # SET ROLE can't take a bind parameter
        raise ValueError(f"Invalid DB_APP_ROLE: {role!r}")

    @event.listens_for(sync_engine, "connect")
    def _set_role(dbapi_connection, _record):
        dbapi_connection.run_async(lambda conn: conn.execute(f"SET ROLE {role}"))


@event.listens_for(Session, "after_begin")
def _apply_tenant_context(session: Session, _transaction, connection) -> None:
    connection.execute(_APPLY, _context_params(session))


def _context_params(session: Session) -> dict:
    return {
        "ws": session.info.get("workspace_id", ""),
        "bypass": "on" if session.info.get("rls_bypass") else "",
    }


async def _apply_now(session: AsyncSession) -> None:
    # after_begin covers future transactions; this covers the one in progress.
    await session.execute(_APPLY, _context_params(session.sync_session))


async def set_tenant(session: Optional[AsyncSession], workspace_id: Union[uuid.UUID, str, None]) -> None:
    """Scope the rest of this session to one workspace."""
    if session is None:
        return
    session.sync_session.info["workspace_id"] = str(workspace_id) if workspace_id else ""
    await _apply_now(session)


@asynccontextmanager
async def rls_bypass(session: Optional[AsyncSession]) -> AsyncIterator[None]:
    """Run a cross-tenant operation (identity lookups, tenant creation, maintenance).

    Not savepoint-aware: a set_config inside begin_nested() is undone by a
    savepoint rollback while `info` keeps its value, so don't nest these in one.
    """
    if session is None:
        yield
        return
    info = session.sync_session.info
    previous = info.get("rls_bypass", False)
    try:
        info["rls_bypass"] = True
        await _apply_now(session)
        yield
    except BaseException:
        info["rls_bypass"] = previous
        # The transaction is probably aborted and must be rolled back; the next one
        # starts from `info` (bypass off) via after_begin. Don't mask the real error.
        if session.in_transaction():
            try:
                await _apply_now(session)
            except Exception:
                pass
        raise
    info["rls_bypass"] = previous
    if session.in_transaction():
        await _apply_now(session)  # a healthy transaction must not stay bypassed


TENANT_TABLES = ["users", "workspaces", "documents", "transformations", "transformation_presets"]


async def rls_status(session: AsyncSession) -> dict:
    """Whether Postgres will apply RLS to this session's queries.

    It won't for superusers, BYPASSRLS roles, or the owner of a tenant table.
    """
    row = (
        await session.execute(
            text(
                "SELECT current_user, r.rolsuper, r.rolbypassrls,"
                " EXISTS (SELECT 1 FROM pg_class c"
                "         WHERE c.relname = ANY(:tables) AND c.relowner = r.oid)"
                " FROM pg_roles r WHERE r.rolname = current_user"
            ),
            {"tables": TENANT_TABLES},
        )
    ).one()
    role, superuser, bypassrls, owner = row
    return {"role": role, "enforced": not (superuser or bypassrls or owner)}


async def check_rls_enforced(session: AsyncSession, component: str) -> dict:
    """Startup guard: refuse to run in production with RLS silently off."""
    status = await rls_status(session)
    if not status["enforced"]:
        message = (
            f"{component}: Postgres row-level security is NOT enforced "
            f"(querying as {status['role']!r}); set DB_APP_ROLE and run migrations"
        )
        if settings.ENVIRONMENT == "production" and settings.DB_APP_ROLE:
            raise RuntimeError(message)
        logger.error(message)
    return status
