"""
Hybrid retriever — runs dense vector search (Qdrant) and sparse BM25 search
independently, then fuses the two rank lists via Reciprocal Rank Fusion.

RRF is used instead of a weighted sum of raw scores because cosine
similarity and BM25 scores live on incomparable scales; RRF only needs
each method's *rank position*, which makes the fusion scale-free and
avoids having to tune a blend weight per corpus.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.core.config import settings
from app.repositories.chunk_repository import ChunkRepository
from app.schemas.search import SearchFilters
from app.services.embedding.embedding_service import EmbeddingService
from app.services.search.bm25_index import BM25Index
from app.vectorstore.base import VectorStore


@dataclass
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    fused_score: float


class HybridRetriever:
    def __init__(
        self,
        vector_store: VectorStore,
        embedding_service: EmbeddingService,
        chunk_repository: ChunkRepository,
    ) -> None:
        self.vector_store = vector_store
        self.embedding_service = embedding_service
        self.chunk_repository = chunk_repository

    async def retrieve(
        self,
        query: str,
        owner_id: uuid.UUID,
        top_k: int,
        filters: SearchFilters | None = None,
    ) -> list[RetrievedChunk]:
        pool_size = settings.SEARCH_CANDIDATE_POOL_SIZE

        vector_ranked = await self._vector_search(query, owner_id, filters, pool_size)
        bm25_ranked = await self._bm25_search(query, owner_id, filters, pool_size)

        fused = self._reciprocal_rank_fusion([vector_ranked, bm25_ranked])
        return fused[:top_k]

    async def _vector_search(
        self,
        query: str,
        owner_id: uuid.UUID,
        filters: SearchFilters | None,
        pool_size: int,
    ) -> list[tuple[uuid.UUID, uuid.UUID]]:
        """Returns [(chunk_id, document_id), ...] in descending relevance order."""
        query_vector = self.embedding_service.embed_query(query)

        vector_filters: dict = {"owner_id": str(owner_id)}
        if filters:
            if filters.document_type is not None:
                vector_filters["document_type"] = filters.document_type.value
            # document_ids and filename_contains aren't single-value equality
            # filters, so they're applied as a post-filter below rather than
            # pushed into Qdrant's payload match.

        results = await self.vector_store.search(query_vector, pool_size, vector_filters)

        pairs = [(r.id, uuid.UUID(r.payload["document_id"])) for r in results]

        if filters and filters.document_ids:
            allowed = set(filters.document_ids)
            pairs = [p for p in pairs if p[1] in allowed]

        return pairs

    async def _bm25_search(
        self,
        query: str,
        owner_id: uuid.UUID,
        filters: SearchFilters | None,
        pool_size: int,
    ) -> list[tuple[uuid.UUID, uuid.UUID]]:
        candidates = await self.chunk_repository.get_candidates_for_owner(
            owner_id=owner_id,
            document_ids=filters.document_ids if filters else None,
            document_type=filters.document_type if filters else None,
            filename_contains=filters.filename_contains if filters else None,
        )
        if not candidates:
            return []

        index = BM25Index(
            chunk_ids=[c.id for c in candidates],
            texts=[c.content for c in candidates],
        )
        doc_id_by_chunk = {c.id: c.document_id for c in candidates}

        scored = index.search(query, pool_size)
        return [(chunk_id, doc_id_by_chunk[chunk_id]) for chunk_id, _score in scored]

    def _reciprocal_rank_fusion(
        self, ranked_lists: list[list[tuple[uuid.UUID, uuid.UUID]]]
    ) -> list[RetrievedChunk]:
        k = settings.RRF_K
        scores: dict[uuid.UUID, float] = {}
        doc_id_by_chunk: dict[uuid.UUID, uuid.UUID] = {}

        for ranked_list in ranked_lists:
            for rank, (chunk_id, document_id) in enumerate(ranked_list, start=1):
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
                doc_id_by_chunk[chunk_id] = document_id

        fused = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
        return [
            RetrievedChunk(
                chunk_id=chunk_id,
                document_id=doc_id_by_chunk[chunk_id],
                fused_score=score,
            )
            for chunk_id, score in fused
        ]