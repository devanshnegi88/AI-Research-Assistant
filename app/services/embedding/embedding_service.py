"""
Embedding generation via sentence-transformers.

Model (`BAAI/bge-small-en-v1.5`) is loaded once per process — instantiation
downloads/loads weights and is too expensive to repeat per call. Both the
FastAPI process (query-time embedding) and the Celery worker (chunk-time
embedding) hold their own lazily-initialized instance.

BGE models are trained with an asymmetric convention: documents are
embedded as-is, but queries need an instruction prefix for best retrieval
quality — `embed_query` applies it, `embed_batch` (for chunks) does not.
"""

from __future__ import annotations

import threading

from sentence_transformers import SentenceTransformer

from app.core.config import settings

_BGE_QUERY_INSTRUCTION = (
    "Represent this sentence for searching relevant passages: "
)

_model_lock = threading.Lock()
_model: SentenceTransformer | None = None


def _get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:  # re-check inside the lock
                _model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)
    return _model


class EmbeddingService:
    def __init__(self) -> None:
        self.model = _get_model()

    def embed_query(self, text: str) -> list[float]:
        vector = self.model.encode(
            f"{_BGE_QUERY_INSTRUCTION}{text}",
            normalize_embeddings=True,
        )
        return vector.tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self.model.encode(
            texts,
            batch_size=settings.EMBEDDING_BATCH_SIZE,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return vectors.tolist()


def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()