"""Typed errors so a failing module reports a cause instead of a stack trace.

Week 1 requires that a missing index, an empty question, or a generation
failure produce a clear error rather than terminating the whole system.
"""


class CS30Error(Exception):
    """Base class for every expected CS-30 failure."""

    code: str = "CS30-000"


class ConfigError(CS30Error):
    """Configuration is missing, unreadable, or invalid."""

    code: str = "CS30-CFG-001"


class EmptyQueryError(CS30Error):
    """The question was empty or whitespace only."""

    code: str = "CS30-QRY-001"


class IndexUnavailableError(CS30Error):
    """The index could not be built, found, or loaded."""

    code: str = "CS30-IDX-001"


class ArtifactMismatchError(IndexUnavailableError):
    """A corpus, chunk config, embedding model, or index version does not match.

    Failing explicitly prevents a stale or mismatched index from silently
    producing evidence that cannot be traced to the loaded corpus.
    """

    code: str = "CS30-IDX-002"


class RetrievalError(CS30Error):
    """Retrieval failed. Finding no evidence is NOT this error: an empty
    ``RetrievalResult.hits`` is a valid result."""

    code: str = "CS30-RET-001"


class RetrievalModeError(RetrievalError):
    """The requested retrieval mode is unknown or unsupported by the service."""

    code: str = "CS30-RET-002"


class GenerationError(CS30Error):
    """The generator failed, timed out, or returned unparseable output."""

    code: str = "CS30-GEN-001"


class CitationIntegrityError(CS30Error):
    """The generated answer cites evidence that retrieval did not supply."""

    code: str = "CS30-CIT-001"
