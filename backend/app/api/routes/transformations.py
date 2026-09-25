"""
Production Transformations Router
Fixed to eliminate SQLAlchemy greenlet errors with proper async patterns
"""

import time
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, update
from sqlalchemy.orm import selectinload
from datetime import datetime
import uuid
import logging

from app.models.transformation import (
    Transformation,
    TransformationCreate,
    QuickTransformRequest,
    TransformationList,
    TransformationStatus,
    TransformationType,
    RefineRequest,
)
from app.db.models.transformation import Transformation as TransformationDB
from app.db.models.document import Document as DocumentDB
from app.db.models.workspace import Workspace
from app.db.models.transformation_preset import TransformationPreset as TransformationPresetDB
from app.db.models.document import DocumentStatus
from app.api.routes.auth import get_current_active_user
from app.api.routes.workspaces import get_current_workspace_context
from app.core.database import get_db_session
from app.services.transformation_prompt import get_transformation_prompt, CONTENT_REPURPOSE_SYSTEM_PROMPT
from app.services.ai_providers import get_ai_provider_manager, AIProviderError
import traceback

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("", response_model=Transformation, status_code=status.HTTP_201_CREATED)
@router.post(
    "/",
    response_model=Transformation,
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False,
)
async def create_transformation(
    transformation: TransformationCreate,
    current_user: dict = Depends(get_current_active_user),
    workspace_context: dict = Depends(get_current_workspace_context),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Create a new content transformation
    Fixed to eliminate greenlet errors with proper async patterns
    """
    try:
        user_id = uuid.UUID(current_user["id"])
        workspace_id = workspace_context["workspace_id"]
        
        logger.info(f"Creating transformation: user_id={user_id}, workspace_id={workspace_id}, document_id={transformation.document_id}")
        
        # Get workspace using explicit async queries (no RLS complexity)
        
        # Verify document exists with eager loading to prevent lazy loading issues
        doc_stmt = (
            select(DocumentDB)
            .where(
                and_(
                    DocumentDB.id == transformation.document_id,
                    DocumentDB.user_id == uuid.UUID(current_user["id"]),  # Explicit UUID conversion
                    DocumentDB.deleted_at.is_(None)
                )
            )
            .options(
                selectinload(DocumentDB.workspace),  # Eager load relationships
                selectinload(DocumentDB.user)
            )
        )
        
        doc_result = await db.execute(doc_stmt)
        document = doc_result.unique().scalar_one_or_none()
        
        logger.info(f"Document lookup result: {document}")
        if document:
            logger.info(f"Found document: id={document.id}, user_id={document.user_id}, workspace_id={getattr(document, 'workspace_id', 'NO_WORKSPACE_ID')}")
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found or access denied"
            )
        
        # Load preset parameters if preset_id provided
        final_parameters = transformation.parameters or {}
        if transformation.preset_id:
            preset_stmt = (
                select(TransformationPresetDB)
                .where(
                    and_(
                        TransformationPresetDB.id == transformation.preset_id,
                        TransformationPresetDB.workspace_id == workspace_id,
                        TransformationPresetDB.deleted_at.is_(None)
                    )
                )
            )
            preset_result = await db.execute(preset_stmt)
            preset = preset_result.scalar_one_or_none()
            
            if not preset:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Preset {transformation.preset_id} not found or access denied"
                )
            
            # Verify preset type matches transformation type
            if preset.transformation_type != transformation.transformation_type:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Preset type {preset.transformation_type} does not match requested type {transformation.transformation_type}"
                )
            
            # Merge parameters: preset base + request overrides
            final_parameters = {**preset.parameters, **final_parameters}
            
            # Increment preset usage count
            preset.usage_count += 1
            db.add(preset)
            
            logger.info(f"Applied preset {preset.id} ({preset.name}) to transformation")
        
        # Create transformation record with PENDING status
        transformation_db = TransformationDB(
            workspace_id=workspace_id,
            user_id=user_id,
            document_id=transformation.document_id,
            transformation_type=transformation.transformation_type,
            parameters=final_parameters,
            status=TransformationStatus.PENDING,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(transformation_db)
        await db.commit()
        await db.refresh(transformation_db)

        # Run AI transformation
        content = (document.extracted_text or "").strip()
        if not content:
            transformation_db.status = TransformationStatus.FAILED
            transformation_db.error_message = "Document has no extractable text content"
            transformation_db.updated_at = datetime.utcnow()
            await db.commit()
            await db.refresh(transformation_db)
        else:
            try:
                t_start = time.time()
                prompt = get_transformation_prompt(
                    transformation.transformation_type, content, final_parameters
                )
                manager = get_ai_provider_manager()
                ai_response = await manager.generate_text(
                    prompt=prompt,
                    system_prompt=CONTENT_REPURPOSE_SYSTEM_PROMPT,
                )
                elapsed = int(time.time() - t_start)

                transformation_db.result = ai_response.content
                transformation_db.status = TransformationStatus.COMPLETED
                transformation_db.ai_provider = ai_response.provider
                transformation_db.tokens_used = ai_response.usage_metrics.total_tokens
                transformation_db.input_tokens = ai_response.usage_metrics.input_tokens
                transformation_db.output_tokens = ai_response.usage_metrics.output_tokens
                transformation_db.ai_cost = ai_response.usage_metrics.total_cost
                transformation_db.processing_time_seconds = elapsed
                transformation_db.updated_at = datetime.utcnow()
                await db.commit()
                await db.refresh(transformation_db)

            except AIProviderError as e:
                logger.error(f"AI provider error for transformation {transformation_db.id}: {e}")
                transformation_db.status = TransformationStatus.FAILED
                transformation_db.error_message = f"AI provider error: {str(e)}"
                transformation_db.updated_at = datetime.utcnow()
                await db.commit()
                await db.refresh(transformation_db)
        
        # Return response model
        return Transformation(
            id=uuid.UUID(str(transformation_db.id)),
            user_id=uuid.UUID(str(transformation_db.user_id)),
            document_id=uuid.UUID(str(transformation_db.document_id)),
            transformation_type=transformation_db.transformation_type,
            parameters=transformation_db.parameters,
            status=transformation_db.status,
            result=transformation_db.result,
            error_message=transformation_db.error_message,
            task_id=None,
            created_at=transformation_db.created_at,
            updated_at=transformation_db.updated_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating transformation: {str(e)}")
        if db:
            await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create transformation: {str(e)}"
        )


async def _create_transformation_in_memory(transformation: TransformationCreate, user_id: uuid.UUID) -> Transformation:
    """Fallback in-memory transformation (no DB). Calls real AI if provider is configured."""
    try:
        content = transformation.parameters.get("_content", "")  # quick transform may stash content
        if content:
            prompt = get_transformation_prompt(
                transformation.transformation_type, content, transformation.parameters
            )
            manager = get_ai_provider_manager()
            ai_response = await manager.generate_text(
                prompt=prompt, system_prompt=CONTENT_REPURPOSE_SYSTEM_PROMPT
            )
            result_text = ai_response.content
        else:
            result_text = f"[No DB mode] Transformation type: {transformation.transformation_type.value}. Provide DATABASE_URL to enable persistence."
    except Exception:
        result_text = f"[No DB mode] Transformation type: {transformation.transformation_type.value}."

    return Transformation(
        id=uuid.uuid4(),
        user_id=user_id,
        document_id=transformation.document_id,
        transformation_type=transformation.transformation_type,
        parameters=transformation.parameters,
        status=TransformationStatus.COMPLETED,
        result=result_text,
        task_id=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

@router.post("/quick", response_model=Transformation, status_code=status.HTTP_201_CREATED)
async def quick_transform(
    request: QuickTransformRequest,
    current_user: dict = Depends(get_current_active_user),
    workspace_context: dict = Depends(get_current_workspace_context),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Single-call quick transform: creates Document + Transformation in one atomic transaction.
    No separate document upload step required.
    """
    user_id = uuid.UUID(current_user["id"])
    workspace_id = workspace_context["workspace_id"]

    # Auto-generate title from first words of content if not provided
    title = request.title or " ".join(request.content.split()[:8]).rstrip(".,;:!?") or "Quick transform"

    try:
        content_bytes = request.content.encode("utf-8")
        word_count = len(request.content.split())

        # 1. Create Document
        document_db = DocumentDB(
            workspace_id=workspace_id,
            user_id=user_id,
            title=title,
            file_path="text_input",
            original_filename=f"{title}.txt",
            content_type="text/plain",
            file_size=len(content_bytes),
            extracted_text=request.content,
            doc_metadata={
                "source": "quick_transform",
                "word_count": word_count,
                "extraction_method": "direct",
            },
            status=DocumentStatus.COMPLETED,
            created_by=user_id,
        )
        db.add(document_db)
        await db.flush()  # get document_db.id without committing

        # 2. Resolve preset parameters
        final_parameters = dict(request.parameters or {})
        if request.preset_id:
            preset_stmt = select(TransformationPresetDB).where(
                and_(
                    TransformationPresetDB.id == request.preset_id,
                    TransformationPresetDB.workspace_id == workspace_id,
                    TransformationPresetDB.deleted_at.is_(None),
                )
            )
            preset_result = await db.execute(preset_stmt)
            preset = preset_result.scalar_one_or_none()
            if preset and preset.transformation_type == request.transformation_type:
                final_parameters = {**preset.parameters, **final_parameters}
                preset.usage_count += 1
                db.add(preset)

        # 3. Create Transformation with PENDING status (AI call happens after commit)
        transformation_db = TransformationDB(
            workspace_id=workspace_id,
            user_id=user_id,
            document_id=document_db.id,
            transformation_type=request.transformation_type,
            parameters=final_parameters,
            status=TransformationStatus.PENDING,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(transformation_db)
        await db.commit()
        await db.refresh(transformation_db)

        # 4. Run AI on the content (outside flush transaction)
        content = request.content.strip()
        try:
            t_start = time.time()
            prompt = get_transformation_prompt(
                request.transformation_type, content, final_parameters
            )
            manager = get_ai_provider_manager()
            ai_response = await manager.generate_text(
                prompt=prompt,
                system_prompt=CONTENT_REPURPOSE_SYSTEM_PROMPT,
            )
            elapsed = int(time.time() - t_start)

            transformation_db.result = ai_response.content
            transformation_db.status = TransformationStatus.COMPLETED
            transformation_db.ai_provider = ai_response.provider
            transformation_db.tokens_used = ai_response.usage_metrics.total_tokens
            transformation_db.input_tokens = ai_response.usage_metrics.input_tokens
            transformation_db.output_tokens = ai_response.usage_metrics.output_tokens
            transformation_db.ai_cost = ai_response.usage_metrics.total_cost
            transformation_db.processing_time_seconds = elapsed
            transformation_db.updated_at = datetime.utcnow()
            await db.commit()
            await db.refresh(transformation_db)

        except AIProviderError as e:
            logger.error(f"Quick transform AI error: {e}")
            transformation_db.status = TransformationStatus.FAILED
            transformation_db.error_message = f"AI provider error: {str(e)}"
            transformation_db.updated_at = datetime.utcnow()
            await db.commit()
            await db.refresh(transformation_db)

        return Transformation(
            id=uuid.UUID(str(transformation_db.id)),
            user_id=uuid.UUID(str(transformation_db.user_id)),
            document_id=uuid.UUID(str(transformation_db.document_id)),
            transformation_type=transformation_db.transformation_type,
            parameters=transformation_db.parameters,
            status=transformation_db.status,
            result=transformation_db.result,
            error_message=transformation_db.error_message,
            task_id=None,
            created_at=transformation_db.created_at,
            updated_at=transformation_db.updated_at,
        )

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Quick transform error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Quick transform failed: {str(e)}",
        )


@router.get("/debug/workspace-test")
async def debug_workspace_test():
    """Debug endpoint to test Workspace model access"""
    try:
        logger.info("Testing Workspace class access...")
        logger.info(f"Workspace: {Workspace}")
        logger.info(f"Workspace.__name__: {Workspace.__name__}")
        logger.info(f"Workspace.__table__.name: {Workspace.__table__.name}")
        logger.info(f"Workspace columns: {[c.name for c in Workspace.__table__.columns]}")
        return {"status": "success", "message": "Workspace model accessible"}
    except Exception as e:
        logger.error(f"Error accessing Workspace: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {"status": "error", "message": str(e)}

@router.get("", response_model=TransformationList)
@router.get("/", response_model=TransformationList, include_in_schema=False)
async def get_user_transformations(
    current_user: dict = Depends(get_current_active_user),
    workspace_context: dict = Depends(get_current_workspace_context),
    db: AsyncSession = Depends(get_db_session),
):
    """Get user transformations with proper eager loading"""
    try:
        user_id = uuid.UUID(current_user["id"])
        workspace_id = workspace_context["workspace_id"]
        
        # Use minimal query without eager loading to isolate the issue
        stmt = (
            select(TransformationDB)
            .where(
                and_(
                    TransformationDB.workspace_id == workspace_id,
                    TransformationDB.user_id == user_id,
                    TransformationDB.deleted_at.is_(None),
                )
            )
            # Remove all eager loading temporarily
            # .options(
            #     selectinload(TransformationDB.document),
            #     # Temporarily remove workspace loading to test
            #     # selectinload(TransformationDB.workspace)
            # )
            .order_by(TransformationDB.created_at.desc())
        )
        
        result = await db.execute(stmt)
        transformations_db = result.unique().scalars().all()
        
        transformations = [
            Transformation(
                id=uuid.UUID(str(t.id)),
                user_id=uuid.UUID(str(t.user_id)),
                document_id=uuid.UUID(str(t.document_id)),
                transformation_type=t.transformation_type,
                parameters=t.parameters,
                status=t.status,
                result=t.result,
                task_id=getattr(t, 'task_id', None),
                created_at=t.created_at,
                updated_at=t.updated_at,
            )
            for t in transformations_db
        ]
        
        return TransformationList(transformations=transformations, count=len(transformations))
        
    except Exception as e:
        logger.error(f"Error retrieving transformations: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve transformations"
        )

@router.get("/{transformation_id}", response_model=Transformation)
async def get_transformation(
    transformation_id: uuid.UUID,
    current_user: dict = Depends(get_current_active_user),
    workspace_context: dict = Depends(get_current_workspace_context),
    db: AsyncSession = Depends(get_db_session),
):
    """Get specific transformation with eager loading"""
    try:
        user_id = uuid.UUID(current_user["id"])
        workspace_id = workspace_context["workspace_id"]
        
        stmt = (
            select(TransformationDB)
            .where(
                and_(
                    TransformationDB.id == transformation_id,
                    TransformationDB.workspace_id == workspace_id,
                    TransformationDB.user_id == user_id,
                    TransformationDB.deleted_at.is_(None),
                )
            )
            .options(
                selectinload(TransformationDB.document),
                selectinload(TransformationDB.workspace)
            )
        )
        
        result = await db.execute(stmt)
        transformation_db = result.unique().scalar_one_or_none()
        
        if not transformation_db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Transformation not found",
            )
        
        return Transformation(
            id=uuid.UUID(str(transformation_db.id)),
            user_id=uuid.UUID(str(transformation_db.user_id)),
            document_id=uuid.UUID(str(transformation_db.document_id)),
            transformation_type=transformation_db.transformation_type,
            parameters=transformation_db.parameters,
            status=transformation_db.status,
            result=transformation_db.result,
            error_message=transformation_db.error_message,
            task_id=getattr(transformation_db, 'task_id', None),
            created_at=transformation_db.created_at,
            updated_at=transformation_db.updated_at,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving transformation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve transformation"
        )

@router.post("/{transformation_id}/refine", response_model=Transformation, status_code=status.HTTP_201_CREATED)
async def refine_transformation(
    transformation_id: uuid.UUID,
    request: RefineRequest,
    current_user: dict = Depends(get_current_active_user),
    workspace_context: dict = Depends(get_current_workspace_context),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Re-run a completed transformation with an additional instruction appended to the original prompt.
    Creates a new Transformation row linked to the same document.
    """
    user_id = uuid.UUID(current_user["id"])
    workspace_id = workspace_context["workspace_id"]

    # Load original transformation (workspace + user scoped)
    stmt = (
        select(TransformationDB)
        .where(
            and_(
                TransformationDB.id == transformation_id,
                TransformationDB.workspace_id == workspace_id,
                TransformationDB.user_id == user_id,
                TransformationDB.deleted_at.is_(None),
            )
        )
    )
    result = await db.execute(stmt)
    original = result.scalar_one_or_none()
    if not original:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transformation not found")

    if original.status != TransformationStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only refine completed transformations",
        )

    # Load document content
    doc_stmt = (
        select(DocumentDB)
        .where(
            and_(
                DocumentDB.id == original.document_id,
                DocumentDB.workspace_id == workspace_id,
                DocumentDB.deleted_at.is_(None),
            )
        )
    )
    doc_result = await db.execute(doc_stmt)
    document = doc_result.scalar_one_or_none()
    if not document or not document.extracted_text:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source document content not found")

    # Build original prompt then append refinement instruction
    base_prompt = get_transformation_prompt(
        original.transformation_type,
        document.extracted_text.strip(),
        original.parameters or {},
    )
    refined_prompt = f"{base_prompt}\n\nAlso: {request.instruction}"

    # Create new transformation row
    new_db = TransformationDB(
        workspace_id=workspace_id,
        user_id=user_id,
        document_id=original.document_id,
        transformation_type=original.transformation_type,
        parameters=original.parameters or {},
        status=TransformationStatus.PENDING,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(new_db)
    await db.commit()
    await db.refresh(new_db)

    try:
        t_start = time.time()
        manager = get_ai_provider_manager()
        ai_response = await manager.generate_text(
            prompt=refined_prompt,
            system_prompt=CONTENT_REPURPOSE_SYSTEM_PROMPT,
        )
        elapsed = int(time.time() - t_start)

        new_db.result = ai_response.content
        new_db.status = TransformationStatus.COMPLETED
        new_db.ai_provider = ai_response.provider
        new_db.tokens_used = ai_response.usage_metrics.total_tokens
        new_db.input_tokens = ai_response.usage_metrics.input_tokens
        new_db.output_tokens = ai_response.usage_metrics.output_tokens
        new_db.ai_cost = ai_response.usage_metrics.total_cost
        new_db.processing_time_seconds = elapsed
        new_db.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(new_db)

    except AIProviderError as e:
        logger.error(f"Refine AI error for {transformation_id}: {e}")
        new_db.status = TransformationStatus.FAILED
        new_db.error_message = f"AI provider error: {str(e)}"
        new_db.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(new_db)

    return Transformation(
        id=uuid.UUID(str(new_db.id)),
        user_id=uuid.UUID(str(new_db.user_id)),
        document_id=uuid.UUID(str(new_db.document_id)),
        transformation_type=new_db.transformation_type,
        parameters=new_db.parameters,
        status=new_db.status,
        result=new_db.result,
        error_message=new_db.error_message,
        task_id=None,
        created_at=new_db.created_at,
        updated_at=new_db.updated_at,
    )


@router.get("/types/available")
async def get_available_transformation_types(
    current_user: dict = Depends(get_current_active_user)
):
    """Get available transformation types"""
    return {
        "transformation_types": [
            {
                "type": TransformationType.SUMMARY.value,
                "description": "Create a concise summary of the document content",
                "parameters": ["length", "style"]
            },
            {
                "type": TransformationType.BLOG_POST.value,
                "description": "Transform content into a blog post format",
                "parameters": ["tone", "target_audience", "word_count"]
            },
            {
                "type": TransformationType.SOCIAL_MEDIA.value,
                "description": "Create social media posts from content",
                "parameters": ["platform", "tone", "hashtags"]
            },
            {
                "type": TransformationType.EMAIL_SEQUENCE.value,
                "description": "Generate email sequence from content",
                "parameters": ["sequence_length", "tone", "call_to_action"]
            },
            {
                "type": TransformationType.NEWSLETTER.value,
                "description": "Format content as newsletter",
                "parameters": ["sections", "tone", "length"]
            },
            {
                "type": TransformationType.CUSTOM.value,
                "description": "Custom transformation with specific instructions",
                "parameters": ["instructions", "format", "tone"]
            }
        ],
        "count": 6
    }

# Debug endpoints (simplified)
@router.get("/debug/user-stats")
async def get_user_transformation_stats(
    current_user: dict = Depends(get_current_active_user),
    workspace_context: dict = Depends(get_current_workspace_context),
    db: AsyncSession = Depends(get_db_session),
):
    """Get transformation stats with proper async queries"""
    try:
        user_id = uuid.UUID(current_user["id"])
        workspace_id = workspace_context["workspace_id"]
        
        # Count by status using explicit async query
        status_stmt = (
            select(
                TransformationDB.status,
                func.count(TransformationDB.id).label('count')
            )
            .where(
                and_(
                    TransformationDB.workspace_id == workspace_id,
                    TransformationDB.user_id == user_id,
                    TransformationDB.deleted_at.is_(None),
                )
            )
            .group_by(TransformationDB.status)
        )
        
        status_result = await db.execute(status_stmt)
        status_counts = {row.status.value: row.count for row in status_result}
        
        return {
            "user_id": str(user_id),
            "workspace_id": str(workspace_id),
            "transformations_by_status": status_counts,
            "mode": "database"
        }
        
    except Exception as e:
        logger.error(f"Error getting transformation stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get transformation statistics"
        )

# CORS OPTIONS handlers
@router.options("/")
@router.options("/{path:path}")
async def handle_cors_options():
    """Handle CORS preflight requests"""
    return {"message": "OK"}
