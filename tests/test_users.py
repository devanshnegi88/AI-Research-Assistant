"""Tests for /users/* endpoints — self-service and RBAC-gated admin routes."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.user import User

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


async def _login_admin(client: AsyncClient, admin_user: User) -> str:
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": admin_user.email, "password": "AdminPass1"},
    )
    return login.json()["access_token"]


async def test_get_my_profile(client: AsyncClient):
    token = await _register_and_login(client, "me@example.com")
    response = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == "me@example.com"


async def test_get_my_profile_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401


async def test_update_my_profile(client: AsyncClient):
    token = await _register_and_login(client, "update@example.com")
    response = await client.patch(
        "/api/v1/users/me",
        json={"full_name": "Updated Name"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "Updated Name"


async def test_regular_user_cannot_list_users(client: AsyncClient):
    token = await _register_and_login(client, "regular@example.com")
    response = await client.get(
        "/api/v1/users", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403
    assert response.json()["error_code"] == "forbidden"


async def test_admin_can_list_users(client: AsyncClient, admin_user: User):
    token = await _login_admin(client, admin_user)
    response = await client.get(
        "/api/v1/users", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert "items" in response.json()


async def test_admin_can_create_user_with_role(client: AsyncClient, admin_user: User):
    token = await _login_admin(client, admin_user)
    response = await client.post(
        "/api/v1/users",
        json={
            "email": "created@example.com",
            "full_name": "Created User",
            "password": "StrongPass1",
            "role": "admin",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    assert response.json()["role"] == "admin"


async def test_regular_user_cannot_delete_user(client: AsyncClient):
    token = await _register_and_login(client, "victim@example.com")
    me = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}
    )
    user_id = me.json()["id"]

    response = await client.delete(
        f"/api/v1/users/{user_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


async def test_change_password_with_wrong_current_fails(client: AsyncClient):
    token = await _register_and_login(client, "pwchange@example.com")
    response = await client.post(
        "/api/v1/users/me/change-password",
        json={"current_password": "WrongPass1", "new_password": "NewPass123"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 401
