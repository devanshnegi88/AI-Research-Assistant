"""
DocumentChunk data-access layer.

Used to resolve citations after retrieval — Qdrant payloads carry enough
to build a citation directly, but this repo backs cases where fresh DB
state is needed (e.g. confirming a chunk's parent document is still owned
by the requesting user, listing chunks for a document, or fetching the
candidate pool BM25 scores over).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.document import Document, DocumentChunk
from app.models.enums import DocumentType
from app.repositories.base import BaseRepository


class ChunkRepository(BaseRepository[DocumentChunk]):
    model = DocumentChunk

    async def get_by_ids_for_owner(
        self, chunk_ids: list[uuid.UUID], owner_id: uuid.UUID
    ) -> list[DocumentChunk]:
        stmt = (
            select(DocumentChunk)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.id.in_(chunk_ids), Document.owner_id == owner_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_document(self, document_id: uuid.UUID) -> list[DocumentChunk]:
        stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_candidates_for_owner(
        self,
        owner_id: uuid.UUID,
        document_ids: list[uuid.UUID] | None = None,
        document_type: DocumentType | None = None,
        filename_contains: str | None = None,
        limit: int = 500,
    ) -> list[DocumentChunk]:
        """Filtered chunk pool for BM25 to score independently of the
        vector store — applies the same `SearchFilters` as vector search
        so both retrieval methods see a consistent candidate universe."""
        stmt = (
            select(DocumentChunk)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(Document.owner_id == owner_id)
        )

        if document_ids:
            stmt = stmt.where(Document.id.in_(document_ids))
        if document_type is not None:
            stmt = stmt.where(Document.document_type == document_type)
        if filename_contains:
            stmt = stmt.where(Document.original_filename.ilike(f"%{filename_contains}%"))

        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())