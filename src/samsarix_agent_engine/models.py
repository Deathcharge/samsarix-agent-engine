# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Small, provider-neutral data models used by the public API."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias

from .errors import InputValidationError, StructuredOutputError

Role = Literal["system", "user", "assistant"]
JsonValue: TypeAlias = bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"] | None


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


@dataclass(frozen=True, slots=True)
class ProviderStreamChunk:
    """One normalized provider stream event.

    Providers emit zero or more content deltas followed by exactly one final
    event. The final event may carry provider-reported usage.
    """

    delta: str = ""
    final: bool = False
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.delta, str):
            raise InputValidationError("stream delta must be a string")
        if not self.delta and not self.final:
            raise InputValidationError("an empty stream event must be final")
        if not isinstance(self.final, bool):
            raise InputValidationError("stream final must be a boolean")
        for label, value in (
            ("input_tokens", self.input_tokens),
            ("output_tokens", self.output_tokens),
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise InputValidationError(f"{label} must be a non-negative integer")


def parse_json_output(content: str, *, max_depth: int = 64) -> JsonValue:
    """Parse strict, finite JSON from an untrusted model response.

    Duplicate object keys, JavaScript-style non-finite numbers, excessive
    nesting, and non-string input are rejected so downstream automation receives
    one deterministic representation.
    """

    if not isinstance(content, str) or not content.strip():
        raise StructuredOutputError("provider response contained no structured output")
    if not isinstance(max_depth, int) or isinstance(max_depth, bool) or not 1 <= max_depth <= 256:
        raise InputValidationError("max_depth must be an integer between 1 and 256")

    def reject_constant(_: str) -> Any:
        raise StructuredOutputError("structured output contains a non-finite number")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise StructuredOutputError("structured output contains duplicate object keys")
            result[key] = value
        return result

    try:
        parsed: Any = json.loads(
            content,
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicate_keys,
        )
    except StructuredOutputError:
        raise
    except (ValueError, RecursionError, UnicodeError) as exc:
        raise StructuredOutputError("provider response was not valid bounded JSON") from exc

    def validate(value: Any, depth: int) -> JsonValue:
        if depth > max_depth:
            raise StructuredOutputError("structured output exceeded the nesting limit")
        if value is None or isinstance(value, (bool, int)):
            return value
        if isinstance(value, str):
            if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
                raise StructuredOutputError("structured output contained invalid Unicode")
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                raise StructuredOutputError("structured output contains a non-finite number")
            return value
        if isinstance(value, list):
            return [validate(item, depth + 1) for item in value]
        if isinstance(value, dict):
            result: dict[str, JsonValue] = {}
            for key, item in value.items():
                if any(0xD800 <= ord(character) <= 0xDFFF for character in key):
                    raise StructuredOutputError("structured output contained invalid Unicode")
                result[key] = validate(item, depth + 1)
            return result
        raise StructuredOutputError("structured output contained an unsupported JSON value")

    return validate(parsed, 1)


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
