# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Public exception hierarchy for Samsarix Agent Engine."""


class SamsarixAgentError(Exception):
    """Base class for errors raised by the package."""


class ConfigurationError(SamsarixAgentError):
    """Raised when engine or provider configuration is invalid."""


class InputValidationError(SamsarixAgentError, ValueError):
    """Raised when caller-provided agent input is invalid."""


class BudgetExceededError(SamsarixAgentError):
    """Raised before a request would exceed a configured local limit."""


class ProviderError(SamsarixAgentError):
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
