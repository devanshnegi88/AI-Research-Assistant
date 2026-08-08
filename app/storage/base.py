"""
Storage backend interface.

Phase 2 ships a local-disk implementation (`local_storage.py`). Swapping to
S3/GCS later means writing one more class against this interface — nothing
in `services/` or `api/` needs to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class StorageBackend(ABC):
    @abstractmethod
    async def save(self, key: str, content: bytes) -> str:
        """Persist `content` under `key`. Returns the storage path/URI."""

    @abstractmethod
    async def read(self, key: str) -> bytes:
        """Read raw bytes back for a previously saved key."""

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete the object at `key`. No-op if it doesn't exist."""

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Whether an object exists at `key`."""
