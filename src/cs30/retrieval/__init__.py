"""Retrieval backends with lazy imports for optional ML dependencies."""

from typing import TYPE_CHECKING

from .fixture import FixtureRetriever

if TYPE_CHECKING:
    from .real import BM25Retriever, FaissDenseRetriever, RealRetrievalService, RRFRetriever

__all__ = [
    "BM25Retriever",
    "FaissDenseRetriever",
    "FixtureRetriever",
    "RealRetrievalService",
    "RRFRetriever",
]


def __getattr__(name: str) -> object:
    if name in {
        "BM25Retriever",
        "FaissDenseRetriever",
        "RealRetrievalService",
        "RRFRetriever",
    }:
        from . import real

        return getattr(real, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
