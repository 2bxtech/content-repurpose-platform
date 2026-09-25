"""Periodic maintenance run by Celery beat."""

import logging
from datetime import datetime, timedelta

from sqlalchemy import update

from app.core.celery_app import celery_app
from app.db.models.transformation import Transformation as TransformationDB
from app.models.transformation import TransformationStatus
from app.tasks.db import run_async, task_session

logger = logging.getLogger(__name__)

# Comfortably above the Celery hard time limit (celery_app.py), so a live task is
# never failed underneath itself.
STUCK_AFTER = timedelta(minutes=30)


@celery_app.task(name="app.tasks.maintenance_tasks.fail_stuck_transformations")
def fail_stuck_transformations() -> int:
    """Mark transformations that never finished (lost message, crashed worker,
    provider hang past every timeout) as FAILED so clients stop polling."""
    return run_async(_fail_stuck())


async def _fail_stuck() -> int:
    cutoff = datetime.utcnow() - STUCK_AFTER
    async with task_session() as db:
        result = await db.execute(
            update(TransformationDB)
            .where(
                TransformationDB.status.in_(
                    [TransformationStatus.PENDING, TransformationStatus.PROCESSING]
                ),
                TransformationDB.updated_at < cutoff,
            )
            .values(
                status=TransformationStatus.FAILED,
                error_message="Timed out waiting for processing",
                updated_at=datetime.utcnow(),
            )
        )
        await db.commit()
    if result.rowcount:
        logger.warning("Marked %d stuck transformations as failed", result.rowcount)
    return result.rowcount
