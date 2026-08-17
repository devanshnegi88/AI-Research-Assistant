"""Conversation data-access layer."""

from __future__ import annotations

import uuid

# pyrefly: ignore [missing-import]
from sqlalchemy import func, select

from app.models.conversation import Conversation
from app.repositories.base import BaseRepository


class ConversationRepository(BaseRepository[Conversation]):
    model = Conversation

    async def get_by_id_for_owner(
        self, conversation_id: uuid.UUID, owner_id: uuid.UUID
    ) -> Conversation | None:
        stmt = select(Conversation).where(
            Conversation.id == conversation_id, Conversation.owner_id == owner_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_owner(
        self, owner_id: uuid.UUID, offset: int = 0, limit: int = 20
    ) -> list[Conversation]:
        stmt = (
            select(Conversation)
            .where(Conversation.owner_id == owner_id)
            .order_by(Conversation.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_for_owner(self, owner_id: uuid.UUID) -> int:
        stmt = select(func.count()).select_from(Conversation).where(
            Conversation.owner_id == owner_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()