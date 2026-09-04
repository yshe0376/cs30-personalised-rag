"""Task-7 local Top-K retrieval over its available smoke evidence."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

from cs30.contracts import IndexArtifact, RetrievalHit, RetrievalMode, RetrievalResult
from cs30.errors import EmptyQueryError, RetrievalError

_WORD = re.compile(r"[a-z0-9]+")
_STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "do",
    "does",
    "describe",
    "difference",
    "explain",
    "for",
    "from",
    "how",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "please",
    "that",
    "the",
    "to",
    "what",
    "when",
    "which",
    "why",
    "who",
    "with",
}


def _normalise_term(term: str) -> str:
    """Apply a small deterministic stemmer without adding a runtime dependency."""

    if len(term) > 5 and term.endswith("ies"):
        return f"{term[:-3]}y"
    if len(term) > 5 and term.endswith("ing"):
        return term[:-3]
    if len(term) > 4 and term.endswith("ed"):
        return term[:-2]
    if len(term) > 4 and term.endswith("s") and not term.endswith("ss"):
        return term[:-1]
    return term


def _terms(text: str) -> set[str]:
    return {
        _normalise_term(term)
        for term in _WORD.findall(text.casefold())
        if term not in _STOP_WORDS and len(term) > 1
    }


@dataclass(frozen=True)
class _Evidence:
    chunk_id: str
    text: str
    chapter_id: str
    source: str
    terms: frozenset[str]


class CombinedEvidenceRetriever:
    """Rank the combined local evidence corpus by weighted query-term coverage.

    This is the portable first RAG retriever. It is intentionally transparent
    and dependency-free; a later dense retriever can replace it behind the same
    ``Retriever`` protocol without changing the pipeline.
    """

    index_type = "weighted-term-coverage"

    def __init__(
        self,
        evidence: Iterable[RetrievalHit],
        *,
        minimum_score: float = 0.2,
    ) -> None:
        if not 0.0 < minimum_score <= 1.0:
            raise ValueError("minimum_score must be in the interval (0, 1]")
        by_id: dict[str, _Evidence] = {}
        for hit in evidence:
            item = _Evidence(
                chunk_id=hit.chunk_id,
                text=hit.text,
                chapter_id=hit.chapter_id,
                source=hit.source,
                terms=frozenset(_terms(hit.text)),
            )
            previous = by_id.get(item.chunk_id)
            if previous is not None and previous != item:
                raise ValueError(f"conflicting evidence for chunk_id: {item.chunk_id}")
            by_id[item.chunk_id] = item
        if not by_id:
            raise ValueError("combined evidence corpus must not be empty")

        self._evidence = tuple(by_id.values())
        self.minimum_score = minimum_score
        document_frequency = Counter(
            term for item in self._evidence for term in item.terms
        )
        corpus_size = len(self._evidence)
        self._idf = {
            term: math.log((corpus_size + 1) / (frequency + 1)) + 1.0
            for term, frequency in document_frequency.items()
        }

    @property
    def evidence_count(self) -> int:
        return len(self._evidence)

    def load_index(self, artifact: IndexArtifact) -> None:
        raise RetrievalError(
            "CombinedEvidenceRetriever is built from local evidence and cannot load "
            f"index artifact {artifact.artifact_id!r}"
        )

    def retrieve(self, query: str, top_k: int) -> RetrievalResult:
        if not query.strip():
            raise EmptyQueryError("query must not be empty")
        if top_k < 1:
            raise RetrievalError("top_k must be positive")

        query_terms = _terms(query)
        if not query_terms:
            return RetrievalResult(query=query, mode=RetrievalMode.FIXTURE)
        query_weight = sum(self._idf.get(term, 1.0) for term in query_terms)
        minimum_overlap = 1 if len(query_terms) == 1 else 2
        scored: list[tuple[float, int, _Evidence]] = []
        for item in self._evidence:
            overlap = query_terms & item.terms
            if len(overlap) < minimum_overlap:
                continue
            overlap_weight = sum(self._idf.get(term, 1.0) for term in overlap)
            score = overlap_weight / query_weight
            if score >= self.minimum_score:
                scored.append((score, len(overlap), item))

        scored.sort(key=lambda row: (-row[0], -row[1], row[2].chunk_id))
        hits = [
            RetrievalHit(
                chunk_id=item.chunk_id,
                text=item.text,
                chapter_id=item.chapter_id,
                source=item.source,
                score=round(score, 4),
                rank=rank,
                retriever_type=RetrievalMode.FIXTURE,
            )
            for rank, (score, _overlap_count, item) in enumerate(
                scored[:top_k], start=1
            )
        ]
        return RetrievalResult(query=query, mode=RetrievalMode.FIXTURE, hits=hits)
