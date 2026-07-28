"""Public exception hierarchy for Helix LLM Agent Engine."""


class HelixAgentError(Exception):
    """Base class for errors raised by the package."""


class ConfigurationError(HelixAgentError):
    """Raised when engine or provider configuration is invalid."""


class InputValidationError(HelixAgentError, ValueError):
    """Raised when caller-provided agent input is invalid."""


class BudgetExceededError(HelixAgentError):
    """Raised before a request would exceed a configured local limit."""


class ProviderError(HelixAgentError):
    """Raised when a model provider fails or returns an invalid response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
