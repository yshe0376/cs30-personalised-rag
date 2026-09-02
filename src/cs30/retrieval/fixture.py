"""Fixture retriever.

This is deliberately a crude lexical overlap, not a ranking model. Its one job
is to be honest: when the question has nothing to do with the packaged sample
chapter it returns no hits, so the pipeline abstains instead of presenting an
unrelated chunk as evidence.
"""

import re

from pydantic import TypeAdapter

from cs30.contracts import (
    Chunk,
    IndexArtifact,
    RetrievalMode,
    RetrievalResult,
    RetrievedEvidence,
)
from cs30.errors import EmptyQueryError
from cs30.fixture_store import load_fixture_index
from cs30.fixtures import load_fixture

_WORD = re.compile(r"[a-z0-9]+")
_MIN_TERM_LENGTH = 4


def _terms(text: str) -> set[str]:
    return {word for word in _WORD.findall(text.lower()) if len(word) >= _MIN_TERM_LENGTH}


class FixtureRetriever:
    """Rank packaged chunks by term overlap with the query."""

    def __init__(self, chunks: list[Chunk] | None = None) -> None:
        if chunks is None:
            chunks = TypeAdapter(list[Chunk]).validate_python(load_fixture("chunks.json"))
        self._chunks = chunks

    def load_index(self, artifact: IndexArtifact) -> None:
        self._chunks = load_fixture_index(artifact)

    def retrieve(self, query: str, top_k: int) -> RetrievalResult:
        if not query.strip():
            raise EmptyQueryError("query must not be empty")

        query_terms = _terms(query)
        scored: list[tuple[float, Chunk]] = []
        for chunk in self._chunks:
            overlap = query_terms & _terms(chunk.text)
            if overlap:
                scored.append((len(overlap) / len(query_terms), chunk))
        scored.sort(key=lambda pair: (-pair[0], pair[1].chunk_id))

        hits = [
            RetrievedEvidence(
                chunk_id=chunk.chunk_id,
                text=chunk.text,
                chapter_id=chunk.chapter_id,
                source=chunk.source,
                score=round(score, 4),
                rank=rank,
                retriever_type=RetrievalMode.FIXTURE,
            )
            for rank, (score, chunk) in enumerate(scored[:top_k], start=1)
        ]
        return RetrievalResult(query=query, mode=RetrievalMode.FIXTURE, hits=hits)
