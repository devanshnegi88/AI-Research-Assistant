"""
Chat service — the top-level orchestrator for a single `/chat` turn.

Flow: resolve/create conversation -> load history -> build memory context
(recent verbatim + rolling summary) -> resummarize if needed -> RAG answer
-> persist both the user and assistant messages -> return response.

This is the only place that touches both `ConversationService` and
`RAGService` — everything downstream of it stays single-purpose.
"""

from __future__ import annotations

import uuid

from app.core.logging import get_logger
from app.models.conversation import Conversation, Message
from app.models.enums import MessageRole
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.chat import Citation
from app.schemas.search import SearchFilters
from app.services.chat.memory_manager import MemoryManager, estimate_tokens
from app.services.conversation.conversation_service import ConversationService
from app.services.rag.rag_service import RAGService

logger = get_logger(__name__)


class ChatService:
    def __init__(
        self,
        conversation_service: ConversationService,
        conversation_repository: ConversationRepository,
        message_repository: MessageRepository,
        memory_manager: MemoryManager,
        rag_service: RAGService,
    ) -> None:
        self.conversation_service = conversation_service
        self.conversation_repository = conversation_repository
        self.message_repository = message_repository
        self.memory_manager = memory_manager
        self.rag_service = rag_service

    async def send_message(
        self,
        owner_id: uuid.UUID,
        message: str,
        conversation_id: uuid.UUID | None,
        filters: SearchFilters | None = None,
        max_context_chunks: int | None = None,
    ) -> tuple[Conversation, Message, list[Citation]]:
        conversation = await self.conversation_service.get_or_create(
            owner_id, conversation_id
        )
        history = await self.message_repository.list_for_conversation(conversation.id)

        conversation = await self._maybe_resummarize(conversation, history)
        context = await self.memory_manager.build_context(conversation, history)

        answer_text, citations = await self.rag_service.answer(
            query=message,
            owner_id=owner_id,
            filters=filters,
            max_context_chunks=max_context_chunks,
            history_messages=context.recent_messages,
            history_summary=context.summary,
        )

        user_message, assistant_message = await self._persist_turn(
            conversation, message, answer_text, citations
        )

        logger.info(
            "chat_turn_completed",
            extra={
                "conversation_id": str(conversation.id),
                "turn_index": assistant_message.turn_index,
            },
        )
        return conversation, assistant_message, citations

    async def _maybe_resummarize(
        self, conversation: Conversation, history: list[Message]
    ) -> Conversation:
        if not history or not self.memory_manager.needs_resummarization(
            conversation, history
        ):
            return conversation

        new_summary, new_cutoff = await self.memory_manager.resummarize(
            conversation, history
        )
        conversation.summary = new_summary
        conversation.summarized_up_to_index = new_cutoff
        await self.conversation_repository.session.flush()
        logger.info(
            "conversation_resummarized",
            extra={
                "conversation_id": str(conversation.id),
                "summarized_up_to_index": new_cutoff,
            },
        )
        return conversation

    async def _persist_turn(
        self,
        conversation: Conversation,
        user_text: str,
        answer_text: str,
        citations: list[Citation],
    ) -> tuple[Message, Message]:
        next_index = await self.message_repository.get_next_turn_index(conversation.id)

        user_message = Message(
            conversation_id=conversation.id,
            turn_index=next_index,
            role=MessageRole.USER,
            content=user_text,
            token_estimate=estimate_tokens(user_text),
        )
        assistant_message = Message(
            conversation_id=conversation.id,
            turn_index=next_index + 1,
            role=MessageRole.ASSISTANT,
            content=answer_text,
            citations=[c.model_dump(mode="json") for c in citations] or None,
            token_estimate=estimate_tokens(answer_text),
        )

        self.message_repository.session.add_all([user_message, assistant_message])
        conversation.message_count += 2

        # First turn — derive a short title from the opening message so
        # conversations aren't all just "New conversation" in a list view.
        if conversation.message_count == 2:
            conversation.title = user_text[:80]

        await self.message_repository.session.flush()
        await self.message_repository.session.refresh(user_message)
        await self.message_repository.session.refresh(assistant_message)

        return user_message, assistant_message