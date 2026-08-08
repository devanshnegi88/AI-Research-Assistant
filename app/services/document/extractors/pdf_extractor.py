"""
PDF text + metadata extraction via PyMuPDF (fitz).

Pages with a real text layer are extracted directly. Pages with no
extractable text (common for scanned documents) are rasterized and handed
to the OCR extractor — so OCR only runs where it's actually needed, not on
every page of every PDF.
"""

from __future__ import annotations

import fitz  # PyMuPDF

from app.services.document.extractors.base import BaseExtractor, ExtractionResult
from app.services.document.extractors.image_ocr_extractor import ImageOCRExtractor

_MIN_CHARS_FOR_TEXT_LAYER = 10
_OCR_RENDER_DPI = 200


class PDFExtractor(BaseExtractor):
    def __init__(self, ocr_extractor: ImageOCRExtractor | None = None) -> None:
        self.ocr_extractor = ocr_extractor or ImageOCRExtractor()

    def extract(self, file_bytes: bytes) -> ExtractionResult:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        try:
            page_texts: list[str] = []
            ocr_page_count = 0

            for page in doc:
                text = page.get_text().strip()

                if len(text) < _MIN_CHARS_FOR_TEXT_LAYER:
                    text = self._ocr_page(page)
                    ocr_page_count += 1

                page_texts.append(text)

            full_text = "\n\n".join(page_texts)
            metadata = self._build_metadata(doc, ocr_page_count)

            return ExtractionResult(
                text=full_text,
                metadata=metadata,
                used_ocr=ocr_page_count > 0,
            )
        finally:
            doc.close()

    def _ocr_page(self, page: "fitz.Page") -> str:
        zoom = _OCR_RENDER_DPI / 72
        matrix = fitz.Matrix(zoom, zoom)
        pixmap = page.get_pixmap(matrix=matrix)
        image_bytes = pixmap.tobytes("png")
        result = self.ocr_extractor.extract(image_bytes)
        return result.text

    def _build_metadata(self, doc: "fitz.Document", ocr_page_count: int) -> dict:
        pdf_meta = doc.metadata or {}
        return {
            "page_count": doc.page_count,
            "ocr_page_count": ocr_page_count,
            "title": pdf_meta.get("title") or None,
            "author": pdf_meta.get("author") or None,
            "producer": pdf_meta.get("producer") or None,
            "creation_date": pdf_meta.get("creationDate") or None,
        }
