# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Small, provider-neutral data models used by the public API."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
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
    "tool.requested",
    "tool.approved",
    "tool.denied",
    "tool.succeeded",
    "tool.failed",
]
ToolMessageRole = Literal["system", "user", "assistant", "tool"]
_SAFE_TOOL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


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
    tool_name: str | None = None
    tool_call_id: str | None = None

    def __post_init__(self) -> None:
        if self.event_type not in {
            "request.started",
            "request.succeeded",
            "request.failed",
            "guardrail.blocked",
            "guardrail.failed",
            "session.exported",
            "session.imported",
            "tool.requested",
            "tool.approved",
            "tool.denied",
            "tool.succeeded",
            "tool.failed",
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
        if (self.tool_name is None) != (self.tool_call_id is None):
            raise InputValidationError("tool_name and tool_call_id must be supplied together")
        if self.tool_name is not None and not _SAFE_TOOL_NAME.fullmatch(self.tool_name):
            raise InputValidationError("event tool_name was invalid")
        if self.tool_call_id is not None and (
            not self.tool_call_id
            or len(self.tool_call_id) > 128
            or any(ord(character) < 32 for character in self.tool_call_id)
        ):
            raise InputValidationError("event tool_call_id was invalid")

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
            "tool_name": self.tool_name,
            "tool_call_id": self.tool_call_id,
        }


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One provider-requested function call with untrusted raw JSON arguments."""

    call_id: str
    name: str
    arguments: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.call_id, str)
            or not self.call_id
            or len(self.call_id) > 128
            or any(ord(character) < 32 for character in self.call_id)
        ):
            raise InputValidationError("tool call id must contain 1-128 safe characters")
        if not isinstance(self.name, str) or not _SAFE_TOOL_NAME.fullmatch(self.name):
            raise InputValidationError(
                "tool name must be 1-64 letters, numbers, underscores, or hyphens"
            )
        if (
            not isinstance(self.arguments, str)
            or not self.arguments
            or len(self.arguments) > 100_000
        ):
            raise InputValidationError("tool arguments must contain at most 100000 characters")

    def as_dict(self) -> dict[str, JsonValue]:
        """Return the OpenAI-compatible assistant tool-call representation."""

        return {
            "id": self.call_id,
            "type": "function",
            "function": {"name": self.name, "arguments": self.arguments},
        }


@dataclass(frozen=True, slots=True)
class ToolMessage:
    """Provider-neutral message used only inside an explicit tool loop."""

    role: ToolMessageRole
    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None

    def __post_init__(self) -> None:
        if self.role not in {"system", "user", "assistant", "tool"}:
            raise InputValidationError("unsupported tool message role")
        if self.content is not None and (not isinstance(self.content, str) or not self.content):
            raise InputValidationError("tool message content must be non-empty when supplied")
        if not isinstance(self.tool_calls, tuple) or any(
            not isinstance(call, ToolCall) for call in self.tool_calls
        ):
            raise InputValidationError("tool_calls must be a tuple of ToolCall values")
        if self.role in {"system", "user"} and (
            self.content is None or self.tool_calls or self.tool_call_id is not None
        ):
            raise InputValidationError("system and user tool messages require content only")
        if self.role == "assistant" and (
            (self.content is None and not self.tool_calls) or self.tool_call_id is not None
        ):
            raise InputValidationError("assistant tool messages require content or tool calls")
        if self.role == "tool" and (
            self.content is None
            or self.tool_calls
            or not isinstance(self.tool_call_id, str)
            or not self.tool_call_id
            or len(self.tool_call_id) > 128
            or any(ord(character) < 32 for character in self.tool_call_id)
        ):
            raise InputValidationError("tool result messages require content and tool_call_id")

    def as_dict(self) -> dict[str, JsonValue]:
        """Return the OpenAI-compatible tool-loop message representation."""

        result: dict[str, JsonValue] = {"role": self.role}
        if self.content is not None:
            result["content"] = self.content
        elif self.role == "assistant":
            result["content"] = None
        if self.tool_calls:
            result["tool_calls"] = [call.as_dict() for call in self.tool_calls]
        if self.tool_call_id is not None:
            result["tool_call_id"] = self.tool_call_id
        return result


ToolHandler: TypeAlias = Callable[[dict[str, JsonValue]], JsonValue | Awaitable[JsonValue]]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    """Bounded function-tool schema and local handler; approval defaults to required."""

    name: str
    description: str
    parameters: Mapping[str, JsonValue]
    handler: ToolHandler = field(repr=False, compare=False)
    requires_approval: bool = True
    strict: bool = True
    _parameters_json: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _SAFE_TOOL_NAME.fullmatch(self.name):
            raise InputValidationError(
                "tool name must be 1-64 letters, numbers, underscores, or hyphens"
            )
        if (
            not isinstance(self.description, str)
            or not self.description.strip()
            or len(self.description) > 1_024
        ):
            raise InputValidationError("tool description must contain 1-1024 characters")
        if not isinstance(self.parameters, Mapping):
            raise InputValidationError("tool parameters must be a JSON Schema object")
        if not callable(self.handler):
            raise InputValidationError("tool handler must be callable")
        if not isinstance(self.requires_approval, bool) or not isinstance(self.strict, bool):
            raise InputValidationError("tool policy flags must be booleans")
        try:
            parameters_json = json.dumps(
                self.parameters,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
            parsed = parse_json_output(parameters_json, max_depth=32)
        except (TypeError, ValueError, StructuredOutputError) as exc:
            raise InputValidationError("tool parameters must contain bounded JSON values") from exc
        if not isinstance(parsed, dict) or len(parameters_json) > 50_000:
            raise InputValidationError(
                "tool parameters must be a JSON object of at most 50000 characters"
            )
        object.__setattr__(self, "_parameters_json", parameters_json)

    def as_dict(self) -> dict[str, JsonValue]:
        """Return a detached OpenAI-compatible function-tool definition."""

        parameters = parse_json_output(self._parameters_json, max_depth=32)
        if not isinstance(parameters, dict):  # pragma: no cover - constructor invariant
            raise InputValidationError("tool parameters invariant failed")
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
                "strict": self.strict,
            },
        }


@dataclass(frozen=True, slots=True)
class ToolProviderResponse:
    """Normalized provider response containing either final text or tool calls."""

    content: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    model: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None

    def __post_init__(self) -> None:
        if self.content is not None and (not isinstance(self.content, str) or not self.content):
            raise InputValidationError("tool provider content must be non-empty when supplied")
        if not isinstance(self.tool_calls, tuple) or any(
            not isinstance(call, ToolCall) for call in self.tool_calls
        ):
            raise InputValidationError("tool provider calls must be a tuple of ToolCall values")
        if self.content is None and not self.tool_calls:
            raise InputValidationError(
                "tool provider response contained neither text nor tool calls"
            )
        for label, value in (
            ("input_tokens", self.input_tokens),
            ("output_tokens", self.output_tokens),
        ):
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise InputValidationError(f"{label} must be a non-negative integer")


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    """Content presented to a caller-owned approval handler before execution."""

    tool_name: str
    tool_call_id: str
    arguments: dict[str, JsonValue]
    agent_name: str
    session_id: str
    round_number: int


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    """Explicit caller-owned tool approval decision."""

    approved: bool
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.approved, bool):
            raise InputValidationError("approval decision must be a boolean")
        if self.reason is not None and (
            not isinstance(self.reason, str)
            or not self.reason.strip()
            or len(self.reason) > 500
            or any(ord(character) < 32 for character in self.reason)
        ):
            raise InputValidationError(
                "approval reason must be 1-500 characters without control characters"
            )
        if self.approved and self.reason is not None:
            raise InputValidationError("an approved decision must not include a reason")


ApprovalHandler: TypeAlias = Callable[
    [ApprovalRequest], ApprovalDecision | bool | Awaitable[ApprovalDecision | bool]
]


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
    tool_calls: int = 0
    tool_failures: int = 0
    tool_denials: int = 0
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
            "tool_calls": self.tool_calls,
            "tool_failures": self.tool_failures,
            "tool_denials": self.tool_denials,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "last_latency_ms": self.last_latency_ms,
        }
