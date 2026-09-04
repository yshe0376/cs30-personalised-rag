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
