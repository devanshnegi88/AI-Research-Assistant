"""
Tests for /documents/* endpoints.

Document processing runs synchronously inside the upload request (Celery
was removed along with Redis), so these tests exercise the full upload
API contract — validation, dedup, ownership scoping — without needing a
running worker or broker.
"""

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


async def test_upload_txt_document(client: AsyncClient):
    token = await _register_and_login(client, "upload@example.com")
    response = await client.post(
        "/api/v1/documents/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["original_filename"] == "notes.txt"
    assert body["status"] == "completed"


async def test_upload_requires_auth(client: AsyncClient):
    response = await client.post(
        "/api/v1/documents/upload",
        files={"file": ("notes.txt", b"hello world", "text/plain")},
    )
    assert response.status_code == 401


async def test_upload_rejects_unsupported_extension(client: AsyncClient):
    token = await _register_and_login(client, "badext@example.com")
    response = await client.post(
        "/api/v1/documents/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("archive.zip", b"PK\x03\x04", "application/zip")},
    )
    assert response.status_code == 400
    assert response.json()["error_code"] == "bad_request"


async def test_upload_rejects_empty_file(client: AsyncClient):
    token = await _register_and_login(client, "empty@example.com")
    response = await client.post(
        "/api/v1/documents/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("empty.txt", b"", "text/plain")},
    )
    assert response.status_code == 400


async def test_duplicate_upload_returns_existing_document(client: AsyncClient):
    token = await _register_and_login(client, "dupe@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    content = b"identical content for dedup test"

    first = await client.post(
        "/api/v1/documents/upload",
        headers=headers,
        files={"file": ("a.txt", content, "text/plain")},
    )
    second = await client.post(
        "/api/v1/documents/upload",
        headers=headers,
        files={"file": ("b.txt", content, "text/plain")},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


async def test_list_documents(client: AsyncClient):
    token = await _register_and_login(client, "list@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    await client.post(
        "/api/v1/documents/upload",
        headers=headers,
        files={"file": ("a.txt", b"content a", "text/plain")},
    )

    response = await client.get("/api/v1/documents", headers=headers)
    assert response.status_code == 200
    assert response.json()["total"] >= 1


async def test_get_document_status(client: AsyncClient):
    token = await _register_and_login(client, "status@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    upload = await client.post(
        "/api/v1/documents/upload",
        headers=headers,
        files={"file": ("a.txt", b"content", "text/plain")},
    )
    document_id = upload.json()["id"]

    response = await client.get(
        f"/api/v1/documents/{document_id}/status", headers=headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


async def test_cannot_access_other_users_document(client: AsyncClient):
    token_a = await _register_and_login(client, "owner@example.com")
    token_b = await _register_and_login(client, "intruder@example.com")

    upload = await client.post(
        "/api/v1/documents/upload",
        headers={"Authorization": f"Bearer {token_a}"},
        files={"file": ("private.txt", b"secret", "text/plain")},
    )
    document_id = upload.json()["id"]

    response = await client.get(
        f"/api/v1/documents/{document_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert response.status_code == 404


async def test_delete_document(client: AsyncClient):
    token = await _register_and_login(client, "delete@example.com")
    headers = {"Authorization": f"Bearer {token}"}
    upload = await client.post(
        "/api/v1/documents/upload",
        headers=headers,
        files={"file": ("todelete.txt", b"bye", "text/plain")},
    )
    document_id = upload.json()["id"]

    delete_response = await client.delete(
        f"/api/v1/documents/{document_id}", headers=headers
    )
    assert delete_response.status_code == 204

    get_response = await client.get(
        f"/api/v1/documents/{document_id}", headers=headers
    )
    assert get_response.status_code == 404
