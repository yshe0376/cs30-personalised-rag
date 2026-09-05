"""Six reproducible, split-ready chunking candidates for engineering runs."""

from __future__ import annotations

from dataclasses import dataclass

from cs30.chunking.strategy import BlockChunkingStrategy
from cs30.contracts import ContentType

CORE_EVIDENCE_TYPES = (
    ContentType.BODY,
    ContentType.EXAMPLE,
    ContentType.FIGURE_CAPTION,
    ContentType.GLOSSARY,
)


@dataclass(frozen=True, slots=True)
class ChunkingCandidate:
    """A named engineering candidate without an effectiveness claim."""

    candidate_id: str
    description: str
    strategy: BlockChunkingStrategy


def _strategy(
    candidate_id: str,
    *,
    include_types: tuple[ContentType, ...] | None,
    respect_section_boundaries: bool = True,
    enrich_embed_text: bool = False,
) -> BlockChunkingStrategy:
    return BlockChunkingStrategy(
        target_tokens=500,
        min_tokens=100,
        max_tokens=600,
        respect_section_boundaries=respect_section_boundaries,
        enrich_embed_text=enrich_embed_text,
        candidate_id=candidate_id,
        include_types=include_types,
    )


CHUNKING_CANDIDATES = (
    ChunkingCandidate(
        "S1",
        "All parser content types, section-isolated, cited text only.",
        _strategy("S1", include_types=None),
    ),
    ChunkingCandidate(
        "S2",
        "Core evidence content types, section-isolated, cited text only.",
        _strategy("S2", include_types=CORE_EVIDENCE_TYPES),
    ),
    ChunkingCandidate(
        "S3",
        "Core evidence plus tables and equations, section-isolated.",
        _strategy(
            "S3",
            include_types=CORE_EVIDENCE_TYPES + (ContentType.TABLE, ContentType.EQUATION),
        ),
    ),
    ChunkingCandidate(
        "S4",
        "Instructional evidence, summaries and sidebars, section-isolated.",
        _strategy(
            "S4",
            include_types=CORE_EVIDENCE_TYPES
            + (
                ContentType.LEARNING_OBJECTIVE,
                ContentType.SIDEBAR,
                ContentType.SUMMARY,
            ),
        ),
    ),
    ChunkingCandidate(
        "S5",
        "Core evidence with chapter and section context in embed_text.",
        _strategy(
            "S5",
            include_types=CORE_EVIDENCE_TYPES,
            enrich_embed_text=True,
        ),
    ),
    ChunkingCandidate(
        "S6",
        "Core evidence with embed_text context and chapter-only isolation.",
        _strategy(
            "S6",
            include_types=CORE_EVIDENCE_TYPES,
            respect_section_boundaries=False,
            enrich_embed_text=True,
        ),
    ),
)


def get_chunking_candidate(candidate_id: str) -> ChunkingCandidate:
    """Return one candidate by its stable S1-S6 identifier."""

    normalised = candidate_id.strip().upper()
    for candidate in CHUNKING_CANDIDATES:
        if candidate.candidate_id == normalised:
            return candidate
    raise ValueError(f"unknown chunking candidate: {candidate_id}")
