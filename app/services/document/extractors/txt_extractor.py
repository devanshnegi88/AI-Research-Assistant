"""Plain-text extraction with basic encoding fallback."""

from __future__ import annotations

from app.services.document.extractors.base import BaseExtractor, ExtractionResult

_ENCODING_CANDIDATES = ("utf-8", "utf-16", "latin-1")


class TXTExtractor(BaseExtractor):
    def extract(self, file_bytes: bytes) -> ExtractionResult:
        text, encoding_used = self._decode(file_bytes)
        metadata = {
            "encoding": encoding_used,
            "line_count": text.count("\n") + 1 if text else 0,
        }
        return ExtractionResult(text=text, metadata=metadata, used_ocr=False)

    def _decode(self, file_bytes: bytes) -> tuple[str, str]:
        for encoding in _ENCODING_CANDIDATES:
            try:
                return file_bytes.decode(encoding), encoding
            except UnicodeDecodeError:
                continue
        # Last resort: never fail the whole upload over an encoding quirk —
        # replace undecodable bytes rather than losing the document.
        return file_bytes.decode("utf-8", errors="replace"), "utf-8 (with replacements)"
