# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Small, provider-neutral data models used by the public API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .errors import InputValidationError

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """One validated message passed to a model provider."""

    role: Role
    content: str

    def __post_init__(self) -> None:
        if self.role not in {"system", "user", "assistant"}:
            raise InputValidationError(f"unsupported message role: {self.role!r}")
        if not isinstance(self.content, str) or not self.content:
            raise InputValidationError("message content must be a non-empty string")

    def as_dict(self) -> dict[str, str]:
        """Return the OpenAI-compatible representation of this message."""

        return {"role": self.role, "content": self.content}


@dataclass(frozen=True, slots=True)
class ProviderResponse:
    """Normalized response returned by every provider implementation."""

    content: str
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.content, str) or not self.content:
            raise InputValidationError("provider response content must be non-empty")
        for label, value in (
            ("input_tokens", self.input_tokens),
            ("output_tokens", self.output_tokens),
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise InputValidationError(f"{label} must be a non-negative integer")


@dataclass(slots=True)
class AgentMetrics:
    """Local counters for one agent instance.

    Token counts are populated only when the provider reports them. They are not
    estimated or presented as billing data.
    """

    requests: int = 0
    successes: int = 0
    failures: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    last_latency_ms: float | None = None

    def as_dict(self) -> dict[str, int | float | None]:
        """Return a stable, JSON-serializable snapshot."""

        return {
            "requests": self.requests,
            "successes": self.successes,
            "failures": self.failures,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "last_latency_ms": self.last_latency_ms,
        }
