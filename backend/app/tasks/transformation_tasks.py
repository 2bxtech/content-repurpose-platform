"""Celery task that runs AI transformations outside the request cycle.

POST /api/transformations stores a PENDING row and enqueues this task with the
row id. The worker loads the document text from Postgres (it shares no disk with
the API), runs the shared executor, and publishes progress events to Redis,
which every API replica relays to the owner's WebSocket connections.
"""

import asyncio
import json
import logging
import uuid
from typing import Any, Dict

from app.core.celery_app import celery_app
from app.db.models.document import Document as DocumentDB
from app.db.models.transformation import Transformation as TransformationDB
from app.models.transformation import TransformationStatus
from app.services.redis_service import redis_service
from app.services.transformation_runner import execute_transformation
from app.tasks.db import task_session

logger = logging.getLogger(__name__)

WEBSOCKET_CHANNEL = "websocket:broadcast"


def publish_progress(transformation: TransformationDB, event: str, **data: Any) -> None:
    """Best-effort progress event for the transformation's owner; never fails the task."""
    if not redis_service.is_connected():
        return
    payload = {
        "type": event,
        "target": "user",
        "target_id": str(transformation.user_id),
        "data": {
            "transformation_id": str(transformation.id),
            "workspace_id": str(transformation.workspace_id),
            "status": transformation.status.value
            if hasattr(transformation.status, "value")
            else str(transformation.status),
            **data,
        },
    }
    try:
        redis_service.redis_client.publish(WEBSOCKET_CHANNEL, json.dumps(payload, default=str))
    except Exception as e:
        logger.warning("Could not publish %s for %s: %s", event, transformation.id, e)


@celery_app.task(
    name="app.tasks.transformation_tasks.process_transformation",
    acks_late=True,  # redeliver if the worker dies mid-task
    reject_on_worker_lost=True,
)
def process_transformation_task(transformation_id: str, workspace_id: str) -> Dict[str, Any]:
    return asyncio.run(_process(uuid.UUID(transformation_id), uuid.UUID(workspace_id)))


async def _process(transformation_id: uuid.UUID, workspace_id: uuid.UUID) -> Dict[str, Any]:
    async with task_session(workspace_id) as db:
        transformation = await db.get(TransformationDB, transformation_id)
        if transformation is None or transformation.workspace_id != workspace_id:
            logger.error("Transformation %s not found in workspace %s", transformation_id, workspace_id)
            return {"transformation_id": str(transformation_id), "status": "not_found"}

        # Idempotency: a redelivered message must not trigger a second (billed) AI call.
        if transformation.status != TransformationStatus.PENDING:
            return {"transformation_id": str(transformation_id), "status": "skipped"}

        document = await db.get(DocumentDB, transformation.document_id)
        publish_progress(transformation, "transformation_started", progress=10)

        transformation = await execute_transformation(
            db, transformation, document.extracted_text if document else ""
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
