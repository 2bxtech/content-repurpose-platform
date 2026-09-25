"""Run one transformation: prompt -> AI provider -> persisted result.

Shared by the Celery worker (default path for POST /api/transformations) and the
synchronous endpoints (/quick, /refine), so every path records the same status,
usage and cost fields.
"""

import logging
import time
from datetime import datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

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
    """Mark PROCESSING, call the provider manager (which handles failover and
    retries), then persist COMPLETED with usage/cost or FAILED with a reason."""
    content = (content or "").strip()
    if not content:
        return await _finish(db, transformation, error="Document has no extractable text content")

    transformation.status = TransformationStatus.PROCESSING
    transformation.updated_at = datetime.utcnow()
    await db.commit()

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
        return await _finish(db, transformation, error=f"AI provider error: {e}")

    usage = response.usage_metrics
    transformation.result = response.content
    transformation.ai_provider = response.provider
    transformation.tokens_used = usage.total_tokens
    transformation.input_tokens = usage.input_tokens
    transformation.output_tokens = usage.output_tokens
    transformation.ai_cost = usage.total_cost
    transformation.processing_time_seconds = int(time.perf_counter() - started)
    return await _finish(db, transformation)


async def _finish(
    db: AsyncSession, transformation: TransformationDB, error: Optional[str] = None
) -> TransformationDB:
    transformation.status = TransformationStatus.FAILED if error else TransformationStatus.COMPLETED
    transformation.error_message = error
    transformation.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(transformation)
    return transformation
