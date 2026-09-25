# backend/app/api/routes/transformation_presets.py
"""API endpoints for transformation presets"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID
import logging

from app.core.database import get_db_session
from app.api.routes.auth import get_current_active_user
from app.models.transformation_preset import (
    TransformationPresetCreate,
    TransformationPresetUpdate,
    TransformationPresetResponse,
    TransformationPresetList,
    TransformationType
)
from app.services import transformation_preset_service

router = APIRouter(tags=["Transformation Presets"])
logger = logging.getLogger(__name__)


async def get_current_workspace(
    current_user: dict = Depends(get_current_active_user)
) -> UUID:
    """Extract workspace_id from current user"""
    workspace_id = current_user.get("workspace_id")
    if not workspace_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User is not associated with a workspace"
        )
    return UUID(workspace_id) if isinstance(workspace_id, str) else workspace_id


@router.post(
    "",
    response_model=TransformationPresetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new transformation preset",
    description="""
    Create a new transformation preset for quick reuse.
    
    - **name**: Unique preset name within workspace
    - **transformation_type**: Type of transformation (BLOG_POST, SOCIAL_MEDIA, etc.)
    - **parameters**: Configuration parameters for the transformation
    - **is_shared**: Share with entire workspace (default: false, personal preset)
    """
)
async def create_preset(
    preset_data: TransformationPresetCreate,
    workspace_id: UUID = Depends(get_current_workspace),
    current_user: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Create a new transformation preset"""
    try:
        preset = await transformation_preset_service.create_preset(
            db=db,
            preset_data=preset_data,
            workspace_id=workspace_id,
            user_id=UUID(current_user["id"])
        )
        
        response = TransformationPresetResponse.from_orm(preset)
        response.is_owner = True
        return response
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error creating preset: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create transformation preset"
        )


@router.get(
    "",
    response_model=TransformationPresetList,
    summary="List transformation presets",
    description="""
    List all transformation presets available to the user.
    
    Returns both personal presets and workspace-shared presets.
    Ordered by usage_count (most popular first) then alphabetically.
    """
)
async def list_presets(
    transformation_type: Optional[TransformationType] = Query(None, description="Filter by transformation type"),
    include_shared: bool = Query(True, description="Include workspace shared presets"),
    skip: int = Query(0, ge=0, description="Number of presets to skip"),
    limit: int = Query(100, ge=1, le=100, description="Number of presets to return"),
    workspace_id: UUID = Depends(get_current_workspace),
    current_user: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """List all transformation presets available to the user"""
    try:
        presets, total = await transformation_preset_service.get_presets(
            db=db,
            workspace_id=workspace_id,
            user_id=UUID(current_user["id"]),
            transformation_type=transformation_type,
            include_shared=include_shared,
            skip=skip,
            limit=limit
        )
        
        # Add is_owner flag
        user_id = UUID(current_user["id"])
        preset_responses = [
            TransformationPresetResponse(
                **{k: v for k, v in preset.__dict__.items() if not k.startswith('_')},
                is_owner=(preset.user_id == user_id)
            )
            for preset in presets
        ]
        
        return TransformationPresetList(
            presets=preset_responses,
            total=total,
            skip=skip,
            limit=limit
        )
    except Exception as e:
        logger.error(f"Error listing presets: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list transformation presets"
        )


@router.get(
    "/{preset_id}",
    response_model=TransformationPresetResponse,
    summary="Get a specific preset",
    description="Get details of a specific transformation preset"
)
async def get_preset(
    preset_id: UUID,
    workspace_id: UUID = Depends(get_current_workspace),
    current_user: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Get details of a specific transformation preset"""
    try:
        preset = await transformation_preset_service.get_preset_by_id(
            db=db,
            preset_id=preset_id,
            workspace_id=workspace_id,
            user_id=UUID(current_user["id"])
        )
        
        if not preset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Preset not found"
            )
        
        response = TransformationPresetResponse.from_orm(preset)
        response.is_owner = (preset.user_id == UUID(current_user["id"]))
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting preset {preset_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get transformation preset"
        )


@router.patch(
    "/{preset_id}",
    response_model=TransformationPresetResponse,
    summary="Update a preset",
    description="""
    Update a transformation preset.
    
    Only the preset owner can update it.
    """
)
async def update_preset(
    preset_id: UUID,
    preset_data: TransformationPresetUpdate,
    workspace_id: UUID = Depends(get_current_workspace),
    current_user: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Update a transformation preset"""
    try:
        preset = await transformation_preset_service.update_preset(
            db=db,
            preset_id=preset_id,
            preset_data=preset_data,
            workspace_id=workspace_id,
            user_id=UUID(current_user["id"])
        )
        
        if not preset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Preset not found"
            )
        
        response = TransformationPresetResponse.from_orm(preset)
        response.is_owner = True
        return response
        
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating preset {preset_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update transformation preset"
        )


@router.delete(
    "/{preset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a preset",
    description="""
    Delete a transformation preset (soft delete).
    
    Only the preset owner can delete it.
    """
)
async def delete_preset(
    preset_id: UUID,
    workspace_id: UUID = Depends(get_current_workspace),
    current_user: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Delete a transformation preset"""
    try:
        success = await transformation_preset_service.delete_preset(
            db=db,
            preset_id=preset_id,
            workspace_id=workspace_id,
            user_id=UUID(current_user["id"])
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Preset not found"
            )
        
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting preset {preset_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete transformation preset"
        )


@router.post(
    "/{preset_id}/use",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Record preset usage",
    description="""
    Increment usage count for a preset.
    
    Called automatically when a transformation is created using a preset.
    """
)
async def record_preset_usage(
    preset_id: UUID,
    workspace_id: UUID = Depends(get_current_workspace),
    current_user: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session)
):
    """Increment usage count for a preset"""
    try:
        await transformation_preset_service.increment_usage_count(
            db=db,
            preset_id=preset_id,
            workspace_id=workspace_id
        )
    except Exception as e:
        logger.error(f"Error recording preset usage {preset_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record preset usage"
        )
