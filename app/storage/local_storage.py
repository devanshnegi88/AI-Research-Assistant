"""
Local disk storage backend.

Files are namespaced under `STORAGE_DIR/<owner_id>/<uuid>_<safe_filename>`.
Blocking file I/O is offloaded to a thread via `asyncio.to_thread` so it
doesn't block the event loop, without pulling in an extra async-file-IO
dependency for Phase 2.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from app.core.config import settings
from app.storage.base import StorageBackend


class LocalStorageBackend(StorageBackend):
    def __init__(self, root_dir: str | None = None) -> None:
        self.root_dir = Path(root_dir or settings.STORAGE_DIR).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, key: str) -> Path:
        """Resolve `key` under root_dir, rejecting any path traversal."""
        path = (self.root_dir / key).resolve()
        if self.root_dir not in path.parents and path != self.root_dir:
            raise ValueError(f"Invalid storage key (path traversal): {key!r}")
        return path

    async def save(self, key: str, content: bytes) -> str:
        path = self._resolve_path(key)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "wb") as f:
                f.write(content)

        await asyncio.to_thread(_write)
        return str(path)

    async def read(self, key: str) -> bytes:
        path = self._resolve_path(key)

        def _read() -> bytes:
            with open(path, "rb") as f:
                return f.read()

        return await asyncio.to_thread(_read)

    async def delete(self, key: str) -> None:
        path = self._resolve_path(key)

        def _delete() -> None:
            if path.exists():
                os.remove(path)

        await asyncio.to_thread(_delete)

    async def exists(self, key: str) -> bool:
        path = self._resolve_path(key)
        return await asyncio.to_thread(path.exists)


def get_storage_backend() -> StorageBackend:
    """FastAPI/Celery-shared factory — swap implementation here in future."""
    return LocalStorageBackend()
