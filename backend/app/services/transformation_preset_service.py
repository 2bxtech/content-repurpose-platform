# backend/app/services/transformation_preset_service.py
"""Service layer for transformation preset operations"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from typing import Optional, List
from uuid import UUID
from datetime import datetime
import logging

from app.db.models.transformation_preset import TransformationPreset
from app.models.transformation_preset import (
    TransformationPresetCreate,
    TransformationPresetUpdate,
    TransformationType
)

logger = logging.getLogger(__name__)


async def create_preset(
    db: AsyncSession,
    preset_data: TransformationPresetCreate,
    workspace_id: UUID,
    user_id: UUID
) -> TransformationPreset:
    """Create a new transformation preset"""
    
    # Check for duplicate name in workspace
    stmt = select(TransformationPreset).where(
        and_(
            TransformationPreset.workspace_id == workspace_id,
            TransformationPreset.name == preset_data.name,
            TransformationPreset.deleted_at.is_(None)
        )
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise ValueError(f"Preset with name '{preset_data.name}' already exists in this workspace")
    
    # Create preset (keep user_id for ownership tracking even when shared)
    preset = TransformationPreset(
        workspace_id=workspace_id,
        user_id=user_id,
        name=preset_data.name,
        description=preset_data.description,
        transformation_type=preset_data.transformation_type.value,
        parameters=preset_data.parameters,
        is_shared=preset_data.is_shared
    )
    
    db.add(preset)
    await db.commit()
    await db.refresh(preset)
    
    logger.info(f"Created transformation preset '{preset.name}' (ID: {preset.id}) in workspace {workspace_id}")
    
    return preset


async def get_presets(
    db: AsyncSession,
    workspace_id: UUID,
    user_id: UUID,
    transformation_type: Optional[TransformationType] = None,
    include_shared: bool = True,
    skip: int = 0,
    limit: int = 100
) -> tuple[List[TransformationPreset], int]:
    """Get presets for workspace and user"""
    
    # Build query: user's presets + shared workspace presets
    filters = [
        TransformationPreset.workspace_id == workspace_id,
        TransformationPreset.deleted_at.is_(None)
    ]
    
    if include_shared:
        filters.append(
            or_(
                TransformationPreset.user_id == user_id,
                TransformationPreset.is_shared
            )
        )
    else:
        filters.append(TransformationPreset.user_id == user_id)
    
    if transformation_type:
        filters.append(TransformationPreset.transformation_type == transformation_type.value)
    
    # Count query
    count_stmt = select(func.count()).select_from(TransformationPreset).where(and_(*filters))
    count_result = await db.execute(count_stmt)
    total = count_result.scalar()
    
    # List query with pagination
    stmt = (
        select(TransformationPreset)
        .where(and_(*filters))
        .order_by(TransformationPreset.usage_count.desc(), TransformationPreset.name)
        .offset(skip)
        .limit(limit)
    )
    
    result = await db.execute(stmt)
    presets = result.scalars().all()
    
    return presets, total


async def get_preset_by_id(
    db: AsyncSession,
    preset_id: UUID,
    workspace_id: UUID,
    user_id: UUID
) -> Optional[TransformationPreset]:
    """Get a single preset by ID"""
    
    stmt = select(TransformationPreset).where(
        and_(
            TransformationPreset.id == preset_id,
            TransformationPreset.workspace_id == workspace_id,
            TransformationPreset.deleted_at.is_(None),
            or_(
                TransformationPreset.user_id == user_id,
                TransformationPreset.is_shared
            )
        )
    )
    
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def update_preset(
    db: AsyncSession,
    preset_id: UUID,
    preset_data: TransformationPresetUpdate,
    workspace_id: UUID,
    user_id: UUID
) -> Optional[TransformationPreset]:
    """Update a preset (only owner can update)"""
    
    # Get preset and verify ownership
    preset = await get_preset_by_id(db, preset_id, workspace_id, user_id)
    if not preset:
        return None
    
    if preset.user_id != user_id:
        raise PermissionError("Only the preset owner can update it")
    
    # Update fields
    update_data = preset_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(preset, field, value)
    
    await db.commit()
    await db.refresh(preset)
    
    logger.info(f"Updated transformation preset '{preset.name}' (ID: {preset.id})")
    
    return preset


async def delete_preset(
    db: AsyncSession,
    preset_id: UUID,
    workspace_id: UUID,
    user_id: UUID
) -> bool:
    """Soft delete a preset (only owner can delete)"""
    
    preset = await get_preset_by_id(db, preset_id, workspace_id, user_id)
    if not preset:
        return False
    
    if preset.user_id != user_id:
        raise PermissionError("Only the preset owner can delete it")
    
    preset.deleted_at = datetime.utcnow()
    await db.commit()
    
    logger.info(f"Deleted transformation preset '{preset.name}' (ID: {preset.id})")
    
    return True


async def increment_usage_count(
    db: AsyncSession,
    preset_id: UUID,
    workspace_id: UUID
) -> None:
    """Increment usage count when preset is used"""
    
    stmt = select(TransformationPreset).where(
        and_(
            TransformationPreset.id == preset_id,
            TransformationPreset.workspace_id == workspace_id,
            TransformationPreset.deleted_at.is_(None)
        )
    )
    
    result = await db.execute(stmt)
    preset = result.scalar_one_or_none()
    
    if preset:
        preset.usage_count += 1
        await db.commit()
        logger.debug(f"Incremented usage count for preset '{preset.name}' to {preset.usage_count}")
