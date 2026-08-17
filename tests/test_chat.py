"""
Tests for `/chat` — retrieval-augmented generation, now routed through
ChatService (conversation resolution + memory + RAG + persistence).

The LLM client and search service are mocked at the DI layer throughout;
Postgres is real (see conftest.py), so conversation/message persistence
and multi-turn history are exercised for real, not mocked.
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


# --- Phase 4: multi-turn conversation behavior ---


async def test_chat_without_conversation_id_creates_new_conversation(
    client: AsyncClient,
):
    from app.core.dependencies import get_llm_client_dep, get_search_service
    from app.main import app

    token = await _register_and_login(client, "chat-newconv@example.com")

    app.dependency_overrides[get_search_service] = lambda: AsyncMock(
        search=AsyncMock(return_value=[])
    )
    app.dependency_overrides[get_llm_client_dep] = lambda: AsyncMock(
        generate=AsyncMock(return_value="Hi there!")
    )
    try:
        response = await client.post(
            "/api/v1/chat",
            json={"message": "Hello"},
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        app.dependency_overrides.pop(get_search_service, None)
        app.dependency_overrides.pop(get_llm_client_dep, None)

    assert response.status_code == 200
    body = response.json()
    assert body["conversation_id"]
    assert body["message_id"]


async def test_second_message_reuses_conversation_and_persists_history(
    client: AsyncClient,
):
    from app.core.dependencies import get_llm_client_dep, get_search_service
    from app.main import app

    token = await _register_and_login(client, "chat-multiturn@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    app.dependency_overrides[get_search_service] = lambda: AsyncMock(
        search=AsyncMock(return_value=[])
    )
    app.dependency_overrides[get_llm_client_dep] = lambda: AsyncMock(
        generate=AsyncMock(return_value="OK")
    )
    try:
        first = await client.post(
            "/api/v1/chat", json={"message": "My name is Alex."}, headers=headers
        )
        conversation_id = first.json()["conversation_id"]

        second = await client.post(
            "/api/v1/chat",
            json={"message": "What's my name?", "conversation_id": conversation_id},
            headers=headers,
        )
    finally:
        app.dependency_overrides.pop(get_search_service, None)
        app.dependency_overrides.pop(get_llm_client_dep, None)

    assert second.status_code == 200
    assert second.json()["conversation_id"] == conversation_id

    history = await client.get(f"/api/v1/conversations/{conversation_id}", headers=headers)
    messages = history.json()["messages"]
    assert len(messages) == 4  # 2 user + 2 assistant
    assert messages[0]["content"] == "My name is Alex."
    assert messages[2]["content"] == "What's my name?"


async def test_second_message_passes_history_to_rag_service(client: AsyncClient):
    """Verifies the actual memory wiring — not just that persistence
    happened, but that the prior turn was handed to RAGService.answer()
    for the second message.

    Note: ChatService depends on both get_rag_service AND
    get_memory_manager, and each independently resolves get_llm_client_dep
    — overriding only one leaves the other constructing a real
    GeminiLLMClient, which fails fast without GEMINI_API_KEY.
    """
    from app.core.dependencies import get_llm_client_dep, get_rag_service
    from app.main import app

    token = await _register_and_login(client, "chat-memorywiring@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    fake_rag = AsyncMock()
    fake_rag.answer = AsyncMock(return_value=("some answer", []))
    app.dependency_overrides[get_rag_service] = lambda: fake_rag
    app.dependency_overrides[get_llm_client_dep] = lambda: AsyncMock()
    try:
        first = await client.post(
            "/api/v1/chat", json={"message": "First message"}, headers=headers
        )
        conversation_id = first.json()["conversation_id"]

        await client.post(
            "/api/v1/chat",
            json={"message": "Second message", "conversation_id": conversation_id},
            headers=headers,
        )
    finally:
        app.dependency_overrides.pop(get_rag_service, None)
        app.dependency_overrides.pop(get_llm_client_dep, None)

    assert fake_rag.answer.await_count == 2
    second_call_kwargs = fake_rag.answer.await_args_list[1].kwargs
    history_messages = second_call_kwargs["history_messages"]
    assert any(m.content == "First message" for m in history_messages)


async def test_cannot_continue_other_users_conversation(client: AsyncClient):
    from app.core.dependencies import get_llm_client_dep, get_search_service
    from app.main import app

    token_a = await _register_and_login(client, "chat-owner@example.com")
    token_b = await _register_and_login(client, "chat-intruder@example.com")

    app.dependency_overrides[get_search_service] = lambda: AsyncMock(
        search=AsyncMock(return_value=[])
    )
    app.dependency_overrides[get_llm_client_dep] = lambda: AsyncMock(
        generate=AsyncMock(return_value="OK")
    )
    try:
        first = await client.post(
            "/api/v1/chat",
            json={"message": "private"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        conversation_id = first.json()["conversation_id"]

        intruding = await client.post(
            "/api/v1/chat",
            json={"message": "trying to continue", "conversation_id": conversation_id},
            headers={"Authorization": f"Bearer {token_b}"},
        )
    finally:
        app.dependency_overrides.pop(get_search_service, None)
        app.dependency_overrides.pop(get_llm_client_dep, None)

    assert intruding.status_code == 404


# --- Phase 5: planner-driven routing, exercised through the real endpoint ---
# (unit-level coverage of every routing branch and fallback path lives in
# tests/test_planner_agent.py — these confirm the /chat HTTP contract and
# that chitchat genuinely skips retrieval, not just that the agent decides
# it should.)


async def test_chat_response_includes_intent_and_subtask_queries(client: AsyncClient):
    from app.core.dependencies import get_llm_client_dep, get_search_service
    from app.main import app

    token = await _register_and_login(client, "chat-intentfield@example.com")

    app.dependency_overrides[get_search_service] = lambda: AsyncMock(
        search=AsyncMock(return_value=[])
    )
    app.dependency_overrides[get_llm_client_dep] = lambda: AsyncMock(
        generate=AsyncMock(return_value="some plain text response")
    )
    try:
        response = await client.post(
            "/api/v1/chat",
            json={"message": "What does the report say?"},
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        app.dependency_overrides.pop(get_search_service, None)
        app.dependency_overrides.pop(get_llm_client_dep, None)

    assert response.status_code == 200
    body = response.json()
    assert "intent" in body
    assert "subtask_queries" in body
    # Non-JSON mock output forces the planner's documented fallback path —
    # this IS the safety behavior under test, not an incidental detail.
    assert body["intent"] == "document_question"
    assert body["subtask_queries"] == ["What does the report say?"]


async def test_chitchat_intent_skips_retrieval_entirely(client: AsyncClient):
    import json as jsonlib

    from app.core.dependencies import get_llm_client_dep, get_search_service
    from app.main import app

    token = await _register_and_login(client, "chat-chitchat@example.com")

    fake_search_service = AsyncMock()
    fake_search_service.search = AsyncMock(return_value=[])

    fake_llm = AsyncMock()
    fake_llm.generate = AsyncMock(
        side_effect=[
            jsonlib.dumps({"intent": "chitchat"}),  # classify_intent
            "Hi there! I can help you search your documents.",  # generate_direct_response
        ]
    )

    app.dependency_overrides[get_search_service] = lambda: fake_search_service
    app.dependency_overrides[get_llm_client_dep] = lambda: fake_llm
    try:
        response = await client.post(
            "/api/v1/chat",
            json={"message": "hello!"},
            headers={"Authorization": f"Bearer {token}"},
        )
    finally:
        app.dependency_overrides.pop(get_search_service, None)
        app.dependency_overrides.pop(get_llm_client_dep, None)

    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "chitchat"
    assert body["subtask_queries"] == []
    assert body["citations"] == []
    assert body["answer"] == "Hi there! I can help you search your documents."

    # The real assertion: retrieval was never attempted for a chitchat turn.
    fake_search_service.search.assert_not_awaited()