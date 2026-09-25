"""
Celery tasks for AI transformation processing.
"""

import uuid
from datetime import datetime
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
import asyncio
import json

from app.core.celery_app import celery_app
from app.core.config import settings
from app.models.transformation import TransformationType, TransformationStatus
from app.db.models.transformation import Transformation as TransformationDB
from app.services.workspace_service import workspace_service
from app.services.redis_service import redis_service
from app.services.ai_providers import get_ai_provider_manager, AIProviderError
from app.services.transformation_prompt import get_transformation_prompt, CONTENT_REPURPOSE_SYSTEM_PROMPT


async def send_websocket_notification(
    workspace_id: str,
    user_id: str,
    transformation_id: str,
    message_type: str,
    data: Dict[str, Any],
):
    """
    Publish a WebSocket notification via Redis pub/sub.
    The API process subscribes to 'websocket:broadcast' and forwards to connected clients.
    This replaces the HTTP-loopback approach that breaks when API and Celery are separate processes.
    """
    try:
        if not redis_service.is_connected():
            return

        payload = {
            "type": message_type,
            "data": {
                "transformation_id": transformation_id,
                "workspace_id": workspace_id,
                "user_id": user_id,
                **data,
            },
            "target": "user",
            "target_id": user_id,
        }
        redis_service.redis_client.publish("websocket:broadcast", json.dumps(payload))
    except Exception as e:
        # Never fail the transformation because of a notification error
        print(f"Error sending WebSocket notification: {e}")


# Create async database session for tasks
async_engine = create_async_engine(
    settings.get_database_url(async_driver=True), echo=settings.DEBUG
)

AsyncSessionLocal = sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False
)


class TransformationTaskStatus:
    """Task status tracking"""

    PENDING = "pending"
    STARTED = "started"
    PROGRESS = "progress"
    SUCCESS = "success"
    FAILURE = "failure"
    RETRY = "retry"


# get_transformation_prompt imported from app.services.transformation_prompt


async def call_ai_provider(prompt: str, ai_provider: str = None) -> Dict[str, Any]:
    """
    Call the configured AI provider using the new provider manager
    """
    manager = get_ai_provider_manager()

    try:
        response = await manager.generate_text(
            prompt=prompt,
            preferred_provider=ai_provider,
            system_prompt=CONTENT_REPURPOSE_SYSTEM_PROMPT,
            max_tokens=settings.AI_MAX_TOKENS,
            temperature=settings.AI_TEMPERATURE,
        )

        return {
            "content": response.content,
            "provider": response.provider,
            "model": response.model,
            "tokens_used": response.usage_metrics.total_tokens,
        }

    except AIProviderError as e:
        raise Exception(f"AI Provider error: {str(e)}")


async def call_claude_api(prompt: str) -> Dict[str, Any]:
    """Call Anthropic Claude API using the provider manager"""
    return await call_ai_provider(prompt, "anthropic")


async def call_openai_api(prompt: str) -> Dict[str, Any]:
    """Call OpenAI GPT API using the provider manager"""
    return await call_ai_provider(prompt, "openai")


@celery_app.task(
    bind=True, name="app.tasks.transformation_tasks.process_transformation"
)
def process_transformation_task(
    self,
    transformation_id: str,
    document_path: str,
    transformation_type: str,
    parameters: Dict[str, Any],
    workspace_id: str,
    user_id: str,
):
    """
    Celery task to process AI transformation
    """
    # Convert string IDs back to UUIDs
    transformation_uuid = uuid.UUID(transformation_id)
    workspace_uuid = uuid.UUID(workspace_id)
    user_uuid = uuid.UUID(user_id)

    # Update task status to started
    self.update_state(
        state=TransformationTaskStatus.STARTED,
        meta={"progress": 0, "status": "Starting transformation..."},
    )

    # Run the async transformation in a new event loop
    return asyncio.run(
        _process_transformation_async(
            self,
            transformation_uuid,
            document_path,
            TransformationType(transformation_type),
            parameters,
            workspace_uuid,
            user_uuid,
        )
    )


async def _process_transformation_async(
    task_instance,
    transformation_id: uuid.UUID,
    document_path: str,
    transformation_type: TransformationType,
    parameters: Dict[str, Any],
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
):
    """
    Async implementation of transformation processing
    """
    async with AsyncSessionLocal() as db:
        try:
            # Update task progress
            task_instance.update_state(
                state=TransformationTaskStatus.PROGRESS,
                meta={"progress": 10, "status": "Loading transformation..."},
            )

            # Send WebSocket notification: transformation started
            await send_websocket_notification(
                workspace_id=str(workspace_id),
                user_id=str(user_id),
                transformation_id=str(transformation_id),
                message_type="transformation_started",
                data={"progress": 10, "status": "Loading transformation..."},
            )

            # Get transformation record
            await workspace_service.set_workspace_context(db, workspace_id)

            stmt = select(TransformationDB).where(
                TransformationDB.id == transformation_id
            )
            result = await db.execute(stmt)
            transformation = result.scalar_one_or_none()

            if not transformation:
                raise Exception("Transformation not found")

            # Idempotency guard: if another worker already picked this up, bail early.
            # Without this check, Celery retries fire a second AI call.
            if transformation.status == TransformationStatus.PROCESSING:
                return {
                    "transformation_id": str(transformation_id),
                    "status": "skipped_already_processing",
                }

            # Update status to processing
            transformation.status = TransformationStatus.PROCESSING
            transformation.updated_at = datetime.utcnow()
            await db.commit()

            # Update task progress
            task_instance.update_state(
                state=TransformationTaskStatus.PROGRESS,
                meta={"progress": 20, "status": "Reading document content..."},
            )

            # Read document content
            try:
                with open(document_path, "r", encoding="utf-8") as file:
                    document_content = file.read()
            except Exception as e:
                raise Exception(f"Failed to read document: {str(e)}")

            # Update task progress
            task_instance.update_state(
                state=TransformationTaskStatus.PROGRESS,
                meta={"progress": 40, "status": "Generating AI prompt..."},
            )

            # Prepare the prompt
            prompt = get_transformation_prompt(
                transformation_type, document_content, parameters
            )

            # Update task progress
            task_instance.update_state(
                state=TransformationTaskStatus.PROGRESS,
                meta={"progress": 60, "status": "Calling AI provider..."},
            )

            # Send WebSocket notification: AI processing
            await send_websocket_notification(
                workspace_id=str(workspace_id),
                user_id=str(user_id),
                transformation_id=str(transformation_id),
                message_type="transformation_progress",
                data={"progress": 60, "status": "Calling AI provider..."},
            )

            # Call AI API
            ai_result = await call_ai_provider(prompt)

            # Update task progress
            task_instance.update_state(
                state=TransformationTaskStatus.PROGRESS,
                meta={"progress": 80, "status": "Saving results..."},
            )

            # Update transformation with result
            transformation.result = ai_result["content"]
            transformation.status = TransformationStatus.COMPLETED
            transformation.updated_at = datetime.utcnow()
            transformation.ai_provider = ai_result["provider"]
            transformation.ai_model = ai_result["model"]
            transformation.tokens_used = ai_result.get("tokens_used")

            await db.commit()

            # Update task progress to completed
            task_instance.update_state(
                state=TransformationTaskStatus.SUCCESS,
                meta={
                    "progress": 100,
                    "status": "Transformation completed successfully!",
                },
            )

            # Send WebSocket notification: transformation completed
            await send_websocket_notification(
                workspace_id=str(workspace_id),
                user_id=str(user_id),
                transformation_id=str(transformation_id),
                message_type="transformation_completed",
                data={
                    "progress": 100,
                    "status": "Transformation completed successfully!",
                    "result_preview": ai_result["content"][:200] + "..."
                    if len(ai_result["content"]) > 200
                    else ai_result["content"],
                    "provider": ai_result["provider"],
                    "tokens_used": ai_result.get("tokens_used"),
                },
            )

            return {
                "transformation_id": str(transformation_id),
                "status": "completed",
                "result": ai_result["content"][:100] + "..."
                if len(ai_result["content"]) > 100
                else ai_result["content"],
                "provider": ai_result["provider"],
                "tokens_used": ai_result.get("tokens_used"),
            }

        except Exception as e:
            # Update transformation with error
            if "transformation" in locals():
                transformation.status = TransformationStatus.FAILED
                transformation.error_message = (
                    f"Error processing transformation: {str(e)}"
                )
                transformation.updated_at = datetime.utcnow()
                await db.commit()

            # Update task status to failure
            task_instance.update_state(
                state=TransformationTaskStatus.FAILURE,
                meta={"progress": 0, "status": f"Transformation failed: {str(e)}"},
            )

            # Send WebSocket failure notification
            await send_websocket_notification(
                workspace_id=str(workspace_id),
                user_id=str(user_id),
                transformation_id=str(transformation_id),
                message_type="transformation_failed",
                data={"error_message": str(e)},
            )

            # Re-raise for Celery retry mechanism
            raise task_instance.retry(exc=e, countdown=60, max_retries=3)

        finally:
            await workspace_service.clear_workspace_context(db)


@celery_app.task(name="app.tasks.transformation_tasks.get_task_status")
def get_task_status(task_id: str):
    """
    Get the status of a transformation task
    """
    result = celery_app.AsyncResult(task_id)

    if result.state == "PENDING":
        return {
            "task_id": task_id,
            "status": "pending",
            "progress": 0,
            "message": "Task is waiting to be processed...",
        }
    elif result.state == TransformationTaskStatus.STARTED:
        return {
            "task_id": task_id,
            "status": "started",
            "progress": result.info.get("progress", 0),
            "message": result.info.get("status", "Task started..."),
        }
    elif result.state == TransformationTaskStatus.PROGRESS:
        return {
            "task_id": task_id,
            "status": "progress",
            "progress": result.info.get("progress", 0),
            "message": result.info.get("status", "Processing..."),
        }
    elif result.state == TransformationTaskStatus.SUCCESS:
        return {
            "task_id": task_id,
            "status": "success",
            "progress": 100,
            "message": "Task completed successfully!",
            "result": result.result,
        }
    elif result.state == TransformationTaskStatus.FAILURE:
        return {
            "task_id": task_id,
            "status": "failed",
            "progress": 0,
            "message": f"Task failed: {str(result.info)}",
            "error": str(result.info),
        }
    else:
        return {
            "task_id": task_id,
            "status": result.state.lower(),
            "progress": 0,
            "message": f"Unknown task state: {result.state}",
        }


@celery_app.task(name="app.tasks.transformation_tasks.cancel_task")
def cancel_task(task_id: str):
    """
    Cancel a running transformation task
    """
    celery_app.control.revoke(task_id, terminate=True)
    return {"task_id": task_id, "status": "cancelled"}
