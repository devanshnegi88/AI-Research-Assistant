"""
Document business logic.

Upload flow: validate → dedup check → persist to storage → insert DB row →
extract text → clean → chunk → embed → index in vector store.

Previously Celery dispatched; now runs inline in the API request since
Redis / Celery have been removed from the stack.
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
from app.services.embedding.embedding_service import get_embedding_service
from app.storage.base import StorageBackend
from app.vectorstore.base import VectorRecord, VectorStore

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

        # Process inline (Celery was removed from the stack).
        try:
            await self._process_document(document, file_bytes)
        except Exception as exc:  # noqa: BLE001 — must persist failure state
            document.status = DocumentStatus.FAILED
            document.error_message = str(exc)[:2000]
            logger.error(
                "document_processing_failed",
                extra={"document_id": str(document.id)},
                exc_info=exc,
            )

        logger.info("document_upload_accepted", extra={"document_id": str(document.id)})
        return document

    async def _process_document(self, document: Document, file_bytes: bytes) -> None:
        """Extract → clean → chunk → embed → index.  Runs inline."""
        document.status = DocumentStatus.PROCESSING

        extractor = get_extractor(document.document_type)
        result = extractor.extract(file_bytes)

        cleaned_text = clean_text(result.text)
        chunks = chunk_text(cleaned_text)

        chunk_rows = [
            DocumentChunk(
                id=uuid.uuid4(),
                document_id=document.id,
                chunk_index=chunk.index,
                content=chunk.content,
                char_count=chunk.char_count,
            )
            for chunk in chunks
        ]

        # Embed and index into vector store
        if chunk_rows:
            embedding_service = get_embedding_service()
            vectors = embedding_service.embed_batch([c.content for c in chunk_rows])

            records = [
                VectorRecord(
                    id=chunk.id,
                    vector=vector,
                    payload={
                        "owner_id": str(document.owner_id),
                        "document_id": str(document.id),
                        "document_type": document.document_type.value,
                        "chunk_index": chunk.chunk_index,
                    },
                )
                for chunk, vector in zip(chunk_rows, vectors)
            ]

            await self.vector_store.delete_by_filter({"document_id": str(document.id)})
            await self.vector_store.upsert(records)

        document.extracted_text = cleaned_text
        document.doc_metadata = {**result.metadata, "used_ocr": result.used_ocr}
        document.chunk_count = len(chunks)
        document.status = DocumentStatus.COMPLETED
        document.error_message = None

        await self.document_repository.replace_chunks(document.id, chunk_rows)

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