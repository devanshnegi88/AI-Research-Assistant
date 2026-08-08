"""
Auth business logic: registration, login, token refresh, logout.

NOTE: Redis was previously used to track refresh-token `jti` for revocation
and reuse-detection. Redis has been removed, so refresh/logout are now
stateless JWT operations.
"""

from __future__ import annotations

import uuid

from app.core.exceptions import (
    InvalidCredentialsException,
    InvalidTokenException,
    UserAlreadyExistsException,
)
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenPair
from app.schemas.user import UserCreate

logger = get_logger(__name__)


class AuthService:
    def __init__(self, user_repository: UserRepository) -> None:
        self.user_repository = user_repository

    async def register(self, payload: UserCreate) -> User:
        if await self.user_repository.email_exists(payload.email):
            raise UserAlreadyExistsException()

        user = User(
            email=payload.email,
            full_name=payload.full_name,
            hashed_password=hash_password(payload.password),
        )
        user = await self.user_repository.create(user)
        logger.info("user_registered", extra={"user_id": str(user.id)})
        return user

    async def login(self, email: str, password: str) -> TokenPair:
        user = await self.user_repository.get_by_email(email)
        if user is None or not verify_password(password, user.hashed_password):
            raise InvalidCredentialsException()
        if not user.is_active:
            raise InvalidCredentialsException("Account is deactivated")

        return self._issue_token_pair(user)

    async def refresh(self, refresh_token: str):
        payload = self._decode_refresh_or_raise(refresh_token)
        user_id = payload["sub"]

        user = await self.user_repository.get_by_id(uuid.UUID(user_id))

        if user is None:
            raise InvalidTokenException("Invalid refresh token")

        return self._issue_token_pair(user)

    async def logout(self, refresh_token: str) -> None:
        # Redis removed — logout is a best-effort no-op now. The token simply
        # expires naturally per its JWT expiry.
        try:
            self._decode_refresh_or_raise(refresh_token)
        except Exception:  # noqa: BLE001 — logout is best-effort
            return

    def _decode_refresh_or_raise(self, refresh_token: str) -> dict:
        payload = decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise InvalidTokenException("Not a refresh token")
        return payload

    def _issue_token_pair(self, user: User) -> TokenPair:
        access_token = create_access_token(str(user.id), user.role.value)
        refresh_token = create_refresh_token(str(user.id), user.role.value)

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
        )
