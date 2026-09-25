from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
import uuid


class WorkspacePlan(str, Enum):
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class WorkspaceRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class WorkspaceSettings(BaseModel):
    max_users: int = 10
    max_documents: int = 100
    max_storage_mb: int = 1000
    ai_requests_per_month: int = 1000
    features_enabled: List[str] = ["basic_transformations"]


class WorkspaceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class WorkspaceCreate(WorkspaceBase):
    slug: str = Field(..., min_length=1, max_length=100)
    plan: WorkspacePlan = WorkspacePlan.FREE

    @validator("slug")
    def validate_slug(cls, v):
        # Ensure slug is URL-safe
        import re

        if not re.match(r"^[a-z0-9-]+$", v):
            raise ValueError(
                "Slug must contain only lowercase letters, numbers, and hyphens"
            )
        if v.startswith("-") or v.endswith("-"):
            raise ValueError("Slug cannot start or end with a hyphen")
        return v


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    plan: Optional[WorkspacePlan] = None
    settings: Optional[WorkspaceSettings] = None
    is_active: Optional[bool] = None


class Workspace(WorkspaceBase):
    id: uuid.UUID
    slug: str
    plan: WorkspacePlan
    settings: WorkspaceSettings
    is_active: bool = True
    created_at: datetime
    updated_at: datetime

    # User's role in this workspace
    user_role: Optional[WorkspaceRole] = None

    # Statistics
    user_count: Optional[int] = None
    document_count: Optional[int] = None
    storage_used_mb: Optional[float] = None

    class Config:
        from_attributes = True


class WorkspaceList(BaseModel):
    workspaces: List[Workspace]
    count: int


class WorkspaceMember(BaseModel):
    id: uuid.UUID
    email: str
    username: str
    role: WorkspaceRole
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None


class WorkspaceMemberList(BaseModel):
    members: List[WorkspaceMember]
    count: int


class WorkspaceInvite(BaseModel):
    email: str = Field(..., pattern=r"^[^@]+@[^@]+\.[^@]+$")
    role: WorkspaceRole = WorkspaceRole.MEMBER
    message: Optional[str] = None


class WorkspaceInviteResponse(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    email: str
    role: WorkspaceRole
    invited_by: uuid.UUID
    message: Optional[str] = None
    token: str  # For accepting invitation
    expires_at: datetime
    created_at: datetime


class WorkspaceSwitch(BaseModel):
    workspace_id: uuid.UUID


class WorkspaceUsage(BaseModel):
    workspace_id: uuid.UUID
    plan: WorkspacePlan
    settings: WorkspaceSettings
    current_usage: Dict[str, Any] = {
        "users": 0,
        "documents": 0,
        "storage_mb": 0,
        "ai_requests_this_month": 0,
    }
    limits: Dict[str, Any] = {}
    usage_percentage: Dict[str, float] = {}


class WorkspaceStats(BaseModel):
    workspace_id: uuid.UUID
    total_documents: int
    total_transformations: int
    active_users: int
    storage_used_mb: float
    ai_requests_this_month: int
    created_this_week: Dict[str, int] = {"documents": 0, "transformations": 0}
