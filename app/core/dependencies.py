"""
Shared FastAPI dependencies: DB/Redis-backed repository and service
providers, current-user extraction from JWT, and role-based access guards.
"""

from __future__ import annotations

import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ForbiddenException, InvalidTokenException
from app.core.security import decode_token
from app.db.session import get_db
from app.models.enums import RoleEnum
from app.models.user import User
from app.repositories.document_repository import DocumentRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.document.document_service import DocumentService
from app.services.user_service import UserService
from app.storage.base import StorageBackend
from app.storage.local_storage import get_storage_backend


security = HTTPBearer(auto_error=True)


# --- Repositories ---

def get_user_repository(db: AsyncSession = Depends(get_db)) -> UserRepository:
    return UserRepository(db)


def get_document_repository(db: AsyncSession = Depends(get_db)) -> DocumentRepository:
    return DocumentRepository(db)


def get_storage() -> StorageBackend:
    return get_storage_backend()


# --- Services ---

def get_auth_service(
    user_repository: UserRepository = Depends(get_user_repository),
) -> AuthService:
    return AuthService(user_repository)


def get_user_service(
    user_repository: UserRepository = Depends(get_user_repository),
) -> UserService:
    return UserService(user_repository)


def get_document_service(
    document_repository: DocumentRepository = Depends(get_document_repository),
    storage: StorageBackend = Depends(get_storage),
) -> DocumentService:
    return DocumentService(document_repository, storage)


# --- Current user / RBAC ---

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_repository: UserRepository = Depends(get_user_repository),
) -> User:
    token = credentials.credentials

    payload = decode_token(token)

    if payload.get("type") != "access":
        raise InvalidTokenException("Not an access token")

    user = await user_repository.get_by_id(uuid.UUID(payload["sub"]))

    if user is None:
        raise InvalidTokenException("User not found")

    if not user.is_active:
        raise InvalidTokenException("User no longer active")

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_active:
        raise ForbiddenException("Account is deactivated")
    return current_user


def require_role(*allowed_roles: RoleEnum):
    """Dependency factory — e.g. `Depends(require_role(RoleEnum.ADMIN))`."""

    async def _guard(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        if current_user.role not in allowed_roles:
            raise ForbiddenException(
                f"Requires one of roles: {[r.value for r in allowed_roles]}"
            )
        return current_user

    return _guard


require_admin = require_role(RoleEnum.ADMIN)
