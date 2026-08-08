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


class StructuredOutputError(ProviderError):
    """Raised when a provider response cannot satisfy a structured-output contract."""


class GuardrailError(SamsarixAgentError):
    """Raised when a local input or output guardrail fails or blocks content."""

    def __init__(self, message: str, *, stage: str, blocked: bool) -> None:
        super().__init__(message)
        self.stage = stage
        self.blocked = blocked


class ToolError(SamsarixAgentError):
    """Base class for bounded tool-loop failures."""


class ToolApprovalError(ToolError):
    """Raised before execution when a tool call is denied or cannot be approved."""

    def __init__(self, message: str, *, tool_name: str, tool_call_id: str) -> None:
        super().__init__(message)
        self.tool_name = tool_name
        self.tool_call_id = tool_call_id


class ToolExecutionError(ToolError):
    """Raised when a tool request or sanitized local handler execution fails."""
