from sqlalchemy import Column, String, Boolean, ForeignKey, Enum as SQLEnum, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.models import BaseModel
from enum import Enum


class UserRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class User(BaseModel):
    """Enhanced User model with multi-tenant support"""

    __tablename__ = "users"

    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)

    # Multi-tenant support
    workspace_id = Column(
        UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=True
    )
    role = Column(SQLEnum(UserRole), default=UserRole.MEMBER, nullable=False)

    # Relationships
    workspace = relationship("Workspace", back_populates="users")
    documents = relationship("Document", back_populates="user", lazy="select")
    transformations = relationship(
        "Transformation", back_populates="user", lazy="select"
    )
    transformation_presets = relationship(
        "TransformationPreset", back_populates="user", lazy="select"
    )

    # Performance indexes
    __table_args__ = (
        Index(
            "idx_users_workspace_active",
            "workspace_id",
            postgresql_where=Column("is_active").is_(True),
        ),
        Index(
            "idx_users_email_active",
            "email",
            postgresql_where=Column("deleted_at").is_(None),
        ),
    )
