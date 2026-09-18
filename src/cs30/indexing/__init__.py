"""Member 5: embeddings and the FAISS dense index.

``FaissIndexBuilder`` needs the optional ``ml`` extra (faiss-cpu and
sentence-transformers), so it is exported lazily. Importing this package must
stay possible for anyone who installed only the core dependencies.
"""

from typing import TYPE_CHECKING

from .fixture import FixtureIndexBuilder

if TYPE_CHECKING:
    from .faiss_index import FaissIndexBuilder

__all__ = ["FaissIndexBuilder", "FixtureIndexBuilder"]


def __getattr__(name: str) -> object:
    """Import the FAISS builder on first use so the core install stays light."""

    if name == "FaissIndexBuilder":
        from .faiss_index import FaissIndexBuilder

        return FaissIndexBuilder
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")