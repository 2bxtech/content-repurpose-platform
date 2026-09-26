import logging
import os
import ipaddress
import socket
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status, Body
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Optional
from datetime import datetime
from urllib.parse import urlparse
import uuid
import httpx

from app.models.documents import Document, DocumentList, DocumentStatus
from app.db.models.document import Document as DocumentDB
from app.api.routes.auth import get_current_active_user
from app.api.routes.workspaces import get_current_workspace_context
from app.core.database import get_db_session
from app.core.config import settings
from app.services.workspace_service import workspace_service
from app.services.file_processor import file_processor  # Enhanced file processor

# Mock database for documents - will be replaced when DB is connected
DOCUMENTS_DB = []
document_id_counter = 1

router = APIRouter()
logger = logging.getLogger(__name__)


def validate_file_extension(filename: str) -> bool:
    """Enhanced file extension validation"""
    return file_processor.validate_file_type(
        "application/octet-stream", filename
    )  # Basic check


@router.post(
    "/documents/upload", response_model=Document, status_code=status.HTTP_201_CREATED
)
async def upload_document(
    title: str = Form(...),
    description: Optional[str] = Form(None),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_active_user),
    workspace_context: dict = Depends(get_current_workspace_context),
    db: AsyncSession = Depends(get_db_session),
):
    global document_id_counter

    # Enhanced file validation using new file processor
    if not file_processor.validate_file_type(file.content_type, file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. File: {file.filename}, MIME: {file.content_type}",
        )

    # Read file content for processing
    content = await file.read()
    await file.seek(0)  # Reset file pointer to beginning

    # Validate file size
    file_size = len(content)
    if file_size > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Size: {file_size / (1024 * 1024):.1f}MB, Maximum: {settings.MAX_UPLOAD_SIZE / (1024 * 1024):.1f}MB",
        )

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file not allowed"
        )

    workspace_id = workspace_context["workspace_id"]

    # Check workspace limits (if using database)
    if db:
        can_create, error_msg = await workspace_service.check_workspace_limits(
            db, workspace_id, "create_document"
        )
        if not can_create:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg
            )


    # Create upload directory if it doesn't exist
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    # Generate a unique filename
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_filename = f"{current_user['id']}_{timestamp}_{file.filename}"
    file_path = os.path.join(settings.UPLOAD_DIR, unique_filename)

    # Save the file
    with open(file_path, "wb") as buffer:
        buffer.write(content)

    try:
        # Enhanced file processing with security validation and content extraction
        processing_result = await file_processor.process_file(
            file_path=file_path,
            content_type=file.content_type,
            original_filename=file.filename,
        )

        if not processing_result.security_scan_passed:
            # Clean up file if security scan failed
            if os.path.exists(file_path):
                os.remove(file_path)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File failed security validation",
            )

    except HTTPException:
        raise  # our own 400 above; don't let the catch-all turn it into a 500
    except ValueError as e:
        # Clean up file if processing failed
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File processing failed: {str(e)}",
        )
    except Exception:
        logger.exception("Unexpected error processing upload %s", file.filename)
        if os.path.exists(file_path):
            os.remove(file_path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error during file processing",
        )

    if db:
        try:
            # Create document record in database with enhanced metadata
            document_db = DocumentDB(
                workspace_id=workspace_id,
                user_id=current_user["id"],
                title=title,
                description=description,
                file_path=file_path,
                original_filename=file.filename,
                content_type=file.content_type,
                file_size=file_size,
                # Enhanced Phase 6 fields
                extracted_text=processing_result.content,
                doc_metadata={
                    **processing_result.metadata,
                    "file_hash": processing_result.file_hash,
                    "preview_path": processing_result.preview_path,
                    "content_encoding": processing_result.content_encoding,
                    "word_count": processing_result.word_count,
                    "extraction_method": processing_result.extraction_method,
                },
                status=DocumentStatus.COMPLETED,  # Mark as completed since processing succeeded
                created_by=current_user["id"],
            )

            db.add(document_db)
            await db.commit()
            await db.refresh(document_db)

            return Document(
                id=document_db.id,
                user_id=document_db.user_id,
                title=document_db.title,
                description=document_db.description,
                file_path=document_db.file_path,
                original_filename=document_db.original_filename,
                content_type=document_db.content_type,
                status=document_db.status,
                created_at=document_db.created_at,
                updated_at=document_db.updated_at,
            )

        except Exception as e:
            # Clean up file if database operation fails
            if os.path.exists(file_path):
                os.remove(file_path)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create document record: {str(e)}",
            )

    else:
        # Fallback to in-memory storage with proper UUID
        document_uuid = uuid.uuid4()
        document = {
            "id": str(document_uuid),  # Use UUID string instead of integer
            "user_id": current_user["id"],
            "title": title,
            "description": description,
            "file_path": file_path,
            "original_filename": file.filename,
            "content_type": file.content_type,
            "status": DocumentStatus.COMPLETED,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            # Enhanced metadata from processing
            "extracted_text": processing_result.content,
            "metadata": processing_result.metadata,
            "file_hash": processing_result.file_hash,
            "preview_path": processing_result.preview_path,
        }

        DOCUMENTS_DB.append(document)
        
        # Return proper Document model with UUID
        return Document(
            id=document_uuid,
            user_id=uuid.UUID(current_user["id"]),
            title=title,
            description=description,
            file_path=file_path,
            original_filename=file.filename,
            content_type=file.content_type,
            status=DocumentStatus.COMPLETED,
            created_at=document["created_at"],
            updated_at=document["updated_at"],
        )


@router.post(
    "/documents/text", response_model=Document, status_code=status.HTTP_201_CREATED
)
async def create_document_from_text(
    title: str = Form(...),
    content: str = Form(...),
    description: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_active_user),
    workspace_context: dict = Depends(get_current_workspace_context),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Create a document directly from pasted text — no file upload required.
    Stores content in extracted_text; file_path is set to a sentinel value.
    """
    if not content or not content.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content cannot be empty",
        )

    workspace_id = workspace_context["workspace_id"]
    content_bytes = content.encode("utf-8")
    word_count = len(content.split())

    if db:
        can_create, error_msg = await workspace_service.check_workspace_limits(
            db, workspace_id, "create_document"
        )
        if not can_create:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=error_msg
            )

        try:
            document_db = DocumentDB(
                workspace_id=workspace_id,
                user_id=current_user["id"],
                title=title,
                description=description,
                file_path="text_input",          # sentinel — no file on disk
                original_filename=f"{title}.txt",
                content_type="text/plain",
                file_size=len(content_bytes),
                extracted_text=content,
                doc_metadata={
                    "source": "text_input",
                    "word_count": word_count,
                    "extraction_method": "direct",
                },
                status=DocumentStatus.COMPLETED,
                created_by=current_user["id"],
            )

            db.add(document_db)
            await db.commit()
            await db.refresh(document_db)

            return Document(
                id=document_db.id,
                user_id=document_db.user_id,
                title=document_db.title,
                description=document_db.description,
                file_path=document_db.file_path,
                original_filename=document_db.original_filename,
                content_type=document_db.content_type,
                status=document_db.status,
                created_at=document_db.created_at,
                updated_at=document_db.updated_at,
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create document: {str(e)}",
            )

    else:
        document_uuid = uuid.uuid4()
        doc = {
            "id": str(document_uuid),
            "user_id": current_user["id"],
            "title": title,
            "description": description,
            "file_path": "text_input",
            "original_filename": f"{title}.txt",
            "content_type": "text/plain",
            "status": DocumentStatus.COMPLETED,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "extracted_text": content,
        }
        DOCUMENTS_DB.append(doc)
        return Document(
            id=document_uuid,
            user_id=uuid.UUID(current_user["id"]),
            title=title,
            description=description,
            file_path="text_input",
            original_filename=f"{title}.txt",
            content_type="text/plain",
            status=DocumentStatus.COMPLETED,
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )


def _validate_url_ssrf(url: str) -> None:
    """SSRF prevention: resolve hostname once, verify IP is public."""
    try:
        parsed = urlparse(url)
    except Exception:
        raise HTTPException(status_code=422, detail="Invalid URL")

    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=422, detail="Only http:// and https:// URLs are allowed")
    if not parsed.hostname:
        raise HTTPException(status_code=422, detail="URL must include a hostname")

    try:
        resolved = {
            ipaddress.ip_address(item[4][0])
            for item in socket.getaddrinfo(
                parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        }
    except (socket.gaierror, OSError):
        raise HTTPException(status_code=422, detail=f"Cannot resolve hostname: {parsed.hostname}")
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid IP address resolved")

    if not resolved or any(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        for ip in resolved
    ):
        raise HTTPException(status_code=422, detail="URL resolves to a non-public IP address (blocked for security)")


def _extract_text_from_html(html: str, url: str) -> tuple[str, str]:
    """Return (page_title, body_text) extracted from HTML."""
    try:
        from bs4 import BeautifulSoup
        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception:
            soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            tag.decompose()

        page_title = soup.find("title")
        title_text = page_title.get_text(strip=True) if page_title else (urlparse(url).hostname or "Web page")

        main = soup.find("main") or soup.find("article") or soup.body or soup
        text = main.get_text(separator="\n", strip=True) if main else soup.get_text(separator="\n", strip=True)
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        return title_text[:255], "\n".join(lines)[:50_000]

    except ImportError:
        import re
        text = re.sub(r"<[^>]+>", " ", html)
        return urlparse(url).hostname or "Web page", " ".join(text.split())[:50_000]


@router.post("/documents/url", response_model=Document, status_code=status.HTTP_201_CREATED)
async def create_document_from_url(
    url: str = Body(..., embed=True),
    title: Optional[str] = Body(None, embed=True),
    current_user: dict = Depends(get_current_active_user),
    workspace_context: dict = Depends(get_current_workspace_context),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Fetch a public URL, extract text, create a Document.
    SSRF-safe: validates IP at resolve time; does not follow redirects.
    """
    url = url.strip()
    _validate_url_ssrf(url)

    try:
        async with httpx.AsyncClient(
            follow_redirects=False,
            timeout=httpx.Timeout(connect=5.0, read=15.0, write=5.0, pool=5.0),
            headers={"User-Agent": "content-repurpose-bot/1.0"},
        ) as client:
            response = await client.get(url)
    except httpx.TimeoutException:
        raise HTTPException(status_code=422, detail="Request timed out fetching URL")
    except httpx.RequestError as e:
        raise HTTPException(status_code=422, detail=f"Failed to fetch URL: {str(e)}")

    if response.is_redirect:
        raise HTTPException(
            status_code=422,
            detail="URL redirects are not followed for security. Provide the final destination URL.",
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=422, detail=f"URL returned HTTP {response.status_code}")

    content_type = response.headers.get("content-type", "")
    if not any(t in content_type for t in ("text/html", "text/plain", "application/xhtml")):
        raise HTTPException(status_code=422, detail=f"Unsupported content type: {content_type}")

    page_title, extracted_text = _extract_text_from_html(response.text, url)
    if len(extracted_text.strip()) < 50:
        raise HTTPException(status_code=422, detail="Extracted content is too short to be useful")

    doc_title = (title or page_title)[:255]
    workspace_id = workspace_context["workspace_id"]

    if db:
        can_create, error_msg = await workspace_service.check_workspace_limits(db, workspace_id, "create_document")
        if not can_create:
            raise HTTPException(status_code=400, detail=error_msg)

        try:
            document_db = DocumentDB(
                workspace_id=workspace_id,
                user_id=current_user["id"],
                title=doc_title,
                file_path="url_input",
                original_filename=f"{doc_title}.txt",
                content_type="text/plain",
                file_size=len(extracted_text.encode("utf-8")),
                extracted_text=extracted_text,
                doc_metadata={
                    "source": "url_input",
                    "source_url": url,
                    "word_count": len(extracted_text.split()),
                    "extraction_method": "html_scrape",
                    "http_status": response.status_code,
                },
                status=DocumentStatus.COMPLETED,
                created_by=current_user["id"],
            )
            db.add(document_db)
            await db.commit()
            await db.refresh(document_db)
            return Document(
                id=document_db.id, user_id=document_db.user_id, title=document_db.title,
                description=None, file_path=document_db.file_path,
                original_filename=document_db.original_filename, content_type=document_db.content_type,
                status=document_db.status, created_at=document_db.created_at, updated_at=document_db.updated_at,
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to create document: {str(e)}")
    else:
        doc_uuid = uuid.uuid4()
        doc = {"id": str(doc_uuid), "user_id": current_user["id"], "title": doc_title,
               "file_path": "url_input", "original_filename": f"{doc_title}.txt",
               "content_type": "text/plain", "status": DocumentStatus.COMPLETED,
               "created_at": datetime.now(), "updated_at": datetime.now(), "extracted_text": extracted_text}
        DOCUMENTS_DB.append(doc)
        return Document(
            id=doc_uuid, user_id=uuid.UUID(current_user["id"]), title=doc_title, description=None,
            file_path="url_input", original_filename=f"{doc_title}.txt", content_type="text/plain",
            status=DocumentStatus.COMPLETED, created_at=doc["created_at"], updated_at=doc["updated_at"],
        )


@router.get("/documents", response_model=DocumentList)
async def get_user_documents(
    current_user: dict = Depends(get_current_active_user),
    workspace_context: dict = Depends(get_current_workspace_context),
    db: AsyncSession = Depends(get_db_session),
):
    workspace_id = workspace_context["workspace_id"]

    if db:

        # Get documents with RLS automatically filtering by workspace
        stmt = (
            select(DocumentDB)
            .where(
                and_(
                    DocumentDB.workspace_id == workspace_id,
                    DocumentDB.user_id == current_user["id"],
                    DocumentDB.deleted_at.is_(None),
                )
            )
            .order_by(DocumentDB.created_at.desc())
        )

        result = await db.execute(stmt)
        documents_db = result.scalars().all()

        documents = []
        for doc_db in documents_db:
            documents.append(
                Document(
                    id=doc_db.id,
                    user_id=doc_db.user_id,
                    title=doc_db.title,
                    description=doc_db.description,
                    file_path=doc_db.file_path,
                    original_filename=doc_db.original_filename,
                    content_type=doc_db.content_type,
                    status=doc_db.status,
                    created_at=doc_db.created_at,
                    updated_at=doc_db.updated_at,
                )
            )

        return DocumentList(documents=documents, count=len(documents))


    else:
        # Fallback to in-memory storage
        user_documents = [
            doc for doc in DOCUMENTS_DB if doc["user_id"] == current_user["id"]
        ]
        return DocumentList(documents=user_documents, count=len(user_documents))


@router.get("/documents/{document_id}", response_model=Document)
async def get_document(
    document_id: uuid.UUID,
    current_user: dict = Depends(get_current_active_user),
    workspace_context: dict = Depends(get_current_workspace_context),
    db: AsyncSession = Depends(get_db_session),
):
    workspace_id = workspace_context["workspace_id"]

    if db:

        stmt = select(DocumentDB).where(
            and_(
                DocumentDB.id == document_id,
                DocumentDB.workspace_id == workspace_id,
                DocumentDB.user_id == current_user["id"],
                DocumentDB.deleted_at.is_(None),
            )
        )

        result = await db.execute(stmt)
        document_db = result.scalar_one_or_none()

        if not document_db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            )

        return Document(
            id=document_db.id,
            user_id=document_db.user_id,
            title=document_db.title,
            description=document_db.description,
            file_path=document_db.file_path,
            original_filename=document_db.original_filename,
            content_type=document_db.content_type,
            status=document_db.status,
            created_at=document_db.created_at,
            updated_at=document_db.updated_at,
        )


    else:
        # Fallback to in-memory storage - search by UUID string
        document_id_str = str(document_id)
        
        for doc in DOCUMENTS_DB:
            if doc["id"] == document_id_str and doc["user_id"] == current_user["id"]:
                return Document(
                    id=uuid.UUID(doc["id"]),
                    user_id=uuid.UUID(doc["user_id"]),
                    title=doc["title"],
                    description=doc["description"],
                    file_path=doc["file_path"],
                    original_filename=doc["original_filename"],
                    content_type=doc["content_type"],
                    status=doc["status"],
                    created_at=doc["created_at"],
                    updated_at=doc["updated_at"],
                )

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )


@router.get("/documents/{document_id}/preview")
async def get_document_preview(
    document_id: uuid.UUID,
    current_user: dict = Depends(get_current_active_user),
    workspace_context: dict = Depends(get_current_workspace_context),
    db: AsyncSession = Depends(get_db_session),
):
    """Get document preview image"""
    from fastapi.responses import FileResponse

    workspace_id = workspace_context["workspace_id"]

    if db:

        stmt = select(DocumentDB).where(
            and_(
                DocumentDB.id == document_id,
                DocumentDB.workspace_id == workspace_id,
                DocumentDB.user_id == current_user["id"],
                DocumentDB.deleted_at.is_(None),
            )
        )

        result = await db.execute(stmt)
        document_db = result.scalar_one_or_none()

        if not document_db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            )

        # Check if preview exists in metadata
        preview_path = None
        if document_db.doc_metadata and "preview_path" in document_db.doc_metadata:
            preview_path = document_db.doc_metadata["preview_path"]

        if preview_path:
            full_preview_path = os.path.join(settings.UPLOAD_DIR, preview_path)
            if os.path.exists(full_preview_path):
                return FileResponse(
                    path=full_preview_path,
                    media_type="image/png",
                    filename=f"preview_{document_db.original_filename}.png",
                )

        # No preview available
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preview not available for this document",
        )


    else:
        # Fallback to in-memory storage - search by UUID string
        document_id_str = str(document_id)
        
        for doc in DOCUMENTS_DB:
            if doc["id"] == document_id_str and doc["user_id"] == current_user["id"]:
                preview_path = doc.get("preview_path")
                if preview_path:
                    full_preview_path = os.path.join(settings.UPLOAD_DIR, preview_path)
                    if os.path.exists(full_preview_path):
                        return FileResponse(
                            path=full_preview_path,
                            media_type="image/png",
                            filename=f"preview_{doc['original_filename']}.png",
                        )
                break

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Preview not available for this document",
        )


@router.get("/documents/{document_id}/content")
async def get_document_content(
    document_id: uuid.UUID,
    current_user: dict = Depends(get_current_active_user),
    workspace_context: dict = Depends(get_current_workspace_context),
    db: AsyncSession = Depends(get_db_session),
):
    """Get extracted document content and metadata"""
    workspace_id = workspace_context["workspace_id"]

    if db:

        stmt = select(DocumentDB).where(
            and_(
                DocumentDB.id == document_id,
                DocumentDB.workspace_id == workspace_id,
                DocumentDB.user_id == current_user["id"],
                DocumentDB.deleted_at.is_(None),
            )
        )

        result = await db.execute(stmt)
        document_db = result.scalar_one_or_none()

        if not document_db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            )

        return {
            "document_id": document_db.id,
            "title": document_db.title,
            "original_filename": document_db.original_filename,
            "extracted_text": document_db.extracted_text or "",
            "metadata": document_db.doc_metadata or {},
            "status": document_db.status,
            "created_at": document_db.created_at,
            "updated_at": document_db.updated_at,
        }


    else:
        # Fallback to in-memory storage - search by UUID string
        document_id_str = str(document_id)
        
        for doc in DOCUMENTS_DB:
            if doc["id"] == document_id_str and doc["user_id"] == current_user["id"]:
                return {
                    "document_id": doc["id"],
                    "title": doc["title"],
                    "original_filename": doc["original_filename"],
                    "extracted_text": doc.get("extracted_text", ""),
                    "metadata": doc.get("metadata", {}),
                    "status": doc["status"],
                    "created_at": doc["created_at"],
                    "updated_at": doc["updated_at"],
                }

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    current_user: dict = Depends(get_current_active_user),
    workspace_context: dict = Depends(get_current_workspace_context),
    db: AsyncSession = Depends(get_db_session),
):
    workspace_id = workspace_context["workspace_id"]

    if db:

        stmt = select(DocumentDB).where(
            and_(
                DocumentDB.id == document_id,
                DocumentDB.workspace_id == workspace_id,
                DocumentDB.user_id == current_user["id"],
                DocumentDB.deleted_at.is_(None),
            )
        )

        result = await db.execute(stmt)
        document_db = result.scalar_one_or_none()

        if not document_db:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
            )

        # Soft delete (mark as deleted)
        document_db.deleted_at = datetime.utcnow()
        document_db.deleted_by = current_user["id"]

        await db.commit()

        # Optionally delete physical file
        if os.path.exists(document_db.file_path):
            os.remove(document_db.file_path)


    else:
        # Fallback to in-memory storage - search by UUID string
        document_id_str = str(document_id)
        
        for i, doc in enumerate(DOCUMENTS_DB):
            if doc["id"] == document_id_str and doc["user_id"] == current_user["id"]:
                # Delete the file
                if os.path.exists(doc["file_path"]):
                    os.remove(doc["file_path"])

                # Remove document from db
                DOCUMENTS_DB.pop(i)
                return

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
        )


# CORS OPTIONS handlers for documents endpoints

