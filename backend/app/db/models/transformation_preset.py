# backend/app/db/models/transformation_preset.py
"""Transformation preset database model"""

from sqlalchemy import Column, String, Integer, Boolean, Text, ForeignKey, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.core.models import BaseModel


class TransformationPreset(BaseModel):
    """Transformation preset database model for saving reusable configurations"""
    
    __tablename__ = "transformation_presets"
    
    # Foreign Keys (Multi-tenant)
    workspace_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,  # NULL = workspace-shared preset
        index=True
    )
    
    # Preset Configuration
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    transformation_type = Column(String(50), nullable=False, index=True)
    parameters = Column(JSONB, nullable=False, default={}, server_default='{}')
    
    # Sharing & Usage
    is_shared = Column(Boolean, nullable=False, default=False, server_default='false')
    usage_count = Column(Integer, nullable=False, default=0, server_default='0')
    
    # Relationships
    workspace = relationship("Workspace", back_populates="transformation_presets")
    user = relationship("User", back_populates="transformation_presets")
    
    # Constraints and Indexes
    __table_args__ = (
        CheckConstraint(
            transformation_type.in_([
                'BLOG_POST', 'SOCIAL_MEDIA', 'EMAIL_SEQUENCE', 
                'NEWSLETTER', 'SUMMARY', 'CUSTOM'
            ]),
            name='valid_transformation_type'
        ),
        Index(
            'idx_presets_workspace_active',
            'workspace_id',
            postgresql_where=Column('deleted_at').is_(None)
        ),
        Index(
            'idx_presets_user_active',
            'user_id',
            postgresql_where=Column('deleted_at').is_(None)
        ),
        Index(
            'idx_presets_type_active',
            'transformation_type',
            postgresql_where=Column('deleted_at').is_(None)
        ),
        Index(
            'idx_presets_usage',
            'usage_count',
            postgresql_where=Column('deleted_at').is_(None)
        ),
    )
