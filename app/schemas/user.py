"""User-related Pydantic v2 schemas (DTOs)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import RoleEnum

_PASSWORD_MIN_LENGTH = 8


def _validate_password_strength(value: str) -> str:
    if len(value) < _PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {_PASSWORD_MIN_LENGTH} characters")
    if not any(c.isupper() for c in value):
        raise ValueError("Password must contain at least one uppercase letter")
    if not any(c.isdigit() for c in value):
        raise ValueError("Password must contain at least one digit")
    return value


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)


class UserCreate(UserBase):
    """Self-registration payload — role is always USER, never client-supplied."""

    password: str = Field(min_length=_PASSWORD_MIN_LENGTH, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return _validate_password_strength(v)


class UserCreateByAdmin(UserBase):
    """Admin-initiated user creation — role is explicitly assignable."""

    password: str = Field(min_length=_PASSWORD_MIN_LENGTH, max_length=128)
    role: RoleEnum = RoleEnum.USER
    is_active: bool = True

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return _validate_password_strength(v)


class UserUpdate(BaseModel):
    """Self-service profile update — no role/is_active fields."""

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None


class UserUpdateByAdmin(BaseModel):
    """Admin-only update — can change role and active status."""

    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: EmailStr | None = None
    role: RoleEnum | None = None
    is_active: bool | None = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str = Field(min_length=_PASSWORD_MIN_LENGTH, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        return _validate_password_strength(v)


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: RoleEnum
    is_active: bool
    is_verified: bool
    created_at: datetime
    updated_at: datetime
