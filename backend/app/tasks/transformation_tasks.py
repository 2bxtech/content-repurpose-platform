"""Celery task that runs AI transformations outside the request cycle.

POST /api/transformations stores a PENDING row and enqueues this task with the
row id. The worker loads the document text from Postgres (it shares no disk with
the API), runs the shared executor, and publishes progress events to Redis,
which every API replica relays to the owner's WebSocket connections.
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict

from sqlalchemy import update

from app.core.celery_app import celery_app
from app.db.models.document import Document as DocumentDB
from app.db.models.transformation import Transformation as TransformationDB
from app.models.transformation import TransformationStatus
from app.services.redis_service import redis_service
from app.services.transformation_runner import execute_transformation, finish
from app.tasks.db import run_async, task_session

logger = logging.getLogger(__name__)

WEBSOCKET_CHANNEL = "websocket:broadcast"


def publish_progress(transformation: TransformationDB, event: str, **data: Any) -> None:
    """Best-effort progress event for the transformation's owner; never fails the task."""
    if redis_service.redis_client is None:
        return
    payload = {
        "type": event,
        "target": "user",
        "target_id": str(transformation.user_id),
        "data": {
            "transformation_id": str(transformation.id),
            "workspace_id": str(transformation.workspace_id),
            "status": getattr(transformation.status, "value", str(transformation.status)),
            **data,
        },
    }
    try:
        redis_service.redis_client.publish(WEBSOCKET_CHANNEL, json.dumps(payload, default=str))
    except Exception as e:
        logger.warning("Could not publish %s for %s: %s", event, transformation.id, e)


@celery_app.task(name="app.tasks.transformation_tasks.process_transformation")
def process_transformation_task(transformation_id: str, workspace_id: str) -> Dict[str, Any]:
    return run_async(_process(uuid.UUID(transformation_id), uuid.UUID(workspace_id)))


async def _process(transformation_id: uuid.UUID, workspace_id: uuid.UUID) -> Dict[str, Any]:
    async with task_session(workspace_id) as db:
        # Atomically claim the row. A duplicate delivery (or a second worker) finds it
        # no longer PENDING and does nothing, so the billed AI call happens at most once.
        claimed = (
            await db.execute(
                update(TransformationDB)
                .where(
                    TransformationDB.id == transformation_id,
                    TransformationDB.workspace_id == workspace_id,
                    TransformationDB.status == TransformationStatus.PENDING,
                )
                .values(status=TransformationStatus.PROCESSING, updated_at=datetime.utcnow())
                .returning(TransformationDB.id)
            )
        ).scalar_one_or_none()
        await db.commit()
        if claimed is None:
            logger.info("Transformation %s not pending; skipping", transformation_id)
            return {"transformation_id": str(transformation_id), "status": "skipped"}

        transformation = await db.get(TransformationDB, transformation_id)
        publish_progress(transformation, "transformation_started", progress=10)
        try:
            document = await db.get(DocumentDB, transformation.document_id)
            transformation = await execute_transformation(
                db, transformation, document.extracted_text if document else ""
            )
        except Exception:
            # Anything the executor didn't handle (DB errors, bugs): fail the row
            # rather than leave the client polling a PROCESSING job.
            logger.exception("Transformation %s crashed", transformation_id)
            transformation = await finish(
                db, transformation, error="Unexpected error while processing"
            )

        if transformation.status == TransformationStatus.COMPLETED:
            publish_progress(
                transformation,
                "transformation_completed",
                progress=100,
                result_preview=(transformation.result or "")[:200],
                provider=transformation.ai_provider,
                tokens_used=transformation.tokens_used,
            )
        else:
            publish_progress(
                transformation, "transformation_failed", error_message=transformation.error_message
            )
        return {"transformation_id": str(transformation_id), "status": transformation.status.value}
