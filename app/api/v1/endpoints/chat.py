"""
Chat route — multi-turn conversation with retrieval-augmented generation
and source citations.

Delegates to ChatService, which owns conversation resolution, memory
(recent history + rolling summary), and persistence — this endpoint is
just the HTTP boundary.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.config import settings
from app.core.dependencies import get_chat_service, get_current_active_user
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat.chat_service import ChatService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    current_user: User = Depends(get_current_active_user),
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    conversation, assistant_message, citations = await chat_service.send_message(
        owner_id=current_user.id,
        message=payload.message,
        conversation_id=payload.conversation_id,
        filters=payload.filters,
        max_context_chunks=payload.max_context_chunks,
    )
    return ChatResponse(
        conversation_id=conversation.id,
        message_id=assistant_message.id,
        answer=assistant_message.content,
        citations=citations,
        model=settings.GEMINI_MODEL_NAME,
    )