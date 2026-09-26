"""Run one transformation: prompt -> AI provider -> persisted result.

Shared by the Celery worker (default path for POST /api/transformations) and the
synchronous endpoints (/quick, /refine), so every path records the same status,
usage and cost fields.

Status moves PENDING -> PROCESSING -> COMPLETED | FAILED. The final write only
applies while the row is still PROCESSING, so a result that arrives after the
stuck-job sweeper has already failed the row can't silently flip it back.
"""

import logging
import time
from datetime import datetime
from typing import Optional

from opentelemetry.trace import Status, StatusCode
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.telemetry import span
from app.db.models.transformation import Transformation as TransformationDB
from app.models.transformation import TransformationStatus
from app.services.ai_providers import AIProviderError, get_ai_provider_manager
from app.services.transformation_prompt import (
    CONTENT_REPURPOSE_SYSTEM_PROMPT,
    get_transformation_prompt,
)

logger = logging.getLogger(__name__)


async def execute_transformation(
    db: AsyncSession,
    transformation: TransformationDB,
    content: str,
    prompt: Optional[str] = None,
) -> TransformationDB:
    """Call the provider manager (which handles failover and retries) and persist
    COMPLETED with usage/cost, or FAILED with a reason. Never raises for AI errors."""
    with span(
        "transformation.execute",
        **{
            "transformation.id": _str_or_none(getattr(transformation, "id", None)),
            "transformation.type": getattr(
                getattr(transformation, "transformation_type", None), "value", None
            ),
            "workspace.id": _str_or_none(getattr(transformation, "workspace_id", None)),
        },
    ) as current:
        result = await _execute(db, transformation, content, prompt)
        current.set_attribute("transformation.status", getattr(result.status, "value", str(result.status)))
        for attribute, field in (("ai.provider", "ai_provider"), ("ai.tokens", "tokens_used"), ("ai.cost_usd", "ai_cost")):
            value = getattr(result, field, None)
            if value is not None:
                current.set_attribute(attribute, value)
        if result.status == TransformationStatus.FAILED:
            current.set_status(Status(StatusCode.ERROR, result.error_message or "failed"))
        return result


def _str_or_none(value) -> Optional[str]:
    return None if value is None else str(value)


async def _execute(
    db: AsyncSession,
    transformation: TransformationDB,
    content: str,
    prompt: Optional[str],
) -> TransformationDB:
    if transformation.status != TransformationStatus.PROCESSING:
        transformation.status = TransformationStatus.PROCESSING
        transformation.updated_at = datetime.utcnow()
        await db.commit()

    content = (content or "").strip()
    if not content:
        return await finish(db, transformation, error="Document has no extractable text content")

    started = time.perf_counter()
    try:
        response = await get_ai_provider_manager().generate_text(
            prompt=prompt
            or get_transformation_prompt(
                transformation.transformation_type, content, transformation.parameters or {}
            ),
            system_prompt=CONTENT_REPURPOSE_SYSTEM_PROMPT,
        )
    except AIProviderError as e:
        logger.warning("Transformation %s failed: %s", transformation.id, e)
        return await finish(db, transformation, error=f"AI provider error: {e}")
    except Exception:
        logger.exception("Unexpected error in transformation %s", transformation.id)
        return await finish(db, transformation, error="Unexpected error while generating content")

    usage = response.usage_metrics
    return await finish(
        db,
        transformation,
        result=response.content,
        ai_provider=response.provider,
        tokens_used=usage.total_tokens,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        ai_cost=usage.total_cost,
        processing_time_seconds=int(time.perf_counter() - started),
    )


async def finish(
    db: AsyncSession, transformation: TransformationDB, error: Optional[str] = None, **fields
) -> TransformationDB:
    """Write the terminal state if the row is still PROCESSING; return the row as stored."""
    transformation_id = transformation.id  # read before rollback expires attributes
    await db.rollback()  # discard any half-done work from a failed statement
    result = await db.execute(
        update(TransformationDB)
        .where(
            TransformationDB.id == transformation_id,
            TransformationDB.status == TransformationStatus.PROCESSING,
        )
        .values(
            status=TransformationStatus.FAILED if error else TransformationStatus.COMPLETED,
            error_message=error,
            updated_at=datetime.utcnow(),
            **fields,
        )
    )
    await db.commit()
    if result.rowcount == 0:
        logger.warning(
            "Transformation %s was finalised elsewhere (e.g. timed out); result discarded",
            transformation_id,
        )
    await db.refresh(transformation)
    return transformation
