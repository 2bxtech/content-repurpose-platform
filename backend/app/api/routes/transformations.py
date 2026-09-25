"""
Production Transformations Router
Fixed to eliminate SQLAlchemy greenlet errors with proper async patterns
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
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
from app.db.models.transformation_preset import TransformationPreset as TransformationPresetDB
from app.db.models.document import DocumentStatus
from app.api.routes.auth import get_current_active_user
from app.api.routes.workspaces import get_current_workspace_context
from app.core.database import get_db_session
from app.core.config import settings
from app.services.transformation_prompt import get_transformation_prompt, CONTENT_REPURPOSE_SYSTEM_PROMPT
from app.services.ai_providers import get_ai_provider_manager
from app.services.transformation_runner import execute_transformation
from app.tasks.transformation_tasks import process_transformation_task
from starlette.concurrency import run_in_threadpool

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
                    DocumentDB.workspace_id == workspace_id,
                    DocumentDB.user_id == user_id,
                    DocumentDB.deleted_at.is_(None),
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

        if settings.TRANSFORMATION_EXECUTION == "inline":
            # Local development without a worker: run in-request.
            await execute_transformation(db, transformation_db, document.extracted_text or "")
        else:
            await _enqueue(db, transformation_db)

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
            task_id=transformation_db.task_id,
            created_at=transformation_db.created_at,
            updated_at=transformation_db.updated_at,
        )

    except HTTPException:
        raise
    except Exception:
        logger.exception("Error creating transformation")
        if db:
            await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create transformation",
        )


async def _enqueue(db: AsyncSession, transformation_db: TransformationDB) -> None:
    """Hand the transformation to a Celery worker; the client polls or listens on
    the WebSocket for completion. Publishing is blocking I/O, so it runs off-loop."""
    try:
        task = await run_in_threadpool(
            process_transformation_task.delay,
            str(transformation_db.id),
            str(transformation_db.workspace_id),
        )
    except Exception:
        logger.exception("Could not enqueue transformation %s", transformation_db.id)
        transformation_db.status = TransformationStatus.FAILED
        transformation_db.error_message = "Background queue unavailable, please retry"
    else:
        transformation_db.task_id = task.id
    transformation_db.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(transformation_db)


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

        # 4. Interactive endpoint: run the AI call in-request (outside the insert transaction)
        transformation_db = await execute_transformation(db, transformation_db, request.content)

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
    except Exception:
        await db.rollback()
        logger.exception("Quick transform failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Quick transform failed",
        )


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

    new_db = await execute_transformation(
        db, new_db, document.extracted_text, prompt=refined_prompt
    )

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


# CORS OPTIONS handlers

