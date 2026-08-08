"""User CRUD business logic."""

from __future__ import annotations

import uuid

from app.core.exceptions import (
    InvalidCredentialsException,
    NotFoundException,
    UserAlreadyExistsException,
)
from app.core.logging import get_logger
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.common import PaginatedResponse
from app.schemas.user import (
    PasswordChange,
    UserCreateByAdmin,
    UserUpdate,
    UserUpdateByAdmin,
)

logger = get_logger(__name__)


class UserService:
    def __init__(self, user_repository: UserRepository) -> None:
        self.user_repository = user_repository

    async def get_by_id(self, user_id: uuid.UUID) -> User:
        user = await self.user_repository.get_by_id(user_id)
        if user is None:
            raise NotFoundException("User not found")
        return user

    async def list_users(self, page: int, page_size: int) -> PaginatedResponse[User]:
        offset = (page - 1) * page_size
        items = await self.user_repository.list(offset=offset, limit=page_size)
        total = await self.user_repository.count()
        return PaginatedResponse.build(items, total, page, page_size)

    async def create_user(self, payload: UserCreateByAdmin) -> User:
        if await self.user_repository.email_exists(payload.email):
            raise UserAlreadyExistsException()

        user = User(
            email=payload.email,
            full_name=payload.full_name,
            hashed_password=hash_password(payload.password),
            role=payload.role,
            is_active=payload.is_active,
        )
        return await self.user_repository.create(user)

    async def update_self(self, user_id: uuid.UUID, payload: UserUpdate) -> User:
        user = await self.get_by_id(user_id)

        if payload.email is not None and payload.email != user.email:
            if await self.user_repository.email_exists(payload.email):
                raise UserAlreadyExistsException()
            user.email = payload.email

        if payload.full_name is not None:
            user.full_name = payload.full_name

        await self.user_repository.session.flush()
        await self.user_repository.session.refresh(user)
        return user

    async def update_by_admin(
        self, user_id: uuid.UUID, payload: UserUpdateByAdmin
    ) -> User:
        user = await self.get_by_id(user_id)

        if payload.email is not None and payload.email != user.email:
            if await self.user_repository.email_exists(payload.email):
                raise UserAlreadyExistsException()
            user.email = payload.email

        if payload.full_name is not None:
            user.full_name = payload.full_name
        if payload.role is not None:
            user.role = payload.role
        if payload.is_active is not None:
            user.is_active = payload.is_active

        await self.user_repository.session.flush()
        await self.user_repository.session.refresh(user)
        logger.info("user_updated_by_admin", extra={"user_id": str(user_id)})
        return user

    async def change_password(
        self, user_id: uuid.UUID, payload: PasswordChange
    ) -> None:
        user = await self.get_by_id(user_id)
        if not verify_password(payload.current_password, user.hashed_password):
            raise InvalidCredentialsException("Current password is incorrect")

        user.hashed_password = hash_password(payload.new_password)
        await self.user_repository.session.flush()

    async def delete_user(self, user_id: uuid.UUID) -> None:
        user = await self.get_by_id(user_id)
        await self.user_repository.delete(user)
        logger.info("user_deleted", extra={"user_id": str(user_id)})
