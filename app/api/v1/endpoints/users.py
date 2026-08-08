"""
User CRUD routes.

- `/users/me/*` — self-service, any authenticated user.
- `/users` (list/create/update-role/delete) — admin only.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import (
    get_current_active_user,
    get_user_service,
    require_admin,
)
from app.models.user import User
from app.schemas.common import MessageResponse, PaginatedResponse
from app.schemas.user import (
    PasswordChange,
    UserCreateByAdmin,
    UserRead,
    UserUpdate,
    UserUpdateByAdmin,
)
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])


# --- Self-service ---

@router.get("/me", response_model=UserRead)
async def get_my_profile(
    current_user: User = Depends(get_current_active_user),
) -> User:
    return current_user


@router.patch("/me", response_model=UserRead)
async def update_my_profile(
    payload: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    user_service: UserService = Depends(get_user_service),
) -> User:
    return await user_service.update_self(current_user.id, payload)


@router.post("/me/change-password", response_model=MessageResponse)
async def change_my_password(
    payload: PasswordChange,
    current_user: User = Depends(get_current_active_user),
    user_service: UserService = Depends(get_user_service),
) -> MessageResponse:
    await user_service.change_password(current_user.id, payload)
    return MessageResponse(message="Password updated successfully")


# --- Admin-only ---

@router.get("", response_model=PaginatedResponse[UserRead], dependencies=[Depends(require_admin)])
async def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user_service: UserService = Depends(get_user_service),
) -> PaginatedResponse[UserRead]:
    return await user_service.list_users(page, page_size)


@router.get("/{user_id}", response_model=UserRead, dependencies=[Depends(require_admin)])
async def get_user(
    user_id: uuid.UUID,
    user_service: UserService = Depends(get_user_service),
) -> User:
    return await user_service.get_by_id(user_id)


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_user(
    payload: UserCreateByAdmin,
    user_service: UserService = Depends(get_user_service),
) -> User:
    return await user_service.create_user(payload)


@router.patch("/{user_id}", response_model=UserRead, dependencies=[Depends(require_admin)])
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdateByAdmin,
    user_service: UserService = Depends(get_user_service),
) -> User:
    return await user_service.update_by_admin(user_id, payload)


from fastapi import Response

@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(require_admin)],
)
async def delete_user(
    user_id: uuid.UUID,
    user_service: UserService = Depends(get_user_service),
):
    await user_service.delete_user(user_id)
