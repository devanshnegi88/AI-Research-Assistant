"""
Celery tasks — the actual extraction → clean → chunk → persist pipeline.

NOTE: Celery has been removed from the application (it depended on Redis as
its message broker). Document processing now runs synchronously inside the
API request via `DocumentService._process_document`. This module is kept
only as a commented-out reference.
"""

# from __future__ import annotations
#
# import uuid
#
# from sqlalchemy import create_engine
# from sqlalchemy.orm import Session, sessionmaker
#
# from app.core.config import settings
# from app.core.logging import get_logger, setup_logging
# from app.models.document import Document, DocumentChunk
# from app.models.enums import DocumentStatus
# from app.services.document.chunking import chunk_text
# from app.services.document.extractors import get_extractor
# from app.services.document.text_cleaning import clean_text
# from app.workers.celery_app import celery_app
#
# setup_logging()
# logger = get_logger(__name__)
#
# # Sync engine — derived from the same DATABASE_URL, swapping the async
# # driver for a sync one, since Celery's worker doesn't run an event loop.
# _sync_url = str(settings.DATABASE_URL).replace("postgresql+asyncpg", "postgresql+psycopg2")
# _engine = create_engine(_sync_url, pool_pre_ping=True)
# SyncSessionLocal = sessionmaker(bind=_engine)
#
#
# @celery_app.task(name="process_document", bind=True, max_retries=2, default_retry_delay=30)
# def process_document(self, document_id: str) -> None:
#     session: Session = SyncSessionLocal()
#     try:
#         document = session.get(Document, uuid.UUID(document_id))
#         if document is None:
#             logger.warning("process_document_missing", extra={"document_id": document_id})
#             return
#
#         document.status = DocumentStatus.PROCESSING
#         session.commit()
#
#         try:
#             _run_pipeline(session, document)
#         except Exception as exc:  # noqa: BLE001 — must persist failure state
#             session.rollback()
#             document = session.get(Document, uuid.UUID(document_id))
#             document.status = DocumentStatus.FAILED
#             document.error_message = str(exc)[:2000]
#             session.commit()
#             logger.error(
#                 "document_processing_failed",
#                 extra={"document_id": document_id},
#                 exc_info=exc,
#             )
#             raise self.retry(exc=exc)
#
#     finally:
#         session.close()
#
#
# def _run_pipeline(session: Session, document: Document) -> None:
#     # Read directly by path — LocalStorageBackend's API is async and there's
#     # no event loop in this Celery worker context to await it.
#     with open(document.storage_path, "rb") as f:
#         file_bytes = f.read()
#
#     extractor = get_extractor(document.document_type)
#     result = extractor.extract(file_bytes)
#
#     cleaned_text = clean_text(result.text)
#     chunks = chunk_text(cleaned_text)
#
#     document.extracted_text = cleaned_text
#     document.doc_metadata = {**result.metadata, "used_ocr": result.used_ocr}
#     document.chunk_count = len(chunks)
#     document.status = DocumentStatus.COMPLETED
#     document.error_message = None
#
#     session.query(DocumentChunk).filter(
#         DocumentChunk.document_id == document.id
#     ).delete()
#     session.add_all(
#         [
#             DocumentChunk(
#                 document_id=document.id,
#                 chunk_index=chunk.index,
#                 content=chunk.content,
#                 char_count=chunk.char_count,
#             )
#             for chunk in chunks
#         ]
#     )
#
#     session.commit()
#     logger.info(
#         "document_processing_completed",
#         extra={"document_id": str(document.id), "chunk_count": len(chunks)},
#     )
