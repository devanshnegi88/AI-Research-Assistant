"""
Qdrant vector store implementation.

Uses the async Qdrant client. Collection is created lazily on first use
with cosine distance, matching `sentence-transformers` similarity
convention for BAAI/bge models.
"""

from __future__ import annotations

import uuid

from qdrant_client import AsyncQdrantClient, models

from app.core.config import settings
from app.core.logging import get_logger
from app.vectorstore.base import VectorRecord, VectorSearchResult, VectorStore

logger = get_logger(__name__)


class QdrantVectorStore(VectorStore):
    def __init__(self) -> None:
        self._client = AsyncQdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            api_key=settings.QDRANT_API_KEY,
        )
        self._collection_name = settings.QDRANT_COLLECTION_NAME
        self._ensured = False

    async def _ensure_collection(self) -> None:
        if self._ensured:
            return

        exists = await self._client.collection_exists(self._collection_name)
        if not exists:
            await self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=models.VectorParams(
                    size=settings.EMBEDDING_DIM,
                    distance=models.Distance.COSINE,
                ),
            )
            # Payload indexes for the fields we filter on — without these,
            # Qdrant falls back to a full scan for every filtered search.
            for field_name, schema in (
                ("owner_id", models.PayloadSchemaType.KEYWORD),
                ("document_id", models.PayloadSchemaType.KEYWORD),
                ("document_type", models.PayloadSchemaType.KEYWORD),
            ):
                await self._client.create_payload_index(
                    collection_name=self._collection_name,
                    field_name=field_name,
                    field_schema=schema,
                )
            logger.info(
                "qdrant_collection_created", extra={"collection": self._collection_name}
            )

        self._ensured = True

    async def upsert(self, records: list[VectorRecord]) -> None:
        if not records:
            return
        await self._ensure_collection()

        points = [
            models.PointStruct(id=str(r.id), vector=r.vector, payload=r.payload)
            for r in records
        ]
        await self._client.upsert(collection_name=self._collection_name, points=points)

    async def search(
        self,
        query_vector: list[float],
        top_k: int,
        filters: dict | None = None,
    ) -> list[VectorSearchResult]:
        await self._ensure_collection()

        qdrant_filter = self._build_filter(filters) if filters else None

        results = await self._client.query_points(
            collection_name=self._collection_name,
            query=query_vector,
            limit=top_k,
            query_filter=qdrant_filter,
            with_payload=True,
        )

        return [
            VectorSearchResult(id=uuid.UUID(point.id), score=point.score, payload=point.payload or {})
            for point in results.points
        ]

    async def delete(self, ids: list[uuid.UUID]) -> None:
        if not ids:
            return
        await self._ensure_collection()
        await self._client.delete(
            collection_name=self._collection_name,
            points_selector=models.PointIdsList(points=[str(i) for i in ids]),
        )

    async def delete_by_filter(self, filters: dict) -> None:
        await self._ensure_collection()
        await self._client.delete(
            collection_name=self._collection_name,
            points_selector=models.FilterSelector(filter=self._build_filter(filters)),
        )

    def _build_filter(self, filters: dict) -> models.Filter:
        conditions = [
            models.FieldCondition(key=key, match=models.MatchValue(value=str(value)))
            for key, value in filters.items()
            if value is not None
        ]
        return models.Filter(must=conditions)


def get_vector_store() -> VectorStore:
    return QdrantVectorStore()