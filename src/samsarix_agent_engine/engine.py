# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Stateful agent and orchestration primitives."""

from __future__ import annotations

import asyncio
import copy
import inspect
import json
import re
from collections import OrderedDict, deque
from collections.abc import AsyncIterator, Callable, Sequence
from datetime import UTC, datetime
from time import perf_counter
from typing import NoReturn, TypeVar

from .errors import (
    BudgetExceededError,
    ConfigurationError,
    GuardrailError,
    InputValidationError,
    ProviderError,
    SamsarixAgentError,
    StructuredOutputError,
    ToolApprovalError,
    ToolExecutionError,
)
from .models import (
    AgentMetrics,
    ApprovalDecision,
    ApprovalHandler,
    ApprovalRequest,
    ChatMessage,
    Guardrail,
    GuardrailContext,
    GuardrailResult,
    JsonValue,
    ProviderResponse,
    ProviderStreamChunk,
    RunEvent,
    RunEventType,
    SessionSnapshot,
    ToolCall,
    ToolDefinition,
    ToolMessage,
    ToolProviderResponse,
    parse_json_output,
)
from .providers import BaseLLMProvider, EchoProvider

_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_StructuredT = TypeVar("_StructuredT")


class Agent:
    """A named prompt, provider, and bounded in-memory conversation history."""

    def __init__(
        self,
        *,
        name: str,
        model: str,
        system_prompt: str,
        provider: BaseLLMProvider,
        provider_name: str,
        max_history_messages: int,
        max_sessions: int,
        max_input_chars: int,
        max_requests_per_session: int,
        max_output_tokens: int,
        max_response_chars: int,
        max_events: int,
        max_tool_rounds: int,
        max_tool_calls: int,
        max_tool_argument_chars: int,
        max_tool_result_chars: int,
        temperature: float,
        input_guardrails: Sequence[Guardrail],
        output_guardrails: Sequence[Guardrail],
    ) -> None:
        self.name = name
        self.model = model
        self.system_prompt = system_prompt
        self.provider_name = provider_name
        self._provider = provider
        self._max_history_messages = max_history_messages
        self._max_sessions = max_sessions
        self._max_input_chars = max_input_chars
        self._max_requests_per_session = max_requests_per_session
        self._max_output_tokens = max_output_tokens
        self._max_response_chars = max_response_chars
        self._max_events = max_events
        self._max_tool_rounds = max_tool_rounds
        self._max_tool_calls = max_tool_calls
        self._max_tool_argument_chars = max_tool_argument_chars
        self._max_tool_result_chars = max_tool_result_chars
        self._temperature = temperature
        self._input_guardrails = tuple(input_guardrails)
        self._output_guardrails = tuple(output_guardrails)
        self._history: OrderedDict[str, list[ChatMessage]] = OrderedDict()
        self._request_counts: dict[str, int] = {}
        self._metrics = AgentMetrics()
        self._events: deque[RunEvent] = deque(maxlen=max_events)
        self._lock = asyncio.Lock()

    async def invoke(self, prompt: str, *, session_id: str = "default") -> str:
        """Invoke the provider and append a successful turn to session history.

        One agent serializes calls so turns cannot be reordered within a session.
        Create separate agents when independent concurrent calls are required.
        """

        return await self._invoke_validated(
            prompt,
            session_id=session_id,
            validator=lambda content: content,
        )

    async def invoke_json(
        self,
        prompt: str,
        *,
        session_id: str = "default",
        max_depth: int = 64,
    ) -> JsonValue:
        """Invoke once and return strict JSON without committing invalid output."""

        max_depth = self._validate_json_depth(max_depth)

        return await self._invoke_validated(
            prompt,
            session_id=session_id,
            validator=lambda content: parse_json_output(content, max_depth=max_depth),
        )

    async def invoke_structured(
        self,
        prompt: str,
        validator: Callable[[JsonValue], _StructuredT],
        *,
        session_id: str = "default",
        max_depth: int = 64,
    ) -> _StructuredT:
        """Return caller-validated JSON, compatible with dataclasses or Pydantic.

        The validator is synchronous and receives already parsed strict JSON.
        Its exceptions are sanitized so model content or application internals do
        not leak through the public error contract.
        """

        if not callable(validator):
            raise InputValidationError("validator must be callable")
        max_depth = self._validate_json_depth(max_depth)

        def validate(content: str) -> _StructuredT:
            parsed = parse_json_output(content, max_depth=max_depth)
            try:
                return validator(parsed)
            except Exception as exc:
                raise StructuredOutputError("structured output validation failed") from exc

        return await self._invoke_validated(prompt, session_id=session_id, validator=validate)

    async def run_tools(
        self,
        prompt: str,
        tools: Sequence[ToolDefinition],
        *,
        approval_handler: ApprovalHandler | None = None,
        session_id: str = "default",
    ) -> str:
        """Run a bounded provider/tool loop and return one final text response.

        Tool handlers are opt-in local code. Approval is required by default for
        every definition, model arguments are strict JSON objects, execution is
        sequential, and only the user's prompt plus final answer enter history.
        """

        prompt = self._validate_prompt(prompt)
        session_id = self._validate_session_id(session_id)
        tools = self._validate_tools(tools)
        if approval_handler is not None and not callable(approval_handler):
            raise InputValidationError("approval_handler must be callable")
        tools_by_name = {tool.name: tool for tool in tools}

        async with self._lock:
            self._run_guardrails(
                self._input_guardrails,
                prompt,
                GuardrailContext(
                    agent_name=self.name,
                    session_id=session_id,
                    stage="input",
                    provider_name=self.provider_name,
                    model=self.model,
                ),
            )
            self._ensure_session(session_id)
            messages = self._build_tool_messages(session_id, prompt)
            used_tool_calls = 0

            for round_number in range(1, self._max_tool_rounds + 1):
                request_number = self._begin_request(session_id)
                self._record_event(
                    "request.started",
                    session_id=session_id,
                    request_number=request_number,
                )
                started = perf_counter()
                final_content: str | None = None
                try:
                    raw_response = await self._provider.invoke_tools(
                        messages,
                        self.model,
                        tools,
                        max_tokens=self._max_output_tokens,
                        temperature=self._temperature,
                    )
                    if not isinstance(raw_response, ToolProviderResponse):
                        raise ProviderError("custom provider returned an invalid tool response")
                    response = raw_response
                    if response.content is not None and (
                        len(response.content) > self._max_response_chars
                    ):
                        raise ProviderError(
                            "provider response exceeded the configured character limit"
                        )
                    self._metrics.input_tokens += response.input_tokens or 0
                    self._metrics.output_tokens += response.output_tokens or 0

                    if response.tool_calls:
                        if round_number >= self._max_tool_rounds:
                            raise BudgetExceededError(
                                "tool loop reached its model-round limit before a final response"
                            )
                        if self._request_counts[session_id] >= self._max_requests_per_session:
                            raise BudgetExceededError(
                                "tool loop lacks request budget for a final model response"
                            )
                        if used_tool_calls + len(response.tool_calls) > self._max_tool_calls:
                            raise BudgetExceededError("tool loop reached its tool-call limit")
                        if any(
                            len(call.arguments) > self._max_tool_argument_chars
                            for call in response.tool_calls
                        ):
                            raise BudgetExceededError(
                                "tool arguments exceeded the configured character limit"
                            )
                        messages.append(
                            ToolMessage(
                                role="assistant",
                                content=response.content,
                                tool_calls=response.tool_calls,
                            )
                        )
                        for call in response.tool_calls:
                            result_message = await self._execute_tool_call(
                                call,
                                tools_by_name,
                                approval_handler=approval_handler,
                                session_id=session_id,
                                round_number=round_number,
                                request_number=request_number,
                            )
                            messages.append(result_message)
                            used_tool_calls += 1
                        self._metrics.successes += 1
                    else:
                        if response.content is None:  # pragma: no cover - model invariant
                            raise ProviderError("provider tool response contained no final text")
                        self._run_guardrails(
                            self._output_guardrails,
                            response.content,
                            GuardrailContext(
                                agent_name=self.name,
                                session_id=session_id,
                                stage="output",
                                provider_name=self.provider_name,
                                model=self.model,
                            ),
                            request_number=request_number,
                        )
                        self._record_success(session_id, prompt, response.content)
                        final_content = response.content
                except asyncio.CancelledError:
                    self._metrics.failures += 1
                    self._record_event(
                        "request.failed",
                        session_id=session_id,
                        request_number=request_number,
                        latency_ms=self._elapsed_ms(started),
                        error_type="CancelledError",
                    )
                    raise
                except SamsarixAgentError as exc:
                    self._metrics.failures += 1
                    self._record_event(
                        "request.failed",
                        session_id=session_id,
                        request_number=request_number,
                        latency_ms=self._elapsed_ms(started),
                        error_type=type(exc).__name__,
                    )
                    raise
                except Exception as exc:
                    self._metrics.failures += 1
                    self._record_event(
                        "request.failed",
                        session_id=session_id,
                        request_number=request_number,
                        latency_ms=self._elapsed_ms(started),
                        error_type="ProviderError",
                    )
                    raise ProviderError("custom provider tool invocation failed") from exc
                finally:
                    self._metrics.last_latency_ms = self._elapsed_ms(started)

                self._record_event(
                    "request.succeeded",
                    session_id=session_id,
                    request_number=request_number,
                    latency_ms=self._metrics.last_latency_ms,
                )
                if final_content is not None:
                    return final_content

        raise BudgetExceededError("tool loop ended without a final response")

    async def stream(
        self,
        prompt: str,
        *,
        session_id: str = "default",
    ) -> AsyncIterator[str]:
        """Yield bounded response deltas and commit history only after completion."""

        prompt = self._validate_prompt(prompt)
        session_id = self._validate_session_id(session_id)
        if self._output_guardrails:
            raise ConfigurationError(
                "streaming is unavailable when output guardrails are configured; use invoke()"
            )
        async with self._lock:
            self._run_guardrails(
                self._input_guardrails,
                prompt,
                GuardrailContext(
                    agent_name=self.name,
                    session_id=session_id,
                    stage="input",
                    provider_name=self.provider_name,
                    model=self.model,
                ),
            )
            request_number = self._begin_request(session_id)
            self._record_event(
                "request.started",
                session_id=session_id,
                request_number=request_number,
            )
            messages = self._build_messages(session_id, prompt)
            started = perf_counter()
            parts: list[str] = []
            character_count = 0
            final_seen = False
            try:
                async for chunk in self._provider.stream(
                    messages,
                    self.model,
                    max_tokens=self._max_output_tokens,
                    temperature=self._temperature,
                ):
                    if not isinstance(chunk, ProviderStreamChunk):
                        raise ProviderError("custom provider emitted an invalid stream event")
                    if final_seen:
                        raise ProviderError("provider emitted data after the final stream event")
                    if chunk.delta:
                        character_count += len(chunk.delta)
                        if character_count > self._max_response_chars:
                            raise ProviderError(
                                "provider response exceeded the configured character limit"
                            )
                        parts.append(chunk.delta)
                        yield chunk.delta
                    if chunk.final:
                        final_seen = True
                        self._metrics.input_tokens += chunk.input_tokens or 0
                        self._metrics.output_tokens += chunk.output_tokens or 0
                if not final_seen:
                    raise ProviderError("provider stream ended without a final event")
                content = "".join(parts)
                if not content:
                    raise ProviderError("provider stream contained no text content")
                self._record_success(session_id, prompt, content)
            except (asyncio.CancelledError, GeneratorExit):
                self._metrics.failures += 1
                self._record_event(
                    "request.failed",
                    session_id=session_id,
                    request_number=request_number,
                    latency_ms=self._elapsed_ms(started),
                    error_type="CancelledError",
                )
                raise
            except SamsarixAgentError as exc:
                self._metrics.failures += 1
                self._record_event(
                    "request.failed",
                    session_id=session_id,
                    request_number=request_number,
                    latency_ms=self._elapsed_ms(started),
                    error_type=type(exc).__name__,
                )
                raise
            except Exception as exc:
                self._metrics.failures += 1
                self._record_event(
                    "request.failed",
                    session_id=session_id,
                    request_number=request_number,
                    latency_ms=self._elapsed_ms(started),
                    error_type="ProviderError",
                )
                raise ProviderError("custom provider streaming failed") from exc
            finally:
                self._metrics.last_latency_ms = self._elapsed_ms(started)

            self._record_event(
                "request.succeeded",
                session_id=session_id,
                request_number=request_number,
                latency_ms=self._metrics.last_latency_ms,
            )

    async def _invoke_validated(
        self,
        prompt: str,
        *,
        session_id: str,
        validator: Callable[[str], _StructuredT],
    ) -> _StructuredT:
        prompt = self._validate_prompt(prompt)
        session_id = self._validate_session_id(session_id)
        async with self._lock:
            self._run_guardrails(
                self._input_guardrails,
                prompt,
                GuardrailContext(
                    agent_name=self.name,
                    session_id=session_id,
                    stage="input",
                    provider_name=self.provider_name,
                    model=self.model,
                ),
            )
            request_number = self._begin_request(session_id)
            self._record_event(
                "request.started",
                session_id=session_id,
                request_number=request_number,
            )
            messages = self._build_messages(session_id, prompt)
            started = perf_counter()
            try:
                raw_response = await self._provider.invoke(
                    messages,
                    self.model,
                    max_tokens=self._max_output_tokens,
                    temperature=self._temperature,
                )
                response = self._normalize_provider_response(raw_response)
                if len(response.content) > self._max_response_chars:
                    raise ProviderError("provider response exceeded the configured character limit")
                self._metrics.input_tokens += response.input_tokens or 0
                self._metrics.output_tokens += response.output_tokens or 0
                self._run_guardrails(
                    self._output_guardrails,
                    response.content,
                    GuardrailContext(
                        agent_name=self.name,
                        session_id=session_id,
                        stage="output",
                        provider_name=self.provider_name,
                        model=self.model,
                    ),
                    request_number=request_number,
                )
                result = validator(response.content)
            except asyncio.CancelledError:
                self._metrics.failures += 1
                self._record_event(
                    "request.failed",
                    session_id=session_id,
                    request_number=request_number,
                    latency_ms=self._elapsed_ms(started),
                    error_type="CancelledError",
                )
                raise
            except SamsarixAgentError as exc:
                self._metrics.failures += 1
                self._record_event(
                    "request.failed",
                    session_id=session_id,
                    request_number=request_number,
                    latency_ms=self._elapsed_ms(started),
                    error_type=type(exc).__name__,
                )
                raise
            except Exception as exc:
                self._metrics.failures += 1
                self._record_event(
                    "request.failed",
                    session_id=session_id,
                    request_number=request_number,
                    latency_ms=self._elapsed_ms(started),
                    error_type="ProviderError",
                )
                raise ProviderError("custom provider invocation failed") from exc
            finally:
                self._metrics.last_latency_ms = self._elapsed_ms(started)

            self._record_success(session_id, prompt, response.content)
            self._record_event(
                "request.succeeded",
                session_id=session_id,
                request_number=request_number,
                latency_ms=self._metrics.last_latency_ms,
            )
            return result

    def _begin_request(self, session_id: str) -> int:
        self._ensure_session(session_id)
        request_count = self._request_counts[session_id]
        if request_count >= self._max_requests_per_session:
            raise BudgetExceededError(
                f"session {session_id!r} reached its request limit; clear it before retrying"
            )
        self._request_counts[session_id] = request_count + 1
        self._metrics.requests += 1
        return self._metrics.requests

    def _record_success(self, session_id: str, prompt: str, content: str) -> None:
        history = self._history[session_id]
        history.extend(
            [
                ChatMessage(role="user", content=prompt),
                ChatMessage(role="assistant", content=content),
            ]
        )
        if len(history) > self._max_history_messages:
            overflow = len(history) - self._max_history_messages
            del history[: overflow + (overflow % 2)]
        self._history.move_to_end(session_id)
        self._metrics.successes += 1

    def history(self, session_id: str = "default") -> tuple[ChatMessage, ...]:
        """Return an immutable snapshot of one session's successful turns."""

        session_id = self._validate_session_id(session_id)
        return tuple(self._history.get(session_id, ()))

    def clear_history(self, session_id: str | None = None) -> None:
        """Clear one session, or every session when ``session_id`` is omitted."""

        if session_id is None:
            self._history.clear()
            self._request_counts.clear()
            return
        session_id = self._validate_session_id(session_id)
        self._history.pop(session_id, None)
        self._request_counts.pop(session_id, None)

    async def export_session(self, session_id: str = "default") -> SessionSnapshot:
        """Return a consistent portable snapshot of one existing session."""

        session_id = self._validate_session_id(session_id)
        async with self._lock:
            if session_id not in self._history:
                raise InputValidationError(f"session {session_id!r} does not exist")
            snapshot = SessionSnapshot(
                session_id=session_id,
                messages=tuple(self._history[session_id]),
                request_count=self._request_counts[session_id],
            )
            self._record_event("session.exported", session_id=session_id)
            return snapshot

    async def import_session(
        self,
        snapshot: SessionSnapshot,
        *,
        session_id: str | None = None,
        replace: bool = False,
    ) -> None:
        """Restore validated state without performing file I/O or a provider call."""

        if not isinstance(snapshot, SessionSnapshot):
            raise InputValidationError("snapshot must be a SessionSnapshot")
        target = self._validate_session_id(session_id or snapshot.session_id)
        if len(snapshot.messages) > self._max_history_messages:
            raise InputValidationError("snapshot exceeds this agent's history limit")
        if snapshot.request_count > self._max_requests_per_session:
            raise InputValidationError("snapshot exceeds this agent's request limit")
        if not isinstance(replace, bool):
            raise InputValidationError("replace must be a boolean")
        async with self._lock:
            if target in self._history and not replace:
                raise InputValidationError(f"session {target!r} already exists")
            if target not in self._history:
                self._ensure_session(target)
            self._history[target] = list(snapshot.messages)
            self._request_counts[target] = snapshot.request_count
            self._history.move_to_end(target)
            self._record_event("session.imported", session_id=target)

    def events(self, session_id: str | None = None) -> tuple[RunEvent, ...]:
        """Return bounded content-free lifecycle events, optionally for one session."""

        if session_id is None:
            return tuple(self._events)
        session_id = self._validate_session_id(session_id)
        return tuple(event for event in self._events if event.session_id == session_id)

    def clear_events(self) -> None:
        """Clear the local audit-event buffer without changing sessions or metrics."""

        self._events.clear()

    def get_metrics(self) -> dict[str, int | float | None]:
        """Return local request and provider-reported token counters."""

        return self._metrics.as_dict()

    def _ensure_session(self, session_id: str) -> None:
        if session_id in self._history:
            self._history.move_to_end(session_id)
            return
        while len(self._history) >= self._max_sessions:
            evicted, _ = self._history.popitem(last=False)
            self._request_counts.pop(evicted, None)
        self._history[session_id] = []
        self._request_counts[session_id] = 0

    def _run_guardrails(
        self,
        guardrails: Sequence[Guardrail],
        content: str,
        context: GuardrailContext,
        *,
        request_number: int | None = None,
    ) -> None:
        for guardrail in guardrails:
            try:
                decision = guardrail(content, context)
                if isinstance(decision, bool):
                    result = GuardrailResult(allowed=decision)
                elif isinstance(decision, GuardrailResult):
                    result = decision
                else:
                    raise TypeError("unsupported guardrail result")
            except Exception as exc:
                self._record_event(
                    "guardrail.failed",
                    session_id=context.session_id,
                    request_number=request_number,
                    error_type="GuardrailCallbackError",
                )
                raise GuardrailError(
                    f"{context.stage} guardrail failed",
                    stage=context.stage,
                    blocked=False,
                ) from exc
            if result.allowed:
                continue
            self._metrics.guardrail_blocks += 1
            self._record_event(
                "guardrail.blocked",
                session_id=context.session_id,
                request_number=request_number,
                error_type="GuardrailError",
            )
            suffix = f": {result.reason}" if result.reason else ""
            raise GuardrailError(
                f"{context.stage} blocked by guardrail{suffix}",
                stage=context.stage,
                blocked=True,
            )

    async def _execute_tool_call(
        self,
        call: ToolCall,
        tools_by_name: dict[str, ToolDefinition],
        *,
        approval_handler: ApprovalHandler | None,
        session_id: str,
        round_number: int,
        request_number: int,
    ) -> ToolMessage:
        self._record_event(
            "tool.requested",
            session_id=session_id,
            request_number=request_number,
            tool_name=call.name,
            tool_call_id=call.call_id,
        )
        tool = tools_by_name.get(call.name)
        if tool is None:
            self._metrics.tool_failures += 1
            self._record_event(
                "tool.failed",
                session_id=session_id,
                request_number=request_number,
                error_type="UnavailableToolError",
                tool_name=call.name,
                tool_call_id=call.call_id,
            )
            raise ToolExecutionError(f"model requested unavailable tool {call.name!r}")

        try:
            parsed_arguments = parse_json_output(call.arguments, max_depth=32)
        except StructuredOutputError as exc:
            self._metrics.tool_failures += 1
            self._record_event(
                "tool.failed",
                session_id=session_id,
                request_number=request_number,
                error_type="InvalidToolArguments",
                tool_name=call.name,
                tool_call_id=call.call_id,
            )
            raise ToolExecutionError("model supplied invalid bounded JSON tool arguments") from exc
        if not isinstance(parsed_arguments, dict):
            self._metrics.tool_failures += 1
            self._record_event(
                "tool.failed",
                session_id=session_id,
                request_number=request_number,
                error_type="InvalidToolArguments",
                tool_name=call.name,
                tool_call_id=call.call_id,
            )
            raise ToolExecutionError("model tool arguments must be a JSON object")

        if tool.requires_approval:
            if approval_handler is None:
                self._deny_tool(call, session_id, request_number, reason=None)
            request = ApprovalRequest(
                tool_name=call.name,
                tool_call_id=call.call_id,
                arguments=copy.deepcopy(parsed_arguments),
                agent_name=self.name,
                session_id=session_id,
                round_number=round_number,
            )
            try:
                approval = approval_handler(request)
                if inspect.isawaitable(approval):
                    approval = await approval
                if isinstance(approval, bool):
                    decision = ApprovalDecision(approved=approval)
                elif isinstance(approval, ApprovalDecision):
                    decision = approval
                else:
                    raise TypeError("unsupported approval result")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._metrics.tool_failures += 1
                self._record_event(
                    "tool.failed",
                    session_id=session_id,
                    request_number=request_number,
                    error_type="ApprovalHandlerError",
                    tool_name=call.name,
                    tool_call_id=call.call_id,
                )
                raise ToolApprovalError(
                    "tool approval handler failed",
                    tool_name=call.name,
                    tool_call_id=call.call_id,
                ) from exc
            if not decision.approved:
                self._deny_tool(call, session_id, request_number, reason=decision.reason)
            self._record_event(
                "tool.approved",
                session_id=session_id,
                request_number=request_number,
                tool_name=call.name,
                tool_call_id=call.call_id,
            )

        try:
            result = tool.handler(copy.deepcopy(parsed_arguments))
            if inspect.isawaitable(result):
                result = await result
            serialized = json.dumps(
                result,
                allow_nan=False,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
            parse_json_output(serialized, max_depth=32)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._metrics.tool_failures += 1
            self._record_event(
                "tool.failed",
                session_id=session_id,
                request_number=request_number,
                error_type="ToolExecutionError",
                tool_name=call.name,
                tool_call_id=call.call_id,
            )
            raise ToolExecutionError("tool handler failed or returned invalid JSON") from exc
        if len(serialized) > self._max_tool_result_chars:
            self._metrics.tool_failures += 1
            self._record_event(
                "tool.failed",
                session_id=session_id,
                request_number=request_number,
                error_type="ToolResultBudgetError",
                tool_name=call.name,
                tool_call_id=call.call_id,
            )
            raise BudgetExceededError("tool result exceeded the configured character limit")

        self._metrics.tool_calls += 1
        self._record_event(
            "tool.succeeded",
            session_id=session_id,
            request_number=request_number,
            tool_name=call.name,
            tool_call_id=call.call_id,
        )
        return ToolMessage(role="tool", content=serialized, tool_call_id=call.call_id)

    def _deny_tool(
        self,
        call: ToolCall,
        session_id: str,
        request_number: int,
        *,
        reason: str | None,
    ) -> NoReturn:
        self._metrics.tool_denials += 1
        self._record_event(
            "tool.denied",
            session_id=session_id,
            request_number=request_number,
            error_type="ToolApprovalError",
            tool_name=call.name,
            tool_call_id=call.call_id,
        )
        suffix = f": {reason}" if reason else ""
        raise ToolApprovalError(
            f"tool call requires approval or was denied{suffix}",
            tool_name=call.name,
            tool_call_id=call.call_id,
        )

    def _record_event(
        self,
        event_type: RunEventType,
        *,
        session_id: str,
        request_number: int | None = None,
        latency_ms: float | None = None,
        error_type: str | None = None,
        tool_name: str | None = None,
        tool_call_id: str | None = None,
    ) -> None:
        self._events.append(
            RunEvent(
                event_type=event_type,
                occurred_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                agent_name=self.name,
                session_id=session_id,
                provider_name=self.provider_name,
                model=self.model,
                request_number=request_number,
                latency_ms=latency_ms,
                error_type=error_type,
                tool_name=tool_name,
                tool_call_id=tool_call_id,
            )
        )

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        return round((perf_counter() - started) * 1_000, 3)

    def _build_messages(self, session_id: str, prompt: str) -> list[ChatMessage]:
        messages: list[ChatMessage] = []
        if self.system_prompt:
            messages.append(ChatMessage(role="system", content=self.system_prompt))
        messages.extend(self._history[session_id])
        messages.append(ChatMessage(role="user", content=prompt))
        return messages

    def _build_tool_messages(self, session_id: str, prompt: str) -> list[ToolMessage]:
        messages: list[ToolMessage] = []
        if self.system_prompt:
            messages.append(ToolMessage(role="system", content=self.system_prompt))
        messages.extend(
            ToolMessage(role=message.role, content=message.content)
            for message in self._history[session_id]
        )
        messages.append(ToolMessage(role="user", content=prompt))
        return messages

    @staticmethod
    def _validate_tools(tools: object) -> tuple[ToolDefinition, ...]:
        if isinstance(tools, (str, bytes)) or not isinstance(tools, Sequence):
            raise InputValidationError("tools must be a sequence of ToolDefinition values")
        result = tuple(tools)
        if (
            not result
            or len(result) > 32
            or any(not isinstance(tool, ToolDefinition) for tool in result)
        ):
            raise InputValidationError("tools must contain 1-32 ToolDefinition values")
        names = [tool.name for tool in result]
        if len(names) != len(set(names)):
            raise InputValidationError("tool names must be unique")
        return result

    @staticmethod
    def _normalize_provider_response(raw: ProviderResponse | str) -> ProviderResponse:
        if isinstance(raw, ProviderResponse):
            return raw
        if isinstance(raw, str) and raw:
            return ProviderResponse(content=raw)
        raise ProviderError("provider returned an empty or unsupported response")

    def _validate_prompt(self, prompt: str) -> str:
        if not isinstance(prompt, str) or not prompt.strip():
            raise InputValidationError("prompt must be a non-empty string")
        if len(prompt) > self._max_input_chars:
            raise InputValidationError(
                f"prompt exceeds the configured {self._max_input_chars}-character limit"
            )
        return prompt

    @staticmethod
    def _validate_session_id(session_id: str) -> str:
        if not isinstance(session_id, str) or not session_id or len(session_id) > 128:
            raise InputValidationError("session_id must contain between 1 and 128 characters")
        if any(ord(character) < 32 for character in session_id):
            raise InputValidationError("session_id must not contain control characters")
        return session_id

    @staticmethod
    def _validate_json_depth(max_depth: int) -> int:
        if (
            isinstance(max_depth, bool)
            or not isinstance(max_depth, int)
            or not 1 <= max_depth <= 256
        ):
            raise InputValidationError("max_depth must be an integer between 1 and 256")
        return max_depth


class LLMAgentEngine:
    """Registry and factory for bounded agents."""

    def __init__(
        self,
        *,
        default_provider: str = "echo",
        max_history_messages: int = 20,
        max_sessions: int = 100,
        max_input_chars: int = 20_000,
        max_requests_per_session: int = 100,
        max_output_tokens: int = 1_024,
        max_response_chars: int = 200_000,
        max_events: int = 1_000,
        max_tool_rounds: int = 4,
        max_tool_calls: int = 8,
        max_tool_argument_chars: int = 20_000,
        max_tool_result_chars: int = 20_000,
        temperature: float = 0.7,
    ) -> None:
        if not isinstance(max_history_messages, int) or not 2 <= max_history_messages <= 1_000:
            raise ConfigurationError("max_history_messages must be between 2 and 1000")
        if not isinstance(max_sessions, int) or not 1 <= max_sessions <= 10_000:
            raise ConfigurationError("max_sessions must be between 1 and 10000")
        if not isinstance(max_input_chars, int) or not 1 <= max_input_chars <= 1_000_000:
            raise ConfigurationError("max_input_chars must be between 1 and 1000000")
        if (
            not isinstance(max_requests_per_session, int)
            or not 1 <= max_requests_per_session <= 100_000
        ):
            raise ConfigurationError("max_requests_per_session must be between 1 and 100000")
        if not isinstance(max_output_tokens, int) or not 1 <= max_output_tokens <= 131_072:
            raise ConfigurationError("max_output_tokens must be between 1 and 131072")
        if not isinstance(max_response_chars, int) or not 1 <= max_response_chars <= 1_000_000:
            raise ConfigurationError("max_response_chars must be between 1 and 1000000")
        if not isinstance(max_events, int) or not 1 <= max_events <= 100_000:
            raise ConfigurationError("max_events must be between 1 and 100000")
        if not isinstance(max_tool_rounds, int) or not 1 <= max_tool_rounds <= 16:
            raise ConfigurationError("max_tool_rounds must be between 1 and 16")
        if not isinstance(max_tool_calls, int) or not 1 <= max_tool_calls <= 128:
            raise ConfigurationError("max_tool_calls must be between 1 and 128")
        if (
            not isinstance(max_tool_argument_chars, int)
            or not 2 <= max_tool_argument_chars <= 100_000
        ):
            raise ConfigurationError("max_tool_argument_chars must be between 2 and 100000")
        if (
            not isinstance(max_tool_result_chars, int)
            or not 1 <= max_tool_result_chars <= 1_000_000
        ):
            raise ConfigurationError("max_tool_result_chars must be between 1 and 1000000")
        if not isinstance(temperature, (int, float)) or not 0 <= temperature <= 2:
            raise ConfigurationError("temperature must be between 0 and 2")

        self.default_provider = self._validate_provider_name(default_provider)
        self._providers: dict[str, BaseLLMProvider] = {"echo": EchoProvider()}
        self._max_history_messages = max_history_messages
        self._max_sessions = max_sessions
        self._max_input_chars = max_input_chars
        self._max_requests_per_session = max_requests_per_session
        self._max_output_tokens = max_output_tokens
        self._max_response_chars = max_response_chars
        self._max_events = max_events
        self._max_tool_rounds = max_tool_rounds
        self._max_tool_calls = max_tool_calls
        self._max_tool_argument_chars = max_tool_argument_chars
        self._max_tool_result_chars = max_tool_result_chars
        self._temperature = float(temperature)
        self._managed_providers: dict[int, BaseLLMProvider] = {
            id(self._providers["echo"]): self._providers["echo"]
        }
        self._closed = False

    def register_provider(self, name: str, provider: BaseLLMProvider) -> None:
        """Register or intentionally replace a provider under a stable name."""

        name = self._validate_provider_name(name)
        if self._closed:
            raise ConfigurationError("engine is closed")
        if not isinstance(provider, BaseLLMProvider):
            raise ConfigurationError("provider must inherit from BaseLLMProvider")
        self._providers[name] = provider
        self._managed_providers.setdefault(id(provider), provider)

    def create_agent(
        self,
        *,
        name: str,
        model: str,
        system_prompt: str = "",
        provider: str | None = None,
        input_guardrails: Sequence[Guardrail] = (),
        output_guardrails: Sequence[Guardrail] = (),
    ) -> Agent:
        """Create an independent agent using a registered provider."""

        if self._closed:
            raise ConfigurationError("engine is closed")
        if not isinstance(name, str) or not _SAFE_NAME.fullmatch(name):
            raise InputValidationError(
                "agent name must be 1-64 letters, numbers, underscores, or hyphens"
            )
        if not isinstance(model, str) or not model.strip() or len(model) > 200:
            raise InputValidationError("model must be a non-empty string of at most 200 characters")
        if not isinstance(system_prompt, str) or len(system_prompt) > self._max_input_chars:
            raise InputValidationError("system_prompt must be a string within the input limit")
        provider_name = self._validate_provider_name(provider or self.default_provider)
        input_guardrails = self._validate_guardrails(input_guardrails, "input_guardrails")
        output_guardrails = self._validate_guardrails(output_guardrails, "output_guardrails")
        try:
            provider_instance = self._providers[provider_name]
        except KeyError as exc:
            available = ", ".join(sorted(self._providers))
            raise ConfigurationError(
                f"provider {provider_name!r} is not registered (available: {available})"
            ) from exc
        return Agent(
            name=name,
            model=model.strip(),
            system_prompt=system_prompt,
            provider=provider_instance,
            provider_name=provider_name,
            max_history_messages=self._max_history_messages,
            max_sessions=self._max_sessions,
            max_input_chars=self._max_input_chars,
            max_requests_per_session=self._max_requests_per_session,
            max_output_tokens=self._max_output_tokens,
            max_response_chars=self._max_response_chars,
            max_events=self._max_events,
            max_tool_rounds=self._max_tool_rounds,
            max_tool_calls=self._max_tool_calls,
            max_tool_argument_chars=self._max_tool_argument_chars,
            max_tool_result_chars=self._max_tool_result_chars,
            temperature=self._temperature,
            input_guardrails=input_guardrails,
            output_guardrails=output_guardrails,
        )

    async def close(self) -> None:
        """Close each distinct registered provider exactly once."""

        if self._closed:
            return
        self._closed = True
        first_error: Exception | None = None
        for provider in self._managed_providers.values():
            try:
                await provider.close()
            except Exception as exc:
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise ProviderError("provider cleanup failed") from first_error

    async def __aenter__(self) -> LLMAgentEngine:
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    @staticmethod
    def _validate_provider_name(name: str) -> str:
        if not isinstance(name, str) or not _SAFE_NAME.fullmatch(name):
            raise ConfigurationError(
                "provider name must be 1-64 letters, numbers, underscores, or hyphens"
            )
        return name

    @staticmethod
    def _validate_guardrails(
        guardrails: object,
        label: str,
    ) -> tuple[Guardrail, ...]:
        if isinstance(guardrails, (str, bytes)) or not isinstance(guardrails, Sequence):
            raise ConfigurationError(f"{label} must be a sequence of callables")
        result = tuple(guardrails)
        if len(result) > 32 or any(not callable(guardrail) for guardrail in result):
            raise ConfigurationError(f"{label} must contain at most 32 callables")
        return result


class AgentOrchestrator:
    """Small sequential collaboration helper with explicit amplification caps."""

    def __init__(self, *, max_agents: int = 8) -> None:
        if not isinstance(max_agents, int) or not 1 <= max_agents <= 32:
            raise ConfigurationError("max_agents must be between 1 and 32")
        self.max_agents = max_agents
        self._agents: list[Agent] = []

    def add_agent(self, agent: Agent) -> None:
        if not isinstance(agent, Agent):
            raise ConfigurationError("orchestrator accepts Agent instances only")
        if len(self._agents) >= self.max_agents:
            raise BudgetExceededError("orchestrator reached its agent limit")
        if any(existing.name == agent.name for existing in self._agents):
            raise ConfigurationError(f"agent {agent.name!r} is already registered")
        self._agents.append(agent)

    async def collective_loop(
        self,
        *,
        prompt: str,
        max_iterations: int = 1,
        session_id: str = "collective",
    ) -> str:
        """Run agents sequentially and return a labeled transcript.

        The hard five-iteration and ``max_agents`` limits bound accidental API
        amplification. Each call is still billed by the configured provider.
        """

        if not self._agents:
            raise ConfigurationError("orchestrator has no agents")
        if not isinstance(max_iterations, int) or not 1 <= max_iterations <= 5:
            raise ConfigurationError("max_iterations must be between 1 and 5")
        if not isinstance(prompt, str) or not prompt.strip():
            raise InputValidationError("prompt must be a non-empty string")

        transcript: list[str] = []
        current_prompt = prompt
        for iteration in range(max_iterations):
            for agent in self._agents:
                response = await agent.invoke(
                    current_prompt,
                    session_id=f"{session_id}:{iteration}:{agent.name}",
                )
                transcript.append(f"{agent.name}: {response}")
                current_prompt = (
                    f"Original task: {prompt}\n\nPrior contribution from {agent.name}:\n{response}"
                )
        return "\n".join(transcript)

    @property
    def agents(self) -> Sequence[Agent]:
        return tuple(self._agents)
