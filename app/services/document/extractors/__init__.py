"""Extractor factory — maps DocumentType to the right extractor instance."""

from __future__ import annotations

from app.models.enums import DocumentType
from app.services.document.extractors.base import BaseExtractor
from app.services.document.extractors.docx_extractor import DOCXExtractor
from app.services.document.extractors.image_ocr_extractor import ImageOCRExtractor
from app.services.document.extractors.pdf_extractor import PDFExtractor
from app.services.document.extractors.txt_extractor import TXTExtractor


def get_extractor(document_type: DocumentType) -> BaseExtractor:
    match document_type:
        case DocumentType.PDF:
            return PDFExtractor()
        case DocumentType.DOCX:
            return DOCXExtractor()
        case DocumentType.TXT:
            return TXTExtractor()
        case DocumentType.IMAGE:
            return ImageOCRExtractor()
        case _:
            raise ValueError(f"No extractor registered for type: {document_type}")
