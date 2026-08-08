"""Document data-access layer."""

from __future__ import annotations

import uuid

from sqlalchemy import delete as sql_delete, func, select

from app.models.document import Document, DocumentChunk
from app.repositories.base import BaseRepository


class DocumentRepository(BaseRepository[Document]):
    model = Document

    async def get_by_id_for_owner(
        self, document_id: uuid.UUID, owner_id: uuid.UUID
    ) -> Document | None:
        stmt = select(Document).where(
            Document.id == document_id, Document.owner_id == owner_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_owner(
        self, owner_id: uuid.UUID, offset: int = 0, limit: int = 20
    ) -> list[Document]:
        stmt = (
            select(Document)
            .where(Document.owner_id == owner_id)
            .order_by(Document.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_owner(self, owner_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(Document).where(
            Document.owner_id == owner_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def get_by_content_hash_for_owner(
        self, content_hash: str, owner_id: uuid.UUID
    ) -> Document | None:
        """Dedup lookup — scoped per-owner, not global."""
        stmt = select(Document).where(
            Document.content_hash == content_hash,
            Document.owner_id == owner_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def replace_chunks(
        self, document_id: uuid.UUID, chunks: list[DocumentChunk]
    ) -> None:
        """Delete any existing chunks for this document, then insert fresh
        ones — used on (re)processing so retries don't accumulate stale rows.
        """
        await self.session.execute(
            sql_delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )
        self.session.add_all(chunks)
        await self.session.flush()
