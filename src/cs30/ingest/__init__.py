"""Member 2: textbook acquisition, parsing, cleaning, and chaptering."""

from typing import TYPE_CHECKING

from .fixture import FixtureDocumentParser

if TYPE_CHECKING:
    from .textbooks import DEFAULT_TEXTBOOK_ID, TEXTBOOKS, TextbookSpec, get_textbook

__all__ = [
    "DEFAULT_TEXTBOOK_ID",
    "FixtureDocumentParser",
    "TEXTBOOKS",
    "TextbookSpec",
    "get_textbook",
]


def __getattr__(name: str) -> object:
    """Load catalogue exports lazily so ``python -m cs30.ingest.textbooks`` is clean."""

    if name in {"DEFAULT_TEXTBOOK_ID", "TEXTBOOKS", "TextbookSpec", "get_textbook"}:
        from . import textbooks

        return getattr(textbooks, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
