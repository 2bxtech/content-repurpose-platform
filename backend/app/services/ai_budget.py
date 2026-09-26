"""Per-workspace monthly AI limits: request count and spend.

Checked before any AI work is accepted (HTTP 402 when exhausted) and again by
the worker right before the billed provider call, which catches work queued
while the workspace was still under its limit. Limits live in the workspace's
settings (`ai_requests_per_month`, `ai_monthly_budget_usd`); workspaces without
them use the defaults from config. Months are calendar months in UTC.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models.transformation import Transformation
from app.db.models.workspace import Workspace


@dataclass(frozen=True)
class AIBudgetStatus:
    requests_used: int
    requests_limit: int
    spend_usd: float
    budget_usd: float
    period_start: datetime

    @property
    def exhausted_reason(self) -> Optional[str]:
        if self.requests_used >= self.requests_limit:
            return f"Monthly AI request limit reached ({self.requests_limit})."
        if self.spend_usd >= self.budget_usd:
            return f"Monthly AI budget reached (${self.budget_usd:.2f})."
        return None


def month_start(now: Optional[datetime] = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def ai_budget_status(db: AsyncSession, workspace_id: uuid.UUID) -> AIBudgetStatus:
    start = month_start()
    workspace_settings = (
        await db.execute(select(Workspace.settings).where(Workspace.id == workspace_id))
    ).scalar_one_or_none() or {}
    used, spend = (
        await db.execute(
            select(func.count(Transformation.id), func.coalesce(func.sum(Transformation.ai_cost), 0.0)).where(
                Transformation.workspace_id == workspace_id,
                Transformation.created_at >= start,
                Transformation.deleted_at.is_(None),
            )
        )
    ).one()
    return AIBudgetStatus(
        requests_used=int(used),
        requests_limit=int(workspace_settings.get("ai_requests_per_month", settings.AI_WORKSPACE_MONTHLY_REQUESTS)),
        spend_usd=float(spend),
        budget_usd=float(workspace_settings.get("ai_monthly_budget_usd", settings.AI_WORKSPACE_MONTHLY_BUDGET_USD)),
        period_start=start,
    )


async def require_ai_budget(db: Optional[AsyncSession], workspace_id: uuid.UUID) -> None:
    """Raise 402 if the workspace can't start more AI work this month."""
    if db is None:  # in-memory dev mode has no usage history
        return
    reason = (await ai_budget_status(db, workspace_id)).exhausted_reason
    if reason:
        raise HTTPException(
            status_code=402,
            detail=f"{reason} It resets at the start of next month (UTC).",
        )
