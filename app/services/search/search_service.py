"""
Search service — the query-facing orchestration layer.

Turns a raw hybrid retrieval result (chunk ids + fused scores) into
`SearchResultItem`s carrying everything needed for source citation:
document filename, chunk index, and the actual excerpt text.
"""

from __future__ import annotations

import uuid

from app.repositories.chunk_repository import ChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.schemas.search import SearchFilters, SearchResultItem
from app.services.search.retriever import HybridRetriever


class SearchService:
    def __init__(
        self,
        retriever: HybridRetriever,
        chunk_repository: ChunkRepository,
        document_repository: DocumentRepository,
    ) -> None:
        self.retriever = retriever
        self.chunk_repository = chunk_repository
        self.document_repository = document_repository

    async def search(
        self,
        query: str,
        owner_id: uuid.UUID,
        top_k: int,
        filters: SearchFilters | None = None,
    ) -> list[SearchResultItem]:
        retrieved = await self.retriever.retrieve(query, owner_id, top_k, filters)
        if not retrieved:
            return []

        chunk_ids = [r.chunk_id for r in retrieved]
        chunks = await self.chunk_repository.get_by_ids_for_owner(chunk_ids, owner_id)
        chunk_by_id = {c.id: c for c in chunks}

        document_ids = {r.document_id for r in retrieved}
        documents = [
            await self.document_repository.get_by_id_for_owner(doc_id, owner_id)
            for doc_id in document_ids
        ]
        filename_by_document_id = {d.id: d.original_filename for d in documents if d}

        results: list[SearchResultItem] = []
        for rank, item in enumerate(retrieved, start=1):
            chunk = chunk_by_id.get(item.chunk_id)
            if chunk is None:
                # Vector store and Postgres drifted (e.g. chunk deleted
                # since the embedding was indexed) — skip rather than error.
                continue

            results.append(
                SearchResultItem(
                    chunk_id=chunk.id,
                    document_id=chunk.document_id,
                    document_filename=filename_by_document_id.get(
                        chunk.document_id, "unknown"
                    ),
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    score=item.fused_score,
                    rank=rank,
                )
            )

        return results