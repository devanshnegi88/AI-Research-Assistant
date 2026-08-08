"""Content-hash based duplicate detection."""

from __future__ import annotations

import hashlib


def compute_content_hash(file_bytes: bytes) -> str:
    """SHA-256 of raw file bytes — identical files hash identically
    regardless of filename, upload time, or extracted content."""
    return hashlib.sha256(file_bytes).hexdigest()
