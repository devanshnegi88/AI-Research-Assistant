"""Conversation (chat session) business logic — CRUD only.

Message persistence and history assembly live in `chat_service.py` /
`memory_manager.py`; this service is deliberately just session lifecycle.
"""

from __future__ import annotations

import uuid

from app.core.exceptions import NotFoundException
from app.models.conversation import Conversation
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.common import PaginatedResponse
from app.schemas.conversation import ConversationCreate


class ConversationService:
    def __init__(
        self,
        conversation_repository: ConversationRepository,
        message_repository: MessageRepository,
    ) -> None:
        self.conversation_repository = conversation_repository
        self.message_repository = message_repository

    async def create(
        self, owner_id: uuid.UUID, payload: ConversationCreate | None = None
    ) -> Conversation:
        title = (payload.title if payload else None) or "New conversation"
        conversation = Conversation(owner_id=owner_id, title=title)
        return await self.conversation_repository.create(conversation)

    async def get_for_owner(
        self, conversation_id: uuid.UUID, owner_id: uuid.UUID
    ) -> Conversation:
        conversation = await self.conversation_repository.get_by_id_for_owner(
            conversation_id, owner_id
        )
        if conversation is None:
            raise NotFoundException("Conversation not found")
        return conversation

    async def get_with_history(
        self, conversation_id: uuid.UUID, owner_id: uuid.UUID
    ) -> tuple[Conversation, list]:
        conversation = await self.get_for_owner(conversation_id, owner_id)
        messages = await self.message_repository.list_for_conversation(conversation_id)
        return conversation, messages

    async def list_for_owner(
        self, owner_id: uuid.UUID, page: int, page_size: int
    ) -> PaginatedResponse[Conversation]:
        offset = (page - 1) * page_size
        items = await self.conversation_repository.list_for_owner(owner_id, offset, page_size)
        total = await self.conversation_repository.count_for_owner(owner_id)
        return PaginatedResponse.build(items, total, page, page_size)

    async def delete_for_owner(self, conversation_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        conversation = await self.get_for_owner(conversation_id, owner_id)
        await self.conversation_repository.delete(conversation)

    async def get_or_create(
        self, owner_id: uuid.UUID, conversation_id: uuid.UUID | None
    ) -> Conversation:
        """Used by chat_service — resolves an existing session or starts a
        new one, so `/chat` callers can omit `conversation_id` entirely."""
        if conversation_id is not None:
            return await self.get_for_owner(conversation_id, owner_id)
        return await self.create(owner_id)