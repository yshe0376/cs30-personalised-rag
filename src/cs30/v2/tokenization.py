"""The ruler that measures chunk length.

Chunk sizes are counted in tokens, so the tokenizer decides where chunk
boundaries fall.  v2 fixes one ruler -- ``Alibaba-NLP/gte-modernbert-base`` --
and keeps it fixed even while other embedding models are compared: otherwise
every model swap would re-chunk the corpus, change every chunk ID, and move two
knobs at once.

The name is part of the chunk config hash, so a corpus always records which
ruler produced it.
"""

from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

# Decided 2026-09-23. Also the default embedding model; the two are separate
# choices, and only this one may not change without re-chunking.
CHUNK_TOKENIZER_NAME = "Alibaba-NLP/gte-modernbert-base"
# Dependency-free ruler for fixtures and tests, never for a real corpus.
REGEX_TOKENIZER_NAME = "unicode-wordpunct-v1"


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

    def _load(self):
        if self._tokenizer is None:
            from transformers import AutoTokenizer

            self._tokenizer = AutoTokenizer.from_pretrained(
                self._name, revision=self._revision
            )
        return self._tokenizer

    def count(self, text: str) -> int:
        return len(self._load().encode(text, add_special_tokens=False))


def build_token_counter(name: str, *, revision: str | None = None) -> TokenCounter:
    """Return the ruler named in a chunk configuration."""

    if name == REGEX_TOKENIZER_NAME:
        return RegexTokenCounter()
    return HuggingFaceTokenCounter(name, revision=revision)
