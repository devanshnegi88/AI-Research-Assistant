"""Tests for /conversations/* endpoints — session CRUD and ownership isolation."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

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


async def test_create_conversation(client: AsyncClient):
    token = await _register_and_login(client, "conv-create@example.com")
    response = await client.post(
        "/api/v1/conversations",
        json={"title": "My research"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "My research"
    assert body["message_count"] == 0


async def test_create_conversation_without_body_uses_default_title(client: AsyncClient):
    token = await _register_and_login(client, "conv-default@example.com")
    response = await client.post(
        "/api/v1/conversations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    assert response.json()["title"] == "New conversation"


async def test_conversations_require_auth(client: AsyncClient):
    response = await client.get("/api/v1/conversations")
    assert response.status_code == 401


async def test_list_conversations(client: AsyncClient):
    token = await _register_and_login(client, "conv-list@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    await client.post("/api/v1/conversations", headers=headers)

    response = await client.get("/api/v1/conversations", headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] >= 1


async def test_get_conversation_includes_empty_message_list(client: AsyncClient):
    token = await _register_and_login(client, "conv-get@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    created = await client.post("/api/v1/conversations", headers=headers)
    conversation_id = created.json()["id"]

    response = await client.get(
        f"/api/v1/conversations/{conversation_id}", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["messages"] == []


async def test_get_nonexistent_conversation_returns_404(client: AsyncClient):
    import uuid

    token = await _register_and_login(client, "conv-404@example.com")
    response = await client.get(
        f"/api/v1/conversations/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


async def test_cannot_access_other_users_conversation(client: AsyncClient):
    token_a = await _register_and_login(client, "conv-owner@example.com")
    token_b = await _register_and_login(client, "conv-intruder@example.com")

    created = await client.post(
        "/api/v1/conversations",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    conversation_id = created.json()["id"]

    response = await client.get(
        f"/api/v1/conversations/{conversation_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert response.status_code == 404


async def test_delete_conversation(client: AsyncClient):
    token = await _register_and_login(client, "conv-delete@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    created = await client.post("/api/v1/conversations", headers=headers)
    conversation_id = created.json()["id"]

    delete_response = await client.delete(
        f"/api/v1/conversations/{conversation_id}", headers=headers
    )
    assert delete_response.status_code == 204

    get_response = await client.get(
        f"/api/v1/conversations/{conversation_id}", headers=headers
    )
    assert get_response.status_code == 404