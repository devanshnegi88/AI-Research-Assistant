"""Document-related Pydantic v2 schemas (DTOs)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import DocumentStatus, DocumentType


class DocumentUploadResponse(BaseModel):
    id: uuid.UUID
    original_filename: str
    document_type: DocumentType
    status: DocumentStatus
    message: str = "Upload accepted — processing in background"


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    document_type: DocumentType
    mime_type: str
    file_size_bytes: int
    status: DocumentStatus
    error_message: str | None
    doc_metadata: dict | None
    chunk_count: int
    created_at: datetime
    updated_at: datetime


class DocumentDetailRead(DocumentRead):
    """Includes extracted text — only returned from the single-document GET."""

    extracted_text: str | None


class DocumentStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: DocumentStatus
    error_message: str | None
    chunk_count: int


class DocumentChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chunk_index: int
    content: str
    char_count: int
