"""
Image OCR extraction via EasyOCR.

The `easyocr.Reader` is process-heavy to initialize (loads model weights),
so it's created once per worker process and reused — not per task.
"""

from __future__ import annotations

import io
import threading

import easyocr
import numpy as np
from PIL import Image

from app.core.config import settings
from app.services.document.extractors.base import BaseExtractor, ExtractionResult

_reader_lock = threading.Lock()
_reader: easyocr.Reader | None = None


def _get_reader() -> easyocr.Reader:
    global _reader
    if _reader is None:
        with _reader_lock:
            if _reader is None:  # re-check inside the lock
                _reader = easyocr.Reader(settings.OCR_LANGUAGES, gpu=False)
    return _reader


class ImageOCRExtractor(BaseExtractor):
    def extract(self, file_bytes: bytes) -> ExtractionResult:
        image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        image_array = np.array(image)

        reader = _get_reader()
        results = reader.readtext(image_array, detail=1)

        lines = [text for (_bbox, text, _confidence) in results]
        confidences = [conf for (_bbox, _text, conf) in results]

        full_text = "\n".join(lines)
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        metadata = {
            "width": image.width,
            "height": image.height,
            "detected_line_count": len(lines),
            "avg_ocr_confidence": round(avg_confidence, 4),
        }

        return ExtractionResult(text=full_text, metadata=metadata, used_ocr=True)
