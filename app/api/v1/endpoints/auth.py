"""Auth routes: register, login, refresh, logout."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.core.dependencies import get_auth_service
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterResponse, TokenPair
from app.schemas.common import MessageResponse
from app.schemas.user import UserCreate
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: UserCreate,
    auth_service: AuthService = Depends(get_auth_service),
) -> RegisterResponse:
    user = await auth_service.register(payload)
    return RegisterResponse(id=user.id, email=user.email)


@router.post("/login", response_model=TokenPair)
async def login(
    payload: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenPair:
    return await auth_service.login(payload.email, payload.password)


@router.post("/refresh", response_model=TokenPair)
async def refresh(
    payload: RefreshRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenPair:
    return await auth_service.refresh(payload.refresh_token)


@router.post("/logout", response_model=MessageResponse)
async def logout(
    payload: RefreshRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> MessageResponse:
    await auth_service.logout(payload.refresh_token)
    return MessageResponse(message="Logged out successfully")
