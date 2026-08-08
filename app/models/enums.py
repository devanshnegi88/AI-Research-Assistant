"""Enumerations shared across models and schemas."""

from __future__ import annotations

import enum


class RoleEnum(str, enum.Enum):
    """Application roles — drives RBAC guards in `core/dependencies.py`."""

    ADMIN = "admin"
    USER = "user"


class DocumentType(str, enum.Enum):
    """Supported upload types — drives extractor selection."""

    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    IMAGE = "image"


class DocumentStatus(str, enum.Enum):
    """Lifecycle of a document through the background processing pipeline."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DUPLICATE = "duplicate"

