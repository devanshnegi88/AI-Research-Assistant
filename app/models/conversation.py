"""Conversation-related Pydantic v2 schemas (DTOs)."""

from __future__ import annotations

import uuid
from datetime import datetime

# pyrefly: ignore [missing-import]
from pydantic import BaseModel, ConfigDict, Field

# pyrefly: ignore [missing-import]
from app.models.enums import MessageRole


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    message_count: int
    created_at: datetime
    updated_at: datetime


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    turn_index: int
    role: MessageRole
    content: str
    citations: list[dict] | None
    created_at: datetime


class ConversationDetailRead(ConversationRead):
    """Includes full message history — only returned from the single-conversation GET."""

    messages: list[MessageRead]