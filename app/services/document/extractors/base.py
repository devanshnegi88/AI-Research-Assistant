"""
Text-extractor interface.

Every file-type extractor (PDF, DOCX, TXT, image/OCR) implements `extract()`
and returns an `ExtractionResult` — the rest of the pipeline (cleaning,
chunking, persistence) doesn't care which extractor produced it.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ExtractionResult:
    text: str
    metadata: dict = field(default_factory=dict)
    used_ocr: bool = False


class BaseExtractor(ABC):
    @abstractmethod
    def extract(self, file_bytes: bytes) -> ExtractionResult:
        """Extract text + metadata from raw file bytes.

        Runs synchronously inside a Celery worker process (not the FastAPI
        event loop) — CPU-bound work here is fine and expected.
        """
