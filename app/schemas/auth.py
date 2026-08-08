"""Auth-related Pydantic v2 schemas (DTOs)."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr

from app.models.enums import RoleEnum


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPayload(BaseModel):
    """Decoded JWT claims."""

    sub: str  # user id
    role: RoleEnum
    exp: int
    iat: int
    jti: str
    type: str  # "access" | "refresh"


class RegisterResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    message: str = "Registration successful"
