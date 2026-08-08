"""
Document business logic.

Upload runs synchronously in the API request:
1. `upload()` — validate, hash-check for duplicates, persist to storage,
   insert a DB row, then process it inline (extract → clean → chunk).
   (Previously this enqueued a Celery task; Celery/Redis has been removed.)
2. Processing is done here via `_process_document()` using the same async
   session, so no separate worker/broker is required.
"""

from __future__ import annotations

import uuid

from app.core.config import settings
from app.core.exceptions import BadRequestException, NotFoundException
from app.core.logging import get_logger
from app.models.document import Document, DocumentChunk
from app.models.enums import DocumentStatus, DocumentType
from app.repositories.document_repository import DocumentRepository
from app.schemas.common import PaginatedResponse
from app.services.document.chunking import chunk_text
from app.services.document.duplicate_detection import compute_content_hash
from app.services.document.extractors import get_extractor
from app.services.document.text_cleaning import clean_text
from app.storage.base import StorageBackend

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
        self, document_repository: DocumentRepository, storage: StorageBackend
    ) -> None:
        self.document_repository = document_repository
        self.storage = storage

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

        # Synchronous processing — Celery/Redis removed. Extraction,
        # cleaning, and chunking happen inline in this request.
        await self._process_document(document, file_bytes)

        logger.info("document_upload_accepted", extra={"document_id": str(document.id)})
        return document

    async def _process_document(self, document: Document, file_bytes: bytes) -> None:
        """Extract → clean → chunk → persist, inline (no Celery worker)."""
        try:
            document.status = DocumentStatus.PROCESSING
            await self.document_repository.session.flush()

            extractor = get_extractor(document.document_type)
            result = extractor.extract(file_bytes)

            cleaned_text = clean_text(result.text)
            chunks = chunk_text(cleaned_text)

            document.extracted_text = cleaned_text
            document.doc_metadata = {**result.metadata, "used_ocr": result.used_ocr}
            document.chunk_count = len(chunks)
            document.status = DocumentStatus.COMPLETED
            document.error_message = None

            await self.document_repository.replace_chunks(
                document.id,
                [
                    DocumentChunk(
                        document_id=document.id,
                        chunk_index=chunk.index,
                        content=chunk.content,
                        char_count=chunk.char_count,
                    )
                    for chunk in chunks
                ],
            )

            logger.info(
                "document_processing_completed",
                extra={"document_id": str(document.id), "chunk_count": len(chunks)},
            )
        except Exception as exc:  # noqa: BLE001 — persist failure state
            await self.document_repository.session.rollback()
            document.status = DocumentStatus.FAILED
            document.error_message = str(exc)[:2000]
            await self.document_repository.session.flush()
            logger.error(
                "document_processing_failed",
                extra={"document_id": str(document.id)},
                exc_info=exc,
            )

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
