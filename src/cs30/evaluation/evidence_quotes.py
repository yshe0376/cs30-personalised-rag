"""Ground evidence excerpts without treating display formatting as new content."""

from __future__ import annotations

import re
import unicodedata

_TYPOGRAPHY = str.maketrans(
    {"\u2010": "-", "\u2011": "-", "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"'}
)
_OMISSION = re.compile(r"\.{3,}|\u2026")


def normalize_quote_text(text: str) -> str:
    """Normalize canonical Unicode, whitespace and typographic quotes/hyphens only."""
    return " ".join(unicodedata.normalize("NFC", text).translate(_TYPOGRAPHY).split())


def quote_is_grounded(quote: str, evidence: str) -> bool:
    """Require every nonempty excerpt to occur in the same cited evidence.

    Ellipses delimit independent excerpts, not a reconstructed continuous sentence.
    Excerpt order is immaterial, as it is for multiple quote rows for one evidence ID.
    Numbers, case, mathematical symbols and other wording are not rewritten.
    """
    normalized = normalize_quote_text(quote)
    fragments = [part.strip() for part in _OMISSION.split(normalized) if part.strip()]
    source = normalize_quote_text(evidence)
    return bool(fragments) and all(fragment in source for fragment in fragments)


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
        grouped.setdefault(evidence_id, []).append(quote)
    return {evidence_id: " … ".join(quotes) for evidence_id, quotes in grouped.items()}
