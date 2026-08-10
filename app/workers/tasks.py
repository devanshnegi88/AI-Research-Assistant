"""
Celery tasks — the actual extraction → clean → chunk → persist pipeline.

Runs in a separate worker process from the FastAPI app, so this module uses
a plain sync SQLAlchemy session (not the async engine from `db/session.py`)
to keep the worker simple and avoid sharing an event loop with Celery's
prefork model.
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.logging import get_logger, setup_logging
from app.models.document import Document, DocumentChunk
from app.models.enums import DocumentStatus
from app.services.document.chunking import chunk_text
from app.services.document.extractors import get_extractor
from app.services.document.text_cleaning import clean_text
from app.services.embedding.embedding_service import get_embedding_service
from app.vectorstore.base import VectorRecord
from app.vectorstore.qdrant_store import get_vector_store
from app.workers.celery_app import celery_app

setup_logging()
logger = get_logger(__name__)

# Sync engine — derived from the same DATABASE_URL, swapping the async
# driver for a sync one, since Celery's worker doesn't run an event loop.
_sync_url = str(settings.DATABASE_URL).replace("postgresql+asyncpg", "postgresql+psycopg2")
_engine = create_engine(_sync_url, pool_pre_ping=True)
SyncSessionLocal = sessionmaker(bind=_engine)


@celery_app.task(name="process_document", bind=True, max_retries=2, default_retry_delay=30)
def process_document(self, document_id: str) -> None:
    session: Session = SyncSessionLocal()
    try:
        document = session.get(Document, uuid.UUID(document_id))
        if document is None:
            logger.warning("process_document_missing", extra={"document_id": document_id})
            return

        document.status = DocumentStatus.PROCESSING
        session.commit()

        try:
            _run_pipeline(session, document)
        except Exception as exc:  # noqa: BLE001 — must persist failure state
            session.rollback()
            document = session.get(Document, uuid.UUID(document_id))
            document.status = DocumentStatus.FAILED
            document.error_message = str(exc)[:2000]
            session.commit()
            logger.error(
                "document_processing_failed",
                extra={"document_id": document_id},
                exc_info=exc,
            )
            raise self.retry(exc=exc)

    finally:
        session.close()


def _run_pipeline(session: Session, document: Document) -> None:
    # Read directly by path — LocalStorageBackend's API is async and there's
    # no event loop in this Celery worker context to await it.
    with open(document.storage_path, "rb") as f:
        file_bytes = f.read()

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

    if chunk_rows:
        _embed_and_index_chunks(document, chunk_rows)

    document.extracted_text = cleaned_text
    document.doc_metadata = {**result.metadata, "used_ocr": result.used_ocr}
    document.chunk_count = len(chunks)
    document.status = DocumentStatus.COMPLETED
    document.error_message = None

    session.query(DocumentChunk).filter(
        DocumentChunk.document_id == document.id
    ).delete()
    session.add_all(chunk_rows)

    session.commit()
    logger.info(
        "document_processing_completed",
        extra={"document_id": str(document.id), "chunk_count": len(chunks)},
    )


def _embed_and_index_chunks(document: Document, chunk_rows: list[DocumentChunk]) -> None:
    """Embed each chunk and upsert into Qdrant.

    Runs before the Postgres commit — if embedding/indexing fails, the task
    raises and retries with the document left in a non-committed state,
    rather than leaving Postgres and Qdrant out of sync.
    """
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

    async def _index() -> None:
        vector_store = get_vector_store()
        # Clear any vectors from a previous processing attempt of this
        # document before inserting fresh ones — mirrors the DB-side
        # delete-then-insert in `_run_pipeline`.
        await vector_store.delete_by_filter({"document_id": str(document.id)})
        await vector_store.upsert(records)

    asyncio.run(_index())