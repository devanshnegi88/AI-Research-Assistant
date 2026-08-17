"""Search-related Pydantic DTOs used across the retrieval and chat flows."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import DocumentType


class SearchFilters(BaseModel):
    """Optional filters applied during retrieval."""

    document_type: DocumentType | None = None
    document_ids: list[uuid.UUID] | None = None
    filename_contains: str | None = None


class SearchQuery(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=5, ge=1, le=25)
    filters: SearchFilters | None = None


class SearchResultItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_filename: str
    chunk_index: int
    content: str
    score: float
    rank: int


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResultItem] = Field(default_factory=list)
    total_results: int