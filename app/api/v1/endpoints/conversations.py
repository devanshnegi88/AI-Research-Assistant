"""
Conversation (chat session) routes.

`/chat` (in chat.py) is where messages actually get sent — these routes
are for managing and browsing sessions: creating one up front, listing
past conversations, viewing full history, deleting a conversation.
"""

from __future__ import annotations

import uuid

# pyrefly: ignore [missing-import]
from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import get_conversation_service, get_current_active_user
from app.models.user import User
from app.schemas.common import PaginatedResponse
# pyrefly: ignore [missing-import]
from app.schemas.conversation import (
    ConversationCreate,
    ConversationDetailRead,
    ConversationRead,
)
# pyrefly: ignore [missing-import]
from app.services.conversation.conversation_service import ConversationService

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.post("", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate | None = None,
    current_user: User = Depends(get_current_active_user),
    conversation_service: ConversationService = Depends(get_conversation_service),
):
    return await conversation_service.create(current_user.id, payload)


@router.get("", response_model=PaginatedResponse[ConversationRead])
async def list_conversations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_active_user),
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> PaginatedResponse[ConversationRead]:
    return await conversation_service.list_for_owner(current_user.id, page, page_size)


@router.get("/{conversation_id}", response_model=ConversationDetailRead)
async def get_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    conversation_service: ConversationService = Depends(get_conversation_service),
):
    conversation, messages = await conversation_service.get_with_history(
        conversation_id, current_user.id
    )
    return ConversationDetailRead(
        id=conversation.id,
        title=conversation.title,
        message_count=conversation.message_count,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
        messages=messages,
    )


@router.delete(
    "/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,  # see documents.py/users.py — required alongside
    # `from __future__ import annotations` or FastAPI misreads `-> None`
    # as "has a response body" and asserts against status_code=204.
)
async def delete_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_active_user),
    conversation_service: ConversationService = Depends(get_conversation_service),
) -> None:
    await conversation_service.delete_for_owner(conversation_id, current_user.id)