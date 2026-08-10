"""
Vector store interface.

Phase 3 ships a Qdrant implementation (`qdrant_store.py`). Kept generic so
a different vector DB can be swapped in later without touching the
retriever, search service, or RAG service.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class VectorRecord:
    """One embedded chunk to upsert."""

    id: uuid.UUID
    vector: list[float]
    payload: dict = field(default_factory=dict)


@dataclass
class VectorSearchResult:
    id: uuid.UUID
    score: float
    payload: dict = field(default_factory=dict)


class VectorStore(ABC):
    @abstractmethod
    async def upsert(self, records: list[VectorRecord]) -> None:
        """Insert or replace vectors by id."""

    @abstractmethod
    async def search(
        self,
        query_vector: list[float],
        top_k: int,
        filters: dict | None = None,
    ) -> list[VectorSearchResult]:
        """ANN search, optionally filtered on payload fields."""

    @abstractmethod
    async def delete(self, ids: list[uuid.UUID]) -> None:
        """Remove vectors by id — no-op for ids that don't exist."""

    @abstractmethod
    async def delete_by_filter(self, filters: dict) -> None:
        """Remove all vectors matching a payload filter (e.g. a document_id)."""