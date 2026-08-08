"""
Text cleaning/normalization applied to raw extracted text before chunking.

Kept as pure functions — easy to unit test and to extend per document type
later without touching the extraction or chunking layers.
"""

from __future__ import annotations

import re
import unicodedata

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MULTIPLE_BLANK_LINES_RE = re.compile(r"\n{3,}")
_MULTIPLE_SPACES_RE = re.compile(r"[ \t]{2,}")
_TRAILING_WHITESPACE_RE = re.compile(r"[ \t]+\n")


def clean_text(raw_text: str) -> str:
    """Normalize unicode, strip control chars, collapse excess whitespace."""
    if not raw_text:
        return ""

    text = unicodedata.normalize("NFKC", raw_text)
    text = _CONTROL_CHARS_RE.sub("", text)
    text = _TRAILING_WHITESPACE_RE.sub("\n", text)
    text = _MULTIPLE_SPACES_RE.sub(" ", text)
    text = _MULTIPLE_BLANK_LINES_RE.sub("\n\n", text)

    return text.strip()
