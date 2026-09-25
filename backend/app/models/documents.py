"""
Document models for Content Repurpose API
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum
import uuid


class DocumentStatus(str, Enum):
    """Document processing status"""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class DocumentBase(BaseModel):
    title: str = Field(..., max_length=255)
    description: Optional[str] = None


class DocumentCreate(DocumentBase):
    pass


class Document(DocumentBase):
    id: uuid.UUID
    user_id: uuid.UUID
    file_path: str
    original_filename: str
    content_type: str
    status: DocumentStatus = DocumentStatus.PENDING
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DocumentList(BaseModel):
    documents: List[Document]
    count: int


class FileProcessingResult(BaseModel):
    file_path: str
    content: str
    metadata: Dict[str, Any]
    file_hash: str
    preview_path: Optional[str] = None
    content_encoding: str
    word_count: int
    extraction_method: str
    security_scan_passed: bool


class FileUploadResponse(BaseModel):
    document_id: uuid.UUID
    filename: str
    size: int
    content_type: str
    status: str
    message: str