"""
Application configuration.

All runtime configuration is sourced from environment variables (or a `.env`
file in local development) via Pydantic Settings. Nothing in this module
should be hardcoded for a specific environment — see `.env.example` for the
full list of required variables.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, field_validator
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

# --- Redis ---  # NOTE: Redis removed from the app — kept here only for reference.
    # REDIS_HOST: str = "localhost"
    # REDIS_PORT: int = 6379
    # REDIS_DB: int = 0
    # REDIS_PASSWORD: str | None = None
    # REDIS_URL: RedisDsn | None = None
    # USE_REDIS: bool = False

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

    # --- Celery ---  # NOTE: Celery removed (it depended on Redis as broker).
    # CELERY_BROKER_URL: str | None = None
    # CELERY_RESULT_BACKEND: str | None = None

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


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor — instantiated once per process."""
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
