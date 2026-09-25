# backend/app/models/transformation_preset.py
"""Transformation preset Pydantic models for API validation"""

from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from enum import Enum


class TransformationType(str, Enum):
    """Transformation type enumeration"""
    BLOG_POST = "BLOG_POST"
    SOCIAL_MEDIA = "SOCIAL_MEDIA"
    EMAIL_SEQUENCE = "EMAIL_SEQUENCE"
    NEWSLETTER = "NEWSLETTER"
    SUMMARY = "SUMMARY"
    CUSTOM = "CUSTOM"


class TransformationPresetCreate(BaseModel):
    """Request model for creating a preset"""
    name: str = Field(..., min_length=1, max_length=255, description="Preset name")
    description: Optional[str] = Field(None, max_length=1000, description="Optional description")
    transformation_type: TransformationType = Field(..., description="Transformation type")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Transformation parameters")
    is_shared: bool = Field(default=False, description="Share with workspace")
    
    @validator('name')
    def validate_name(cls, v):
        """Validate preset name"""
        if not v or not v.strip():
            raise ValueError("Preset name cannot be empty")
        return v.strip()
    
    @validator('parameters')
    def validate_parameters(cls, v, values):
        """Validate parameters are a dictionary"""
        if not isinstance(v, dict):
            raise ValueError("Parameters must be a dictionary")
        return v


class TransformationPresetUpdate(BaseModel):
    """Request model for updating a preset"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=1000)
    parameters: Optional[Dict[str, Any]] = None
    is_shared: Optional[bool] = None
    
    @validator('name')
    def validate_name(cls, v):
        """Validate preset name if provided"""
        if v is not None and (not v or not v.strip()):
            raise ValueError("Preset name cannot be empty")
        return v.strip() if v else v


class TransformationPresetResponse(BaseModel):
    """Response model for preset"""
    id: UUID
    workspace_id: UUID
    user_id: Optional[UUID]
    name: str
    description: Optional[str]
    transformation_type: TransformationType
    parameters: Dict[str, Any]
    is_shared: bool
    usage_count: int
    created_at: datetime
    updated_at: datetime
    
    # Computed fields
    is_owner: bool = Field(default=False, description="Current user owns this preset")
    
    class Config:
        from_attributes = True


class TransformationPresetList(BaseModel):
    """Response model for list of presets"""
    presets: list[TransformationPresetResponse]
    total: int
    skip: int
    limit: int
