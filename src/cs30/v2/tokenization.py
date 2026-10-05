"""The ruler that measures chunk length.

Chunk sizes are counted in tokens, so the tokenizer decides where chunk
boundaries fall.  v2 fixes one ruler -- the BERT WordPiece tokenizer of
``google-bert/bert-base-uncased`` at a pinned revision -- and keeps it fixed
even while embedding models are compared: otherwise every model swap would
re-chunk the corpus, change every chunk ID, and move two knobs at once.

The ruler only counts; each embedding model still encodes with its own
tokenizer.  It is the same WordPiece tokenizer that sized the frozen v1 (W5)
corpus, so v2 chunk sizes stay comparable with v1.

The name and revision are part of the chunk config hash, so a corpus always
records exactly which tokenizer files produced it.
"""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

# Decided 2026-09-24, replacing the gte-modernbert-base ruler of 2026-09-23.
# Independent of the default embedding model. MiniLM, bge-base-en-v1.5 and
# e5-base-v2 ship the same WordPiece vocabulary, but MiniLM's tokenizer.json
# bakes in a 128-token truncation, so the ruler is loaded from the original.
CHUNK_TOKENIZER_NAME = "google-bert/bert-base-uncased"
CHUNK_TOKENIZER_REVISION = "86b5e0934494bd15c9632b12f734a8a67f723594"
# Dependency-free ruler for fixtures and tests, never for a real corpus.
REGEX_TOKENIZER_NAME = "unicode-wordpunct-v1"

_COMMIT_HASH = re.compile(r"[0-9a-f]{40}")


def is_pinned_revision(revision: str | None) -> bool:
    """Whether ``revision`` is a full commit hash rather than a movable ref."""

    return revision is not None and _COMMIT_HASH.fullmatch(revision) is not None


@runtime_checkable
class TokenCounter(Protocol):
    @property
    def name(self) -> str: ...

    def count(self, text: str) -> int: ...


class RegexTokenCounter:
    """Words and single punctuation marks; deterministic and offline."""

    _pattern = re.compile(r"\w+|[^\w\s]", flags=re.UNICODE)

    @property
    def name(self) -> str:
        return REGEX_TOKENIZER_NAME

    def count(self, text: str) -> int:
        return sum(1 for _ in self._pattern.finditer(text))


class HuggingFaceTokenCounter:
    """Count with a Hugging Face tokenizer, loaded on first use."""

    def __init__(self, name: str, *, revision: str | None = None) -> None:
        self._name = name
        self._revision = revision
        self._tokenizer = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def revision(self) -> str | None:
        return self._revision

    def _load(self):
        if self._tokenizer is None:
            from transformers import AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(
                self._name, revision=self._revision
            )
        return self._tokenizer

    def count(self, text: str) -> int:
        # A ruler must see the whole text: never truncate, and do not warn when
        # a chunk is longer than some model's input limit.
        return len(
            self._load().encode(
                text, add_special_tokens=False, truncation=False, verbose=False
            )
        )


def build_token_counter(name: str, *, revision: str | None = None) -> TokenCounter:
    """Return the ruler named in a chunk configuration."""

    if name == REGEX_TOKENIZER_NAME:
        return RegexTokenCounter()
    return HuggingFaceTokenCounter(name, revision=revision)
