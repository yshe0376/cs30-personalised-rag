"""Generation-specific error categories recorded in Week 1 run traces."""

from cs30.errors import GenerationError


class LLMProviderError(GenerationError):
    """The remote provider rejected or failed a request."""


class LLMTimeoutError(LLMProviderError):
    """The remote provider did not respond before the configured timeout."""


class LLMEmptyResponseError(LLMProviderError):
    """The provider response did not contain output text."""


class LLMOutputValidationError(GenerationError):
    """The model output did not match the fixed answer schema."""


class LLMRequestBudgetExceeded(ValueError):
    """The cumulative HTTP request budget has been exhausted; resume after review."""


class LLMCacheIntegrityError(ValueError):
    """A saved API response changed; stop before overwriting or making paid calls."""


class LLMRetryLater(LLMProviderError, ValueError):
    """The rate-limit wait/retry budget is exhausted; do not retry immediately."""
