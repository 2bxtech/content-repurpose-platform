"""
Transformation models for Content Repurpose API
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
import uuid


class TransformationType(str, Enum):
    """Transformation type enumeration"""
    BLOG_POST = "BLOG_POST"
    SOCIAL_MEDIA = "SOCIAL_MEDIA"
    EMAIL_SEQUENCE = "EMAIL_SEQUENCE"
    NEWSLETTER = "NEWSLETTER"
    SUMMARY = "SUMMARY"
    CUSTOM = "CUSTOM"


class TransformationStatus(str, Enum):
    """Transformation status enumeration"""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TransformationParametersBase(BaseModel):
    """Base transformation parameters"""
    pass


class SummaryParameters(TransformationParametersBase):
    length: str = Field(default="medium", description="Summary length: short, medium, long")
    style: str = Field(default="bullet_points", description="Summary style: paragraph, bullet_points, outline")


class BlogPostParameters(TransformationParametersBase):
    tone: str = Field(default="professional", description="Writing tone")
    target_audience: str = Field(default="general", description="Target audience")
    word_count: int = Field(default=800, gt=0, description="Target word count")


class SocialMediaParameters(TransformationParametersBase):
    platform: str = Field(default="linkedin", description="Social media platform")
    tone: str = Field(default="engaging", description="Post tone")
    hashtags: bool = Field(default=True, description="Include hashtags")


class EmailSequenceParameters(TransformationParametersBase):
    sequence_length: int = Field(default=3, ge=1, le=10, description="Number of emails")
    tone: str = Field(default="professional", description="Email tone")
    call_to_action: str = Field(default="", description="Call to action")


class NewsletterParameters(TransformationParametersBase):
    sections: List[str] = Field(default=["intro", "main_content", "conclusion"], description="Newsletter sections")
    tone: str = Field(default="informative", description="Newsletter tone")
    length: str = Field(default="medium", description="Newsletter length")


class CustomParameters(TransformationParametersBase):
    instructions: str = Field(..., description="Custom transformation instructions")
    format: str = Field(default="text", description="Output format")
    tone: str = Field(default="neutral", description="Writing tone")


class TransformationCreate(BaseModel):
    document_id: uuid.UUID
    transformation_type: TransformationType
    parameters: Dict[str, Any] = Field(default={}, description="Transformation parameters")
    preset_id: Optional[uuid.UUID] = Field(None, description="Optional preset ID to load parameters from")


class QuickTransformRequest(BaseModel):
    """Single-call: create document + transformation in one transaction."""
    content: str = Field(..., min_length=20, description="Text content to transform")
    transformation_type: TransformationType
    title: Optional[str] = Field(None, max_length=255, description="Document title — auto-generated if omitted")
    parameters: Dict[str, Any] = Field(default={}, description="Transformation parameters")
    preset_id: Optional[uuid.UUID] = Field(None, description="Preset to apply")


class Transformation(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    document_id: uuid.UUID
    transformation_type: TransformationType
    parameters: Dict[str, Any]
    status: TransformationStatus
    result: Optional[str] = None
    error_message: Optional[str] = None
    task_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TransformationList(BaseModel):
    transformations: List[Transformation]
    count: int


class RefineRequest(BaseModel):
    """Body for POST /transformations/{id}/refine"""
    instruction: str = Field(..., min_length=1, max_length=2000, description="Instruction to append to the original prompt")