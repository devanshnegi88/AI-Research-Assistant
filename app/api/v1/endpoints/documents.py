"""
Document routes — upload, list, get, delete, processing status.

All routes are scoped to the authenticated user's own documents; there is
no cross-user access in Phase 2 (no admin document browsing yet).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from app.core.dependencies import get_current_active_user, get_document_service
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.document import (
    DocumentDetailRead,
    DocumentRead,
    DocumentStatusResponse,
    DocumentUploadResponse,
)
from app.services.document.document_service import DocumentService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    document_service: DocumentService = Depends(get_document_service),
) -> DocumentUploadResponse:
    file_bytes = await file.read()
    document = await document_service.upload(
        owner_id=current_user.id,
        filename=file.filename or "untitled",
        content_type=file.content_type or "application/octet-stream",
        file_bytes=file_bytes,
    )
    return DocumentUploadResponse(
        id=document.id,
        original_filename=document.original_filename,
        document_type=document.document_type,
        status=document.status,
    )


@router.get("", response_model=PaginatedResponse[DocumentRead])
async def list_documents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    document_service: DocumentService = Depends(get_document_service),
) -> PaginatedResponse[DocumentRead]:
    return await document_service.list_for_owner(current_user.id, page, page_size)


@router.get("/{document_id}", response_model=DocumentDetailRead)
async def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    document_service: DocumentService = Depends(get_document_service),
):
    return await document_service.get_for_owner(document_id, current_user.id)


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
async def get_document_status(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    document_service: DocumentService = Depends(get_document_service),
):
    return await document_service.get_for_owner(document_id, current_user.id)


from fastapi import Response

@router.delete(
    "/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    document_service: DocumentService = Depends(get_document_service),
):
    await document_service.delete_for_owner(document_id, current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)