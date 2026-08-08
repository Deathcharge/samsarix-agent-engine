# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Small, provider-neutral data models used by the public API."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, ClassVar, Literal, TypeAlias, cast

from .errors import InputValidationError, StructuredOutputError

Role = Literal["system", "user", "assistant"]
JsonValue: TypeAlias = bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"] | None
GuardrailStage = Literal["input", "output"]
RunEventType = Literal[
    "request.started",
    "request.succeeded",
    "request.failed",
    "guardrail.blocked",
    "guardrail.failed",
    "session.exported",
    "session.imported",
]


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


@dataclass(frozen=True, slots=True)
class GuardrailContext:
    """Non-content context supplied to a local guardrail."""

    agent_name: str
    session_id: str
    stage: GuardrailStage
    provider_name: str
    model: str


@dataclass(frozen=True, slots=True)
class GuardrailResult:
    """Explicit allow/block decision returned by a guardrail."""

    allowed: bool
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.allowed, bool):
            raise InputValidationError("guardrail allowed must be a boolean")
        if self.reason is not None and (
            not isinstance(self.reason, str)
            or not self.reason.strip()
            or len(self.reason) > 500
            or any(ord(character) < 32 for character in self.reason)
        ):
            raise InputValidationError(
                "guardrail reason must be 1-500 characters without control characters"
            )
        if self.allowed and self.reason is not None:
            raise InputValidationError("an allowed guardrail result must not include a reason")


Guardrail: TypeAlias = Callable[[str, GuardrailContext], GuardrailResult | bool]


@dataclass(frozen=True, slots=True)
class RunEvent:
    """Content-free local audit event for an agent request or session operation."""

    event_type: RunEventType
    occurred_at: str
    agent_name: str
    session_id: str
    provider_name: str
    model: str
    request_number: int | None = None
    latency_ms: float | None = None
    error_type: str | None = None

    def __post_init__(self) -> None:
        if self.event_type not in {
            "request.started",
            "request.succeeded",
            "request.failed",
            "guardrail.blocked",
            "guardrail.failed",
            "session.exported",
            "session.imported",
        }:
            raise InputValidationError("unsupported run event type")
        if self.request_number is not None and (
            isinstance(self.request_number, bool)
            or not isinstance(self.request_number, int)
            or self.request_number < 1
        ):
            raise InputValidationError("request_number must be a positive integer")
        if self.latency_ms is not None and (
            isinstance(self.latency_ms, bool)
            or not isinstance(self.latency_ms, (int, float))
            or not math.isfinite(self.latency_ms)
            or self.latency_ms < 0
        ):
            raise InputValidationError("latency_ms must be a finite non-negative number")

    def as_dict(self) -> dict[str, str | int | float | None]:
        """Return a stable content-free JSON representation."""

        return {
            "event_type": self.event_type,
            "occurred_at": self.occurred_at,
            "agent_name": self.agent_name,
            "session_id": self.session_id,
            "provider_name": self.provider_name,
            "model": self.model,
            "request_number": self.request_number,
            "latency_ms": self.latency_ms,
            "error_type": self.error_type,
        }


@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    """Portable, bounded successful-turn state with no provider credentials."""

    FORMAT: ClassVar[str] = "samsarix-agent-session"
    VERSION: ClassVar[int] = 1
    MAX_SERIALIZED_CHARS: ClassVar[int] = 1_000_000

    session_id: str
    messages: tuple[ChatMessage, ...]
    request_count: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.session_id, str)
            or not self.session_id
            or len(self.session_id) > 128
            or any(ord(character) < 32 for character in self.session_id)
        ):
            raise InputValidationError("snapshot session_id must contain 1-128 safe characters")
        if (
            isinstance(self.request_count, bool)
            or not isinstance(self.request_count, int)
            or not 0 <= self.request_count <= 100_000
        ):
            raise InputValidationError("snapshot request_count must be between 0 and 100000")
        if not isinstance(self.messages, tuple) or len(self.messages) > 1_000:
            raise InputValidationError("snapshot messages must be a tuple of at most 1000 items")
        if len(self.messages) % 2:
            raise InputValidationError(
                "snapshot messages must contain complete user/assistant turns"
            )
        content_chars = 0
        for index, message in enumerate(self.messages):
            expected_role = "user" if index % 2 == 0 else "assistant"
            if not isinstance(message, ChatMessage) or message.role != expected_role:
                raise InputValidationError(
                    "snapshot messages must alternate user and assistant roles"
                )
            content_chars += len(message.content)
            if content_chars > self.MAX_SERIALIZED_CHARS:
                raise InputValidationError("snapshot exceeds the serialized size limit")
        if len(self.to_json()) > self.MAX_SERIALIZED_CHARS:
            raise InputValidationError("snapshot exceeds the serialized size limit")

    def as_dict(self) -> dict[str, JsonValue]:
        """Return the versioned portable representation."""

        return {
            "format": self.FORMAT,
            "version": self.VERSION,
            "session_id": self.session_id,
            "request_count": self.request_count,
            "messages": [cast(JsonValue, message.as_dict()) for message in self.messages],
        }

    def to_json(self) -> str:
        """Serialize deterministically; callers choose where or whether to persist it."""

        return json.dumps(self.as_dict(), ensure_ascii=True, separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> SessionSnapshot:
        """Validate a snapshot decoded by a trusted or untrusted JSON parser."""

        if not isinstance(value, Mapping):
            raise InputValidationError("snapshot must be a JSON object")
        required = {"format", "version", "session_id", "request_count", "messages"}
        if set(value) != required:
            raise InputValidationError("snapshot fields did not match the supported format")
        if value["format"] != cls.FORMAT or value["version"] != cls.VERSION:
            raise InputValidationError("snapshot format or version is not supported")
        raw_messages = value["messages"]
        if not isinstance(raw_messages, list):
            raise InputValidationError("snapshot messages must be an array")
        messages: list[ChatMessage] = []
        for raw_message in raw_messages:
            if not isinstance(raw_message, dict) or set(raw_message) != {"role", "content"}:
                raise InputValidationError("snapshot contained an invalid message")
            role = raw_message["role"]
            content = raw_message["content"]
            if role not in {"user", "assistant"} or not isinstance(content, str):
                raise InputValidationError("snapshot contained an invalid message")
            messages.append(ChatMessage(role=role, content=content))
        session_id = value["session_id"]
        request_count = value["request_count"]
        if not isinstance(session_id, str):
            raise InputValidationError("snapshot session_id must be a string")
        if isinstance(request_count, bool) or not isinstance(request_count, int):
            raise InputValidationError("snapshot request_count must be an integer")
        return cls(
            session_id=session_id,
            messages=tuple(messages),
            request_count=request_count,
        )

    @classmethod
    def from_json(cls, serialized: str) -> SessionSnapshot:
        """Parse a bounded versioned snapshot without executing or importing content."""

        if (
            not isinstance(serialized, str)
            or not serialized
            or len(serialized) > cls.MAX_SERIALIZED_CHARS
        ):
            raise InputValidationError(
                "serialized snapshot must contain at most 1000000 characters"
            )
        try:
            parsed = parse_json_output(serialized, max_depth=8)
        except StructuredOutputError as exc:
            raise InputValidationError("snapshot was not valid bounded JSON") from exc
        if not isinstance(parsed, dict):
            raise InputValidationError("snapshot must be a JSON object")
        return cls.from_dict(parsed)


@dataclass(slots=True)
class AgentMetrics:
    """Local counters for one agent instance.

    Token counts are populated only when the provider reports them. They are not
    estimated or presented as billing data.
    """

    requests: int = 0
    successes: int = 0
    failures: int = 0
    guardrail_blocks: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    last_latency_ms: float | None = None

    def as_dict(self) -> dict[str, int | float | None]:
        """Return a stable, JSON-serializable snapshot."""

        return {
            "requests": self.requests,
            "successes": self.successes,
            "failures": self.failures,
            "guardrail_blocks": self.guardrail_blocks,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "last_latency_ms": self.last_latency_ms,
        }
