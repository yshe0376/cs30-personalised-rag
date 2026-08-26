"""Configuration for block-boundary-aware textbook chunking."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BlockChunkingStrategy:
    """One structure-aware chunking strategy expressed as constructor data.

    The target is intentionally not a sliding-window size. Whole parser blocks
    are grouped so their combined token count is near ``target_tokens`` while
    respecting ``max_tokens`` whenever the individual blocks allow it.
    """

    target_tokens: int = 500
    min_tokens: int = 100
    max_tokens: int = 600
    respect_section_boundaries: bool = True
    enrich_embed_text: bool = False
    reject_duplicate_text: bool = True
    chunker_version: str = "0.2.0"

    def __post_init__(self) -> None:
        if self.min_tokens <= 0:
            raise ValueError("min_tokens must be positive")
        if self.target_tokens < self.min_tokens:
            raise ValueError("target_tokens must be greater than or equal to min_tokens")
        if self.max_tokens < self.target_tokens:
            raise ValueError("max_tokens must be greater than or equal to target_tokens")
        if not self.chunker_version.strip():
            raise ValueError("chunker_version must not be empty")

