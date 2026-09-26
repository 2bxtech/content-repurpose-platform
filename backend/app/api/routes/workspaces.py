from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload
import uuid
import logging

from app.models.workspace import (
    WorkspaceCreate,
    WorkspaceUpdate,
    Workspace,
    WorkspaceList,
    WorkspaceMember,
    WorkspaceMemberList,
    WorkspaceUsage,
)
from app.db.models.workspace import Workspace as WorkspaceDB
from app.db.models.user import User as UserDB, UserRole
from app.api.routes.auth import get_current_active_user
from app.core.database import get_db_session
from app.core.tenancy import rls_bypass
from app.services.workspace_service import workspace_service

router = APIRouter()
logger = logging.getLogger(__name__)


async def get_current_workspace_context(
    current_user: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Get current workspace context for the user"""
    # In production, this would get the user's current workspace from session or header
    # For now, we'll get their primary workspace
    user_id = current_user["id"]
    stmt = (
        select(UserDB)
        .where(UserDB.id == user_id)
        .options(selectinload(UserDB.workspace))
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User workspace not found"
        )

    return {
        "workspace_id": user.workspace_id,
        "workspace_slug": user.workspace.slug,
        "user_role": user.role.value,
        "workspace": user.workspace,
    }


@router.get("/workspaces", response_model=WorkspaceList)
async def list_workspaces(
    current_user: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """List all workspaces the current user has access to"""

    user_id = current_user["id"]

    # Get all workspaces where user is a member
    stmt = (
        select(WorkspaceDB, UserDB.role)
        .join(UserDB, WorkspaceDB.id == UserDB.workspace_id)
        .where(
            and_(
                UserDB.id == user_id,
                UserDB.is_active,
                WorkspaceDB.is_active,
                WorkspaceDB.deleted_at.is_(None),
            )
        )
        .order_by(WorkspaceDB.name)
    )

    result = await db.execute(stmt)
    workspace_data = result.all()

    workspaces = []
    for workspace_db, user_role in workspace_data:
        # Get workspace statistics
        stats = await workspace_service.get_workspace_stats(db, workspace_db.id)

        workspace = Workspace(
            id=workspace_db.id,
            name=workspace_db.name,
            slug=workspace_db.slug,
            description=workspace_db.description,
            plan=workspace_db.plan,
            settings=workspace_db.settings,
            is_active=workspace_db.is_active,
            created_at=workspace_db.created_at,
            updated_at=workspace_db.updated_at,
            user_role=user_role,
            user_count=stats.get("user_count", 0),
            document_count=stats.get("document_count", 0),
            storage_used_mb=stats.get("storage_used_mb", 0.0),
        )
        workspaces.append(workspace)

    return WorkspaceList(workspaces=workspaces, count=len(workspaces))


@router.post(
    "/workspaces", response_model=Workspace, status_code=status.HTTP_201_CREATED
)
async def create_workspace(
    workspace_data: WorkspaceCreate,
    current_user: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Create a new workspace"""
    # Creating a tenant spans tenants: slugs are global, and the new workspace and
    # the user moving into it are outside the caller's current workspace.
    async with rls_bypass(db):
        # Check if slug is already taken
        stmt = select(WorkspaceDB).where(
            and_(WorkspaceDB.slug == workspace_data.slug, WorkspaceDB.deleted_at.is_(None))
        )
        result = await db.execute(stmt)
        existing_workspace = result.scalar_one_or_none()

        if existing_workspace:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Workspace slug '{workspace_data.slug}' is already taken",
            )

        # Create workspace
        workspace = WorkspaceDB(
            name=workspace_data.name,
            slug=workspace_data.slug,
            description=workspace_data.description,
            plan=workspace_data.plan.value,
            settings={
                "max_users": 10,
                "max_documents": 100,
                "max_storage_mb": 1000,
                "ai_requests_per_month": 1000,
                "features_enabled": ["basic_transformations"],
            },
            is_active=True,
            created_by=current_user["id"],
        )

        db.add(workspace)
        await db.flush()  # Get the workspace ID

        # Add current user as workspace owner
        user_id = current_user["id"]
        stmt = select(UserDB).where(UserDB.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if user:
            # Update user's workspace and role
            user.workspace_id = workspace.id
            user.role = UserRole.OWNER

        await db.commit()
        await db.refresh(workspace)

    logger.info(f"Workspace created: {workspace.slug} by user {current_user['email']}")

    return Workspace(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        description=workspace.description,
        plan=workspace.plan,
        settings=workspace.settings,
        is_active=workspace.is_active,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
        user_role="owner",
        user_count=1,
        document_count=0,
        storage_used_mb=0.0,
    )


@router.get("/workspaces/{workspace_id}", response_model=Workspace)
async def get_workspace(
    workspace_id: uuid.UUID,
    workspace_context: dict = Depends(get_current_workspace_context),
    db: AsyncSession = Depends(get_db_session),
):
    """Get workspace details"""

    # Verify user has access to this workspace
    if workspace_context["workspace_id"] != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this workspace",
        )

    stmt = select(WorkspaceDB).where(
        and_(WorkspaceDB.id == workspace_id, WorkspaceDB.deleted_at.is_(None))
    )
    result = await db.execute(stmt)
    workspace = result.scalar_one_or_none()

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )

    # Get workspace statistics
    stats = await workspace_service.get_workspace_stats(db, workspace_id)

    return Workspace(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        description=workspace.description,
        plan=workspace.plan,
        settings=workspace.settings,
        is_active=workspace.is_active,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
        user_role=workspace_context["user_role"],
        user_count=stats.get("user_count", 0),
        document_count=stats.get("document_count", 0),
        storage_used_mb=stats.get("storage_used_mb", 0.0),
    )


@router.put("/workspaces/{workspace_id}", response_model=Workspace)
async def update_workspace(
    workspace_id: uuid.UUID,
    workspace_data: WorkspaceUpdate,
    workspace_context: dict = Depends(get_current_workspace_context),
    db: AsyncSession = Depends(get_db_session),
):
    """Update workspace details (admin/owner only)"""

    # Verify user has access and appropriate role
    if workspace_context["workspace_id"] != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this workspace",
        )

    if workspace_context["user_role"] not in ["owner", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only workspace owners and admins can update workspace settings",
        )

    stmt = select(WorkspaceDB).where(
        and_(WorkspaceDB.id == workspace_id, WorkspaceDB.deleted_at.is_(None))
    )
    result = await db.execute(stmt)
    workspace = result.scalar_one_or_none()

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )

    # Update fields
    update_data = workspace_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(workspace, field):
            setattr(workspace, field, value)

    await db.commit()
    await db.refresh(workspace)

    logger.info(f"Workspace updated: {workspace.slug}")

    # Get updated statistics
    stats = await workspace_service.get_workspace_stats(db, workspace_id)

    return Workspace(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        description=workspace.description,
        plan=workspace.plan,
        settings=workspace.settings,
        is_active=workspace.is_active,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
        user_role=workspace_context["user_role"],
        user_count=stats.get("user_count", 0),
        document_count=stats.get("document_count", 0),
        storage_used_mb=stats.get("storage_used_mb", 0.0),
    )


@router.post("/workspaces/{workspace_id}/switch")
async def switch_workspace(
    workspace_id: uuid.UUID,
    current_user: dict = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db_session),
):
    """Switch to a different workspace"""

    user_id = current_user["id"]

    # Verify user has access to the target workspace
    stmt = (
        select(UserDB)
        .where(
            and_(
                UserDB.id == user_id,
                UserDB.workspace_id == workspace_id,
                UserDB.is_active,
            )
        )
        .options(selectinload(UserDB.workspace))
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found or access denied",
        )

    # In a full implementation, this would update the user's session
    # For now, we'll return success
    logger.info(
        f"User {current_user['email']} switched to workspace {user.workspace.slug}"
    )

    return {
        "message": "Workspace switched successfully",
        "workspace_id": workspace_id,
        "workspace_slug": user.workspace.slug,
    }


@router.get("/workspaces/{workspace_id}/members", response_model=WorkspaceMemberList)
async def get_workspace_members(
    workspace_id: uuid.UUID,
    workspace_context: dict = Depends(get_current_workspace_context),
    db: AsyncSession = Depends(get_db_session),
):
    """Get workspace members"""

    # Verify user has access to this workspace
    if workspace_context["workspace_id"] != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this workspace",
        )

    stmt = (
        select(UserDB)
        .where(and_(UserDB.workspace_id == workspace_id, UserDB.deleted_at.is_(None)))
        .order_by(UserDB.role, UserDB.username)
    )
    result = await db.execute(stmt)
    users = result.scalars().all()

    members = []
    for user in users:
        member = WorkspaceMember(
            id=user.id,
            email=user.email,
            username=user.username,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
            last_login=getattr(user, "last_login", None),
        )
        members.append(member)

    return WorkspaceMemberList(members=members, count=len(members))


@router.get("/workspaces/{workspace_id}/usage", response_model=WorkspaceUsage)
async def get_workspace_usage(
    workspace_id: uuid.UUID,
    workspace_context: dict = Depends(get_current_workspace_context),
    db: AsyncSession = Depends(get_db_session),
):
    """Get workspace usage statistics"""

    # Verify user has access to this workspace
    if workspace_context["workspace_id"] != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this workspace",
        )

    workspace = workspace_context.get("workspace")
    if not workspace:
        stmt = select(WorkspaceDB).where(WorkspaceDB.id == workspace_id)
        result = await db.execute(stmt)
        workspace = result.scalar_one_or_none()

    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found"
        )

    # Get current usage
    usage_stats = await workspace_service.get_workspace_usage(db, workspace_id)

    return WorkspaceUsage(
        workspace_id=workspace_id,
        plan=workspace.plan,
        settings=workspace.settings,
        current_usage=usage_stats["current_usage"],
        limits=usage_stats["limits"],
        usage_percentage=usage_stats["usage_percentage"],
    )
