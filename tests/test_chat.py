"""
Tests for `/chat` (RAG).

The LLM client and search service are mocked — these tests verify the API
contract (auth, request validation, citation shape) and that citation
numbering in the response matches the retrieved chunks, without calling
Gemini or requiring real embeddings/Qdrant/BM25 data.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.schemas.search import SearchResultItem

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


async def test_chat_requires_auth(client: AsyncClient):
    response = await client.post("/api/v1/chat", json={"message": "hello"})
    assert response.status_code == 401


async def test_chat_rejects_empty_message(client: AsyncClient):
    from app.core.dependencies import get_llm_client_dep
    from app.main import app

    token = await _register_and_login(client, "chat-empty@example.com")

    app.dependency_overrides[get_llm_client_dep] = lambda: AsyncMock()
    try:
        response = await client.post(
            "/api/v1/chat",
            json={"message": ""},
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        app.dependency_overrides.pop(get_llm_client_dep, None)

    assert response.status_code == 422


async def test_chat_returns_no_context_message_when_search_finds_nothing(
    client: AsyncClient,
):
    from app.core.dependencies import get_search_service, get_llm_client_dep
    from app.main import app

    token = await _register_and_login(client, "chat-nodata@example.com")

    fake_search_service = AsyncMock()
    fake_search_service.search = AsyncMock(return_value=[])

    app.dependency_overrides[get_search_service] = lambda: fake_search_service
    app.dependency_overrides[get_llm_client_dep] = lambda: AsyncMock()
    try:
        response = await client.post(
            "/api/v1/chat",
            json={"message": "What does the document say?"},
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        app.dependency_overrides.pop(get_search_service, None)
        app.dependency_overrides.pop(get_llm_client_dep, None)

    assert response.status_code == 200
    body = response.json()
    assert body["citations"] == []
    assert "couldn't find" in body["answer"].lower()


async def test_chat_returns_citations_matching_retrieved_chunks(client: AsyncClient):
    from app.core.dependencies import get_search_service, get_llm_client_dep
    from app.main import app

    token = await _register_and_login(client, "chat-citations@example.com")

    document_id = uuid.uuid4()
    chunk_id = uuid.uuid4()
    fake_results = [
        SearchResultItem(
            chunk_id=chunk_id,
            document_id=document_id,
            document_filename="report.pdf",
            chunk_index=0,
            content="The quarterly revenue grew by 12%.",
            score=0.9,
            rank=1,
        )
    ]

    fake_search_service = AsyncMock()
    fake_search_service.search = AsyncMock(return_value=fake_results)

    fake_llm = AsyncMock()
    fake_llm.generate = AsyncMock(return_value="Revenue grew by 12% [1].")

    app.dependency_overrides[get_search_service] = lambda: fake_search_service
    app.dependency_overrides[get_llm_client_dep] = lambda: fake_llm
    try:
        response = await client.post(
            "/api/v1/chat",
            json={"message": "How did revenue change?"},
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        app.dependency_overrides.pop(get_search_service, None)
        app.dependency_overrides.pop(get_llm_client_dep, None)

    assert response.status_code == 200
    body = response.json()
    assert "[1]" in body["answer"]
    assert len(body["citations"]) == 1
    assert body["citations"][0]["chunk_id"] == str(chunk_id)
    assert body["citations"][0]["document_filename"] == "report.pdf"