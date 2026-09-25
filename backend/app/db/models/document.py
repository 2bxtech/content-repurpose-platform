from sqlalchemy import Column, String, Text, Integer, ForeignKey, Enum as SQLEnum, Index
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.models import BaseModel, WorkspaceMixin
from enum import Enum


class DocumentStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Document(BaseModel, WorkspaceMixin):
    """Enhanced Document model with content extraction"""

    __tablename__ = "documents"

    # Multi-tenant support (RLS ready)
    workspace_id = Column(
        UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Document metadata
    title = Column(String(255), nullable=False)
    description = Column(Text)
    file_path = Column(String(500), nullable=False)
    original_filename = Column(String(255), nullable=False)
    content_type = Column(String(100))
    file_size = Column(Integer)

    # Content extraction (Enhanced in Phase 1)
    extracted_text = Column(Text)
    doc_metadata = Column(JSONB, default={})

    # Status tracking
    status = Column(SQLEnum(DocumentStatus), default=DocumentStatus.PENDING)
    version = Column(Integer, default=1)

    # Relationships
    workspace = relationship("Workspace", back_populates="documents")
    user = relationship("User", back_populates="documents")
    transformations = relationship(
        "Transformation", back_populates="document", lazy="select"
    )

    # Performance indexes
    __table_args__ = (
        Index(
            "idx_documents_workspace_user_created",
            "workspace_id",
            "user_id",
            "created_at",
        ),
        Index("idx_documents_status", "status"),
        WorkspaceMixin.create_workspace_index("documents"),
    )
