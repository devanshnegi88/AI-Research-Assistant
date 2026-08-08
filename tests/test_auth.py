"""Tests for /auth/* endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


async def test_register_success(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@example.com",
            "full_name": "New User",
            "password": "StrongPass1",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "newuser@example.com"


async def test_register_duplicate_email_fails(client: AsyncClient):
    payload = {
        "email": "dupe@example.com",
        "full_name": "Dupe User",
        "password": "StrongPass1",
    }
    first = await client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/v1/auth/register", json=payload)
    assert second.status_code == 409
    assert second.json()["error_code"] == "user_already_exists"


async def test_register_weak_password_fails(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "weak@example.com",
            "full_name": "Weak User",
            "password": "weak",
        },
    )
    assert response.status_code == 422


async def test_login_success(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "login@example.com",
            "full_name": "Login User",
            "password": "StrongPass1",
        },
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "login@example.com", "password": "StrongPass1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body


async def test_login_wrong_password_fails(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "wrongpass@example.com",
            "full_name": "User",
            "password": "StrongPass1",
        },
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "wrongpass@example.com", "password": "WrongPass1"},
    )
    assert response.status_code == 401
    assert response.json()["error_code"] == "invalid_credentials"


async def test_refresh_token_flow(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "refresh@example.com",
            "full_name": "Refresh User",
            "password": "StrongPass1",
        },
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "refresh@example.com", "password": "StrongPass1"},
    )
    refresh_token = login_resp.json()["refresh_token"]

    refresh_resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert refresh_resp.status_code == 200
    assert "access_token" in refresh_resp.json()


async def test_refresh_token_reuse_rejected(client: AsyncClient):
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "reuse@example.com",
            "full_name": "Reuse User",
            "password": "StrongPass1",
        },
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "reuse@example.com", "password": "StrongPass1"},
    )
    refresh_token = login_resp.json()["refresh_token"]

    first = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert first.status_code == 200

    second = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert second.status_code == 401
