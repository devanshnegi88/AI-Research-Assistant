"""
Document business logic.

Upload is split across two phases:
1. `upload()` (this file, runs in the API request) — validate, hash-check
   for duplicates, persist to storage, insert a `pending` DB row, enqueue
   the Celery task. Fast — no extraction/OCR happens here.
2. `process_document` (Celery task, `workers/tasks.py`) — does the actual
   extraction, cleaning, and chunking, then updates the row's status.
"""

from __future__ import annotations

import uuid

from app.core.config import settings
from app.core.exceptions import BadRequestException, NotFoundException
from app.core.logging import get_logger
from app.models.document import Document
from app.models.enums import DocumentStatus, DocumentType
from app.repositories.document_repository import DocumentRepository
from app.schemas.common import PaginatedResponse
from app.services.document.duplicate_detection import compute_content_hash
from app.storage.base import StorageBackend
from app.vectorstore.base import VectorStore

logger = get_logger(__name__)

_EXTENSION_TO_TYPE: dict[str, DocumentType] = {
    "pdf": DocumentType.PDF,
    "docx": DocumentType.DOCX,
    "txt": DocumentType.TXT,
    "png": DocumentType.IMAGE,
    "jpg": DocumentType.IMAGE,
    "jpeg": DocumentType.IMAGE,
}


class DocumentService:
    def __init__(
        self,
        document_repository: DocumentRepository,
        storage: StorageBackend,
        vector_store: VectorStore,
    ) -> None:
        self.document_repository = document_repository
        self.storage = storage
        self.vector_store = vector_store

    async def upload(
        self,
        owner_id: uuid.UUID,
        filename: str,
        content_type: str,
        file_bytes: bytes,
    ) -> Document:
        document_type = self._resolve_document_type(filename)
        self._validate_size(file_bytes)

        content_hash = compute_content_hash(file_bytes)
        existing = await self.document_repository.get_by_content_hash_for_owner(
            content_hash, owner_id
        )
        if existing is not None:
            logger.info(
                "duplicate_upload_detected",
                extra={"owner_id": str(owner_id), "existing_document_id": str(existing.id)},
            )
            return existing

        storage_key = f"{owner_id}/{uuid.uuid4()}_{filename}"
        storage_path = await self.storage.save(storage_key, file_bytes)

        document = Document(
            owner_id=owner_id,
            original_filename=filename,
            storage_path=storage_path,
            document_type=document_type,
            mime_type=content_type,
            file_size_bytes=len(file_bytes),
            content_hash=content_hash,
            status=DocumentStatus.PENDING,
        )
        document = await self.document_repository.create(document)

        # Imported lazily to avoid a hard import-time dependency from the
        # API process on the Celery app configuration.
        from app.workers.tasks import process_document

        process_document.delay(str(document.id))

        logger.info("document_upload_accepted", extra={"document_id": str(document.id)})
        return document

    async def get_for_owner(self, document_id: uuid.UUID, owner_id: uuid.UUID) -> Document:
        document = await self.document_repository.get_by_id_for_owner(document_id, owner_id)
        if document is None:
            raise NotFoundException("Document not found")
        return document

    async def list_for_owner(
        self, owner_id: uuid.UUID, page: int, page_size: int
    ) -> PaginatedResponse[Document]:
        offset = (page - 1) * page_size
        items = await self.document_repository.list_for_owner(owner_id, offset, page_size)
        total = await self.document_repository.count_for_owner(owner_id)
        return PaginatedResponse.build(items, total, page, page_size)

    async def delete_for_owner(self, document_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        document = await self.get_for_owner(document_id, owner_id)
        await self.storage.delete(document.storage_path)
        # Best-effort vector cleanup — deliberately after storage delete but
        # before the DB delete, so a Qdrant failure here still leaves the
        # Postgres row in place to retry against rather than being silently
        # orphaned on both sides.
        await self.vector_store.delete_by_filter({"document_id": str(document_id)})
        await self.document_repository.delete(document)
        logger.info("document_deleted", extra={"document_id": str(document_id)})

    def _resolve_document_type(self, filename: str) -> DocumentType:
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if extension not in settings.ALLOWED_UPLOAD_EXTENSIONS:
            raise BadRequestException(
                f"Unsupported file extension: .{extension}. "
                f"Allowed: {settings.ALLOWED_UPLOAD_EXTENSIONS}"
            )
        return _EXTENSION_TO_TYPE[extension]

    def _validate_size(self, file_bytes: bytes) -> None:
        if len(file_bytes) > settings.max_upload_size_bytes:
            raise BadRequestException(
                f"File exceeds maximum upload size of {settings.MAX_UPLOAD_SIZE_MB}MB"
            )
        if len(file_bytes) == 0:
            raise BadRequestException("Uploaded file is empty")