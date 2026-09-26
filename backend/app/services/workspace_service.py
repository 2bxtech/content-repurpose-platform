from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Dict, Any, Optional
import uuid
from datetime import datetime, timedelta
import logging

from app.db.models.workspace import Workspace
from app.db.models.user import User
from app.db.models.document import Document
from app.db.models.transformation import Transformation

logger = logging.getLogger(__name__)


class WorkspaceService:
    """Service for workspace-related operations"""

    async def get_workspace_stats(
        self, db: AsyncSession, workspace_id: uuid.UUID
    ) -> Dict[str, Any]:
        """Get basic workspace statistics"""


        # Count users
        user_count_stmt = select(func.count(User.id)).where(
            and_(
                User.workspace_id == workspace_id,
                User.is_active,
                User.deleted_at.is_(None),
            )
        )
        user_count_result = await db.execute(user_count_stmt)
        user_count = user_count_result.scalar() or 0

        # Count documents
        doc_count_stmt = select(func.count(Document.id)).where(
            and_(
                Document.workspace_id == workspace_id, Document.deleted_at.is_(None)
            )
        )
        doc_count_result = await db.execute(doc_count_stmt)
        document_count = doc_count_result.scalar() or 0

        # Calculate storage used (sum of file sizes)
        storage_stmt = select(func.coalesce(func.sum(Document.file_size), 0)).where(
            and_(
                Document.workspace_id == workspace_id, Document.deleted_at.is_(None)
            )
        )
        storage_result = await db.execute(storage_stmt)
        storage_bytes = storage_result.scalar() or 0
        storage_mb = storage_bytes / (1024 * 1024)  # Convert to MB

        # Count transformations
        transform_count_stmt = select(func.count(Transformation.id)).where(
            and_(
                Transformation.workspace_id == workspace_id,
                Transformation.deleted_at.is_(None),
            )
        )
        transform_count_result = await db.execute(transform_count_stmt)
        transformation_count = transform_count_result.scalar() or 0

        return {
            "user_count": user_count,
            "document_count": document_count,
            "storage_used_mb": round(storage_mb, 2),
            "transformation_count": transformation_count,
        }


    async def get_workspace_usage(
        self, db: AsyncSession, workspace_id: uuid.UUID
    ) -> Dict[str, Any]:
        """Get detailed workspace usage against plan limits"""

        # Get workspace to check plan limits
        stmt = select(Workspace).where(Workspace.id == workspace_id)
        result = await db.execute(stmt)
        workspace = result.scalar_one_or_none()

        if not workspace:
            raise ValueError(f"Workspace {workspace_id} not found")

        # Get current stats
        stats = await self.get_workspace_stats(db, workspace_id)

        # Get monthly AI requests (current month)
        current_month = datetime.now().replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )


        monthly_requests_stmt = select(func.count(Transformation.id)).where(
            and_(
                Transformation.workspace_id == workspace_id,
                Transformation.created_at >= current_month,
                Transformation.deleted_at.is_(None),
            )
        )
        monthly_requests_result = await db.execute(monthly_requests_stmt)
        monthly_ai_requests = monthly_requests_result.scalar() or 0


        # Extract limits from workspace settings
        settings = workspace.settings or {}
        limits = {
            "max_users": settings.get("max_users", 10),
            "max_documents": settings.get("max_documents", 100),
            "max_storage_mb": settings.get("max_storage_mb", 1000),
            "ai_requests_per_month": settings.get("ai_requests_per_month", 1000),
        }

        # Current usage
        current_usage = {
            "users": stats["user_count"],
            "documents": stats["document_count"],
            "storage_mb": stats["storage_used_mb"],
            "ai_requests_this_month": monthly_ai_requests,
        }

        # Calculate usage percentages
        usage_percentage = {}
        for key in ["users", "documents", "storage_mb", "ai_requests_this_month"]:
            limit_key = (
                f"max_{key}"
                if key != "ai_requests_this_month"
                else "ai_requests_per_month"
            )
            if limits.get(limit_key, 0) > 0:
                usage_percentage[key] = min(
                    100, (current_usage[key] / limits[limit_key]) * 100
                )
            else:
                usage_percentage[key] = 0

        return {
            "current_usage": current_usage,
            "limits": limits,
            "usage_percentage": usage_percentage,
        }

    async def get_workspace_activity(
        self, db: AsyncSession, workspace_id: uuid.UUID, days: int = 7
    ) -> Dict[str, Any]:
        """Get workspace activity for the last N days"""

        start_date = datetime.now() - timedelta(days=days)


        # Documents created in the last N days
        docs_created_stmt = select(func.count(Document.id)).where(
            and_(
                Document.workspace_id == workspace_id,
                Document.created_at >= start_date,
                Document.deleted_at.is_(None),
            )
        )
        docs_created_result = await db.execute(docs_created_stmt)
        docs_created = docs_created_result.scalar() or 0

        # Transformations created in the last N days
        transforms_created_stmt = select(func.count(Transformation.id)).where(
            and_(
                Transformation.workspace_id == workspace_id,
                Transformation.created_at >= start_date,
                Transformation.deleted_at.is_(None),
            )
        )
        transforms_created_result = await db.execute(transforms_created_stmt)
        transforms_created = transforms_created_result.scalar() or 0

        # Active users (users who performed any action in the last N days)
        # This is simplified - in production you'd track user activity
        active_users_stmt = select(func.count(func.distinct(User.id))).where(
            and_(
                User.workspace_id == workspace_id,
                User.is_active,
                User.deleted_at.is_(None),
            )
        )
        active_users_result = await db.execute(active_users_stmt)
        active_users = active_users_result.scalar() or 0

        return {
            f"documents_created_last_{days}_days": docs_created,
            f"transformations_created_last_{days}_days": transforms_created,
            f"active_users_last_{days}_days": active_users,
        }


    async def check_workspace_limits(
        self,
        db: AsyncSession,
        workspace_id: uuid.UUID,
        action: str,
        current_count: Optional[int] = None,
    ) -> tuple[bool, Optional[str]]:
        """Check if workspace can perform an action based on plan limits"""

        # Get workspace
        stmt = select(Workspace).where(Workspace.id == workspace_id)
        result = await db.execute(stmt)
        workspace = result.scalar_one_or_none()

        if not workspace:
            return False, "Workspace not found"

        settings = workspace.settings or {}

        if action == "create_document":
            max_docs = settings.get("max_documents", 100)
            if current_count is None:
                stats = await self.get_workspace_stats(db, workspace_id)
                current_count = stats["document_count"]

            if current_count >= max_docs:
                return (
                    False,
                    f"Document limit reached ({max_docs}). Upgrade your plan to create more documents.",
                )

        elif action == "invite_user":
            max_users = settings.get("max_users", 10)
            if current_count is None:
                stats = await self.get_workspace_stats(db, workspace_id)
                current_count = stats["user_count"]

            if current_count >= max_users:
                return (
                    False,
                    f"User limit reached ({max_users}). Upgrade your plan to invite more users.",
                )

        elif action == "ai_transform":
            usage = await self.get_workspace_usage(db, workspace_id)
            current_requests = usage["current_usage"]["ai_requests_this_month"]
            max_requests = usage["limits"]["ai_requests_per_month"]

            if current_requests >= max_requests:
                return (
                    False,
                    f"Monthly AI request limit reached ({max_requests}). Upgrade your plan or wait for next month.",
                )

        return True, None

    async def create_default_workspace(
        self, db: AsyncSession, user_id: Optional[uuid.UUID]
    ) -> Workspace:
        """Create a default workspace for a new user"""

        # Generate unique slug
        if user_id:
            base_slug = f"user-{str(user_id)[:8]}"
        else:
            # Use a random UUID if user_id is not available yet
            base_slug = f"workspace-{str(uuid.uuid4())[:8]}"
            
        slug = base_slug
        counter = 1

        while True:
            stmt = select(Workspace).where(
                and_(Workspace.slug == slug, Workspace.deleted_at.is_(None))
            )
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()

            if not existing:
                break

            slug = f"{base_slug}-{counter}"
            counter += 1

        # Create workspace
        workspace = Workspace(
            name="My Workspace",
            slug=slug,
            plan="free",
            settings={
                "max_users": 10,
                "max_documents": 100,
                "max_storage_mb": 1000,
                "ai_requests_per_month": 1000,
                "features_enabled": ["basic_transformations"],
            },
            description="Your personal workspace",
            is_active=True,
            created_by=user_id,  # Can be None initially, will be updated later
        )

        db.add(workspace)
        await db.flush()

        logger.info(f"Created default workspace: {slug} for user {user_id}")

        return workspace


# Global service instance
workspace_service = WorkspaceService()
