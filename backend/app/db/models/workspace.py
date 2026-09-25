from sqlalchemy import Column, String, Boolean, Text, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from app.core.models import BaseModel, WorkspaceMixin


class Workspace(BaseModel, WorkspaceMixin):
    """Workspace model for multi-tenant support"""

    __tablename__ = "workspaces"

    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False, index=True)
    plan = Column(String(50), default="free", nullable=False)

    # Plan limits and settings
    settings = Column(
        JSONB,
        default={
            "max_users": 10,
            "max_documents": 100,
            "max_storage_mb": 1000,
            "ai_requests_per_month": 1000,
            "features_enabled": ["basic_transformations"],
        },
    )

    description = Column(Text)
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    users = relationship("User", back_populates="workspace", lazy="select")
    documents = relationship("Document", back_populates="workspace", lazy="select")
    transformations = relationship(
        "Transformation", back_populates="workspace", lazy="select"
    )
    transformation_presets = relationship(
        "TransformationPreset", back_populates="workspace", lazy="select"
    )

    # Performance indexes
    __table_args__ = (
        Index(
            "idx_workspace_slug_active",
            "slug",
            postgresql_where=Column("deleted_at").is_(None),
        ),
        WorkspaceMixin.create_active_records_index("workspaces"),
    )
