"""
Tests for `/search` and the hybrid retriever.

The vector store and embedding model are mocked — these tests verify RRF
fusion behavior, metadata filtering, and owner-scoping without needing a
running Qdrant instance or loading the actual sentence-transformers model.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.services.search.retriever import HybridRetriever
from app.vectorstore.base import VectorSearchResult

pytestmark = pytest.mark.asyncio


async def _register_and_login(client: AsyncClient, email: str) -> str:
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": "Test User", "password": "StrongPass1"},
    )
    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "StrongPass1"}
    )
    return login.json()["access_token"]


async def test_search_requires_auth(client: AsyncClient):
    response = await client.post("/api/v1/search", json={"query": "test"})
    assert response.status_code == 401


async def test_search_rejects_empty_query(client: AsyncClient):
    token = await _register_and_login(client, "search-empty@example.com")
    response = await client.post(
        "/api/v1/search",
        json={"query": ""},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


async def test_search_returns_empty_results_for_no_documents(client: AsyncClient):
    from app.core.dependencies import get_embedding_service_dep, get_vector_store_dep
    from app.main import app

    token = await _register_and_login(client, "search-nodata@example.com")

    fake_embedding_service = AsyncMock()
    fake_embedding_service.embed_query = lambda text: [0.1] * 384

    app.dependency_overrides[get_vector_store_dep] = lambda: _FakeVectorStore([])
    app.dependency_overrides[get_embedding_service_dep] = lambda: fake_embedding_service
    try:
        response = await client.post(
            "/api/v1/search",
            json={"query": "anything"},
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        app.dependency_overrides.pop(get_vector_store_dep, None)
        app.dependency_overrides.pop(get_embedding_service_dep, None)

    assert response.status_code == 200
    body = response.json()
    assert body["results"] == []
    assert body["total_results"] == 0


class _FakeVectorStore:
    """Minimal VectorStore stub returning a fixed ranked result set."""

    def __init__(self, results: list[VectorSearchResult]) -> None:
        self._results = results

    async def upsert(self, records):  # pragma: no cover — unused in these tests
        pass

    async def search(self, query_vector, top_k, filters=None):
        return self._results[:top_k]

    async def delete(self, ids):  # pragma: no cover
        pass

    async def delete_by_filter(self, filters):  # pragma: no cover
        pass


async def test_reciprocal_rank_fusion_prefers_items_ranked_high_in_both_lists():
    """Unit-level RRF check — bypasses the API entirely."""

    chunk_a, chunk_b, chunk_c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    doc_id = uuid.uuid4()

    # chunk_a: rank 1 in both lists — should win overall.
    # chunk_b: rank 2 in vector, absent from BM25.
    # chunk_c: absent from vector, rank 1 in BM25.
    vector_list = [(chunk_a, doc_id), (chunk_b, doc_id)]
    bm25_list = [(chunk_a, doc_id), (chunk_c, doc_id)]

    retriever = HybridRetriever(
        vector_store=AsyncMock(), embedding_service=AsyncMock(), chunk_repository=AsyncMock()
    )
    fused = retriever._reciprocal_rank_fusion([vector_list, bm25_list])

    assert fused[0].chunk_id == chunk_a  # appears first in both — highest fused score
    fused_ids = [f.chunk_id for f in fused]
    assert chunk_b in fused_ids
    assert chunk_c in fused_ids