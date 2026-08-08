"""
Character-based overlapping text chunker.

Splits on paragraph/sentence boundaries where possible so chunks don't cut
mid-sentence; falls back to a hard split only when a single paragraph
exceeds the chunk size.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings

_SENTENCE_BOUNDARY = ". "


@dataclass
class Chunk:
    index: int
    content: str
    char_count: int


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[Chunk]:
    chunk_size = chunk_size or settings.CHUNK_SIZE_CHARS
    overlap = overlap if overlap is not None else settings.CHUNK_OVERLAP_CHARS

    if not text:
        return []
    if overlap >= chunk_size:
        raise ValueError("chunk overlap must be smaller than chunk size")

    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    raw_chunks: list[str] = []
    buffer = ""

    for paragraph in paragraphs:
        candidate = f"{buffer}\n\n{paragraph}" if buffer else paragraph

        if len(candidate) <= chunk_size:
            buffer = candidate
            continue

        if buffer:
            raw_chunks.append(buffer)
            buffer = ""

        if len(paragraph) <= chunk_size:
            buffer = paragraph
        else:
            # Paragraph itself exceeds chunk_size — hard-split at sentence
            # boundaries, falling back to a fixed-size slice if needed.
            raw_chunks.extend(_split_oversized(paragraph, chunk_size))

    if buffer:
        raw_chunks.append(buffer)

    overlapped = _apply_overlap(raw_chunks, overlap)

    return [
        Chunk(index=i, content=c, char_count=len(c)) for i, c in enumerate(overlapped)
    ]


def _split_oversized(paragraph: str, chunk_size: int) -> list[str]:
    sentences = paragraph.split(_SENTENCE_BOUNDARY)
    pieces: list[str] = []
    buffer = ""

    for sentence in sentences:
        candidate = f"{buffer}{_SENTENCE_BOUNDARY}{sentence}" if buffer else sentence
        if len(candidate) <= chunk_size:
            buffer = candidate
        else:
            if buffer:
                pieces.append(buffer)
            buffer = sentence if len(sentence) <= chunk_size else sentence[:chunk_size]

    if buffer:
        pieces.append(buffer)

    return pieces


def _apply_overlap(chunks: list[str], overlap: int) -> list[str]:
    if overlap <= 0 or len(chunks) <= 1:
        return chunks

    overlapped = [chunks[0]]
    for prev, current in zip(chunks, chunks[1:]):
        tail = prev[-overlap:]
        overlapped.append(f"{tail}{current}")

    return overlapped
