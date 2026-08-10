"""Chat route — retrieval-augmented generation with source citations."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.config import settings
# from app.core.dependencies import get_current_active_user, get_rag_service
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.rag.rag_service import RAGService

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    current_user: User = Depends(get_current_active_user),
    rag_service: RAGService = Depends(get_rag_service),
) -> ChatResponse:
    answer, citations = await rag_service.answer(
        query=payload.message,
        owner_id=current_user.id,
        filters=payload.filters,
        max_context_chunks=payload.max_context_chunks,
    )
    return ChatResponse(
        answer=answer, citations=citations, model=settings.GEMINI_MODEL_NAME
    )