"""
Application configuration.

All runtime configuration is sourced from environment variables (or a `.env`
file in local development) via Pydantic Settings. Nothing in this module
should be hardcoded for a specific environment — see `.env.example` for the
full list of required variables.
"""

from functools import lru_cache
from typing import Literal

# pyrefly: ignore [missing-import]
from pydantic import Field, PostgresDsn, field_validator
# pyrefly: ignore [missing-import]
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings, populated from environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- App ---
    PROJECT_NAME: str = "AI Research Assistant"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: Literal["local", "staging", "production", "test"] = "local"
    DEBUG: bool = False

    # --- Database ---
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str
    DATABASE_URL: PostgresDsn | None = None

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_database_url(cls, v: str | None, info) -> str:
        if isinstance(v, str) and v:
            return v
        data = info.data
        return (
            f"postgresql+asyncpg://{data['POSTGRES_USER']}:{data['POSTGRES_PASSWORD']}"
            f"@{data['POSTGRES_HOST']}:{data['POSTGRES_PORT']}/{data['POSTGRES_DB']}"
        )

    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_ECHO: bool = False

    # --- Redis ---
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str | None = None
    # REDIS_URL: RedisDsn | None = None

    # @field_validator("REDIS_URL", mode="before")
    # @classmethod
    # def assemble_redis_url(cls, v: str | None, info) -> str:
    #     if isinstance(v, str) and v:
    #         return v
    #     data = info.data
    #     auth = f":{data['REDIS_PASSWORD']}@" if data.get("REDIS_PASSWORD") else ""
    #     return f"redis://{auth}{data['REDIS_HOST']}:{data['REDIS_PORT']}/{data['REDIS_DB']}"

    # --- JWT / Security ---
    JWT_SECRET_KEY: str = Field(..., min_length=32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- CORS ---
    BACKEND_CORS_ORIGINS: list[str] = []

    # --- Logging ---
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    LOG_JSON: bool = False

    # --- Celery ---
    CELERY_BROKER_URL: str | None = None
    CELERY_RESULT_BACKEND: str | None = None

    # @field_validator("CELERY_BROKER_URL", mode="before")
    # @classmethod
    # def assemble_celery_broker_url(cls, v: str | None, info) -> str:
    #     if isinstance(v, str) and v:
    #         return v
    #     data = info.data
    #     auth = f":{data['REDIS_PASSWORD']}@" if data.get("REDIS_PASSWORD") else ""
    #     # Dedicated Redis DB index for Celery so it never collides with
    #     # app caching/refresh-token keys on REDIS_DB.
    #     return f"redis://{auth}{data['REDIS_HOST']}:{data['REDIS_PORT']}/1"

    # @field_validator("CELERY_RESULT_BACKEND", mode="before")
    # @classmethod
    # def assemble_celery_result_backend(cls, v: str | None, info) -> str:
    #     if isinstance(v, str) and v:
    #         return v
    #     data = info.data
    #     auth = f":{data['REDIS_PASSWORD']}@" if data.get("REDIS_PASSWORD") else ""
    #     return f"redis://{auth}{data['REDIS_HOST']}:{data['REDIS_PORT']}/2"

    # --- File storage / uploads ---
    STORAGE_DIR: str = "./storage/uploads"
    MAX_UPLOAD_SIZE_MB: int = 25
    ALLOWED_UPLOAD_EXTENSIONS: list[str] = ["pdf", "docx", "txt", "png", "jpg", "jpeg"]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    # --- OCR / chunking ---
    OCR_LANGUAGES: list[str] = ["en"]
    CHUNK_SIZE_CHARS: int = 1000
    CHUNK_OVERLAP_CHARS: int = 150

    # --- Embeddings ---
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIM: int = 384
    EMBEDDING_BATCH_SIZE: int = 32

    # --- Qdrant ---
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION_NAME: str = "document_chunks"
    QDRANT_API_KEY: str | None = None

    # --- Hybrid search ---
    SEARCH_TOP_K: int = 10
    SEARCH_CANDIDATE_POOL_SIZE: int = 50  # per-method pool before RRF fusion
    RRF_K: int = 60  # standard Reciprocal Rank Fusion smoothing constant

    # --- RAG / LLM ---
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL_NAME: str = "gemini-2.0-flash"
    RAG_MAX_CONTEXT_CHUNKS: int = 6
    RAG_TEMPERATURE: float = 0.2

    # --- Conversation memory / context window ---
    # Token counts here are a `len(text) // 4` heuristic (see
    # services/chat/memory_manager.py) — there's no free local tokenizer
    # for Gemini equivalent to tiktoken, and calling the API to count
    # tokens on every memory decision would add a round-trip per turn.
    MEMORY_MAX_HISTORY_TOKENS: int = 3000  # budget for verbatim recent turns
    MEMORY_MIN_RECENT_TURNS: int = 2  # always keep at least this many turns verbatim
    MEMORY_SUMMARY_MAX_TOKENS: int = 500  # target length for the rolling summary
    MEMORY_SUMMARIZE_AFTER_MESSAGES: int = 10  # re-summarize once this many new messages have aged out


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor — instantiated once per process."""
    return Settings()  # type: ignore[call-arg]


settings = get_settings()