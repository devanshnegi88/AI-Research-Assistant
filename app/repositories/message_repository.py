"""Message data-access layer."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.models.conversation import Message
from app.repositories.base import BaseRepository


class MessageRepository(BaseRepository[Message]):
    model = Message

    async def list_for_conversation(self, conversation_id: uuid.UUID) -> list[Message]:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.turn_index)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_tail(
        self, conversation_id: uuid.UUID, after_turn_index: int
    ) -> list[Message]:
        """Messages after `after_turn_index` — the portion not yet folded
        into the conversation's rolling summary."""
        stmt = (
            select(Message)
            .where(
                Message.conversation_id == conversation_id,
                Message.turn_index > after_turn_index,
            )
            .order_by(Message.turn_index)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_next_turn_index(self, conversation_id: uuid.UUID) -> int:
        stmt = select(Message.turn_index).where(
            Message.conversation_id == conversation_id
        ).order_by(Message.turn_index.desc()).limit(1)
        result = await self.session.execute(stmt)
        last = result.scalar_one_or_none()
        return (last + 1) if last is not None else 0