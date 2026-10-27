"""Ground evidence excerpts without treating display formatting as new content."""

from __future__ import annotations

import re
import unicodedata

_TYPOGRAPHY = str.maketrans(
    {"\u2010": "-", "\u2011": "-", "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'}
)
_OMISSION = re.compile(r"\.{3,}|\u2026")
QUOTE_ROW_SEPARATOR = "\n[quote-row]\n"


def normalize_quote_text(text: str) -> str:
    """Normalize canonical Unicode, whitespace and typographic quotes/hyphens only."""
    return " ".join(unicodedata.normalize("NFC", text).translate(_TYPOGRAPHY).split())


def quote_is_grounded(quote: str, evidence: str) -> bool:
    """Ground three-word fragments in source order within each independent row.

    Rows are stored separately inside the existing ID-to-string representation.
    Ellipsis fragments within a row must not overlap. Row order is independent.
    Numbers, case, mathematical symbols and other wording are not rewritten.
    """
    source = normalize_quote_text(evidence)
    for row in quote.split(QUOTE_ROW_SEPARATOR):
        normalized = normalize_quote_text(row)
        fragments = [part.strip() for part in _OMISSION.split(normalized) if part.strip()]
        if not fragments:
            return False
        cursor = 0
        for fragment in fragments:
            words = sum(any(char.isalnum() for char in token) for token in fragment.split())
            if words < 3:
                return False
            start = source.find(fragment, cursor)
            if start < 0:
                return False
            cursor = start + len(fragment)
    return True


def merge_quote_rows(value: object) -> object:
    """Keep the existing ID-to-string shape while preserving repeated-ID excerpts."""
    if not isinstance(value, list):
        return value
    grouped: dict[str, list[str]] = {}
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError("evidence quote entries must be objects")
        evidence_id = entry.get("evidence_id")
        if not isinstance(evidence_id, str) or not evidence_id:
            raise ValueError("evidence quote entries require an evidence_id")
        quote = entry.get("quote")
        if not isinstance(quote, str) or not quote.strip():
            raise ValueError("evidence quote entries require a nonempty quote")
        if QUOTE_ROW_SEPARATOR in quote:
            raise ValueError(
                "a single evidence quote row cannot contain the reserved row separator"
            )
        grouped.setdefault(evidence_id, []).append(quote)
    return {
        evidence_id: QUOTE_ROW_SEPARATOR.join(quotes) for evidence_id, quotes in grouped.items()
    }
