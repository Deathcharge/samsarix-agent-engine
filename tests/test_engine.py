from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from typing import cast

import pytest

from samsarix_agent_engine import (
    AgentOrchestrator,
    ApprovalDecision,
    ApprovalRequest,
    BaseLLMProvider,
    BudgetExceededError,
    ChatMessage,
    ConfigurationError,
    GuardrailContext,
    GuardrailError,
    GuardrailResult,
    InputValidationError,
    JsonValue,
    LLMAgentEngine,
    ProviderError,
    ProviderResponse,
    ProviderStreamChunk,
    SessionSnapshot,
    StructuredOutputError,
    ToolApprovalError,
    ToolCall,
    ToolDefinition,
    ToolExecutionError,
    ToolMessage,
    ToolProviderResponse,
)


class RecordingProvider(BaseLLMProvider):
    def __init__(self, response: str = "done") -> None:
        self.response = response
        self.calls: list[tuple[list[ChatMessage], str, int, float]] = []
        self.closed = 0

    async def invoke(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> ProviderResponse:
        self.calls.append((list(messages), model, max_tokens, temperature))
        return ProviderResponse(
            content=self.response,
            model=model,
            input_tokens=4,
            output_tokens=2,
        )

    async def close(self) -> None:
        self.closed += 1


class FailingProvider(BaseLLMProvider):
    def __init__(self, *, expected: bool) -> None:
        self.expected = expected

    async def invoke(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> ProviderResponse:
        del messages, model, max_tokens, temperature
        if self.expected:
            raise ProviderError("bounded failure")
        raise RuntimeError("secret-bearing custom failure")


class FailingCloseProvider(RecordingProvider):
    async def close(self) -> None:
        raise RuntimeError("secret-bearing cleanup failure")


class StreamingProvider(BaseLLMProvider):
    def __init__(
        self,
        chunks: tuple[ProviderStreamChunk | object, ...] | None = None,
    ) -> None:
        self.chunks = chunks or (
            ProviderStreamChunk(delta="hel"),
            ProviderStreamChunk(delta="lo"),
            ProviderStreamChunk(final=True, input_tokens=3, output_tokens=2),
        )
        self.calls = 0

    async def invoke(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> ProviderResponse:
        del messages, model, max_tokens, temperature
        raise AssertionError("native streaming should not call invoke")

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[ProviderStreamChunk]:
        del messages, model, max_tokens, temperature
        self.calls += 1
        for chunk in self.chunks:
            yield cast(ProviderStreamChunk, chunk)


class ToolLoopProvider(BaseLLMProvider):
    def __init__(self, responses: Sequence[ToolProviderResponse]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[list[ToolMessage], str, tuple[ToolDefinition, ...], int, float]] = []

    async def invoke(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> ProviderResponse:
        del messages, model, max_tokens, temperature
        raise AssertionError("tool loop should call invoke_tools")

    async def invoke_tools(
        self,
        messages: Sequence[ToolMessage],
        model: str,
        tools: Sequence[ToolDefinition],
        *,
        max_tokens: int,
        temperature: float,
    ) -> ToolProviderResponse:
        self.calls.append((list(messages), model, tuple(tools), max_tokens, temperature))
        if not self.responses:
            raise AssertionError("scripted tool responses exhausted")
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_agent_invocation_tracks_real_history_and_metrics() -> None:
    provider = RecordingProvider("first")
    engine = LLMAgentEngine(max_output_tokens=321, temperature=0.25)
    engine.register_provider("recording", provider)
    agent = engine.create_agent(
        name="researcher",
        model="test-model",
        system_prompt="Be exact.",
        provider="recording",
    )

    assert await agent.invoke("Hello", session_id="thread-1") == "first"
    provider.response = "second"
    assert await agent.invoke("Again", session_id="thread-1") == "second"

    assert [message.as_dict() for message in provider.calls[1][0]] == [
        {"role": "system", "content": "Be exact."},
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "first"},
        {"role": "user", "content": "Again"},
    ]
    assert provider.calls[0][1:] == ("test-model", 321, 0.25)
    assert agent.get_metrics() == {
        "requests": 2,
        "successes": 2,
        "failures": 0,
        "guardrail_blocks": 0,
        "tool_calls": 0,
        "tool_failures": 0,
        "tool_denials": 0,
        "input_tokens": 8,
        "output_tokens": 4,
        "last_latency_ms": pytest.approx(agent.get_metrics()["last_latency_ms"]),
    }
    assert len(agent.history("thread-1")) == 4
    assert [event.event_type for event in agent.events("thread-1")] == [
        "request.started",
        "request.succeeded",
        "request.started",
        "request.succeeded",
    ]
    assert all("content" not in event.as_dict() for event in agent.events())


@pytest.mark.asyncio
async def test_input_guardrail_blocks_before_provider_request() -> None:
    provider = RecordingProvider()
    contexts: list[GuardrailContext] = []

    def block(_: str, context: GuardrailContext) -> GuardrailResult:
        contexts.append(context)
        return GuardrailResult(allowed=False, reason="sensitive input")

    engine = LLMAgentEngine()
    engine.register_provider("recording", provider)
    agent = engine.create_agent(
        name="assistant",
        model="test",
        provider="recording",
        input_guardrails=(block,),
    )

    with pytest.raises(GuardrailError, match="sensitive input") as captured:
        await agent.invoke("secret")

    assert captured.value.stage == "input"
    assert captured.value.blocked is True
    assert provider.calls == []
    assert agent.get_metrics()["requests"] == 0
    assert agent.get_metrics()["guardrail_blocks"] == 1
    assert contexts[0].provider_name == "recording"
    assert [event.event_type for event in agent.events()] == ["guardrail.blocked"]


@pytest.mark.asyncio
async def test_output_guardrail_blocks_after_request_without_committing_history() -> None:
    provider = RecordingProvider("unsafe output")

    def block(_: str, context: GuardrailContext) -> bool:
        assert context.stage == "output"
        return False

    engine = LLMAgentEngine()
    engine.register_provider("recording", provider)
    agent = engine.create_agent(
        name="assistant",
        model="test",
        provider="recording",
        output_guardrails=(block,),
    )

    with pytest.raises(GuardrailError, match="output blocked"):
        await agent.invoke("hello")

    assert len(provider.calls) == 1
    assert agent.history() == ()
    assert agent.get_metrics()["failures"] == 1
    assert agent.get_metrics()["guardrail_blocks"] == 1
    assert [event.event_type for event in agent.events()] == [
        "request.started",
        "guardrail.blocked",
        "request.failed",
    ]


@pytest.mark.asyncio
async def test_guardrail_callback_failure_is_sanitized_and_audited() -> None:
    provider = RecordingProvider()

    def fail(_: str, __: GuardrailContext) -> bool:
        raise RuntimeError("secret-bearing callback failure")

    engine = LLMAgentEngine()
    engine.register_provider("recording", provider)
    agent = engine.create_agent(
        name="assistant",
        model="test",
        provider="recording",
        input_guardrails=(fail,),
    )

    with pytest.raises(GuardrailError, match="guardrail failed") as captured:
        await agent.invoke("hello")
    assert "secret-bearing" not in str(captured.value)
    assert captured.value.blocked is False
    assert [event.event_type for event in agent.events()] == ["guardrail.failed"]


@pytest.mark.asyncio
async def test_streaming_fails_closed_when_output_guardrails_are_configured() -> None:
    engine = LLMAgentEngine()
    agent = engine.create_agent(
        name="assistant",
        model="echo",
        output_guardrails=(lambda _content, _context: True,),
    )

    with pytest.raises(ConfigurationError, match="output guardrails"):
        _ = [chunk async for chunk in agent.stream("hello")]
    assert agent.get_metrics()["requests"] == 0


@pytest.mark.asyncio
async def test_event_buffer_is_bounded_and_can_be_cleared() -> None:
    engine = LLMAgentEngine(max_events=2)
    agent = engine.create_agent(name="assistant", model="echo")

    await agent.invoke("one", session_id="a")
    await agent.invoke("two", session_id="b")
    assert len(agent.events()) == 2
    assert {event.session_id for event in agent.events()} == {"b"}
    agent.clear_events()
    assert agent.events() == ()


@pytest.mark.asyncio
async def test_approved_tool_loop_executes_and_commits_only_final_turn() -> None:
    provider = ToolLoopProvider(
        [
            ToolProviderResponse(
                tool_calls=(
                    ToolCall(
                        call_id="call-1",
                        name="lookup_ticket",
                        arguments='{"ticket_id":"T-1"}',
                    ),
                ),
                input_tokens=4,
                output_tokens=2,
            ),
            ToolProviderResponse(content="Ticket T-1 is open.", input_tokens=7, output_tokens=5),
        ]
    )
    handled: list[dict[str, JsonValue]] = []
    approvals: list[ApprovalRequest] = []

    async def lookup(arguments: dict[str, JsonValue]) -> JsonValue:
        handled.append(arguments)
        return {"status": "open", "ticket_id": arguments["ticket_id"]}

    async def approve(request: ApprovalRequest) -> ApprovalDecision:
        approvals.append(request)
        return ApprovalDecision(approved=True)

    tool = ToolDefinition(
        name="lookup_ticket",
        description="Look up a support ticket.",
        parameters={
            "type": "object",
            "properties": {"ticket_id": {"type": "string"}},
            "required": ["ticket_id"],
            "additionalProperties": False,
        },
        handler=lookup,
    )
    engine = LLMAgentEngine(max_output_tokens=321, temperature=0.25)
    engine.register_provider("tools", provider)
    agent = engine.create_agent(name="assistant", model="test", provider="tools")

    result = await agent.run_tools(
        "Check T-1",
        [tool],
        approval_handler=approve,
        session_id="support",
    )

    assert result == "Ticket T-1 is open."
    assert handled == [{"ticket_id": "T-1"}]
    assert approvals[0].arguments == {"ticket_id": "T-1"}
    assert approvals[0].round_number == 1
    assert [message.as_dict() for message in provider.calls[1][0]] == [
        {"role": "user", "content": "Check T-1"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "lookup_ticket",
                        "arguments": '{"ticket_id":"T-1"}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "content": '{"status":"open","ticket_id":"T-1"}',
            "tool_call_id": "call-1",
        },
    ]
    assert [message.content for message in agent.history("support")] == [
        "Check T-1",
        "Ticket T-1 is open.",
    ]
    metrics = agent.get_metrics()
    assert metrics["requests"] == 2
    assert metrics["successes"] == 2
    assert metrics["tool_calls"] == 1
    assert metrics["tool_failures"] == 0
    assert [event.event_type for event in agent.events()] == [
        "request.started",
        "tool.requested",
        "tool.approved",
        "tool.succeeded",
        "request.succeeded",
        "request.started",
        "request.succeeded",
    ]
    assert all("arguments" not in event.as_dict() for event in agent.events())


@pytest.mark.asyncio
async def test_tool_requires_explicit_approval_by_default() -> None:
    provider = ToolLoopProvider(
        [ToolProviderResponse(tool_calls=(ToolCall(call_id="call-1", name="act", arguments="{}"),))]
    )
    executed = False

    def act(_: dict[str, JsonValue]) -> JsonValue:
        nonlocal executed
        executed = True
        return {"ok": True}

    engine = LLMAgentEngine()
    engine.register_provider("tools", provider)
    agent = engine.create_agent(name="assistant", model="test", provider="tools")
    tool = ToolDefinition(
        name="act",
        description="Perform an action.",
        parameters={"type": "object"},
        handler=act,
    )

    with pytest.raises(ToolApprovalError, match="requires approval") as captured:
        await agent.run_tools("act", [tool])

    assert executed is False
    assert captured.value.tool_name == "act"
    assert agent.get_metrics()["tool_denials"] == 1
    assert agent.history() == ()
    assert [event.event_type for event in agent.events()] == [
        "request.started",
        "tool.requested",
        "tool.denied",
        "request.failed",
    ]


@pytest.mark.asyncio
async def test_operator_can_explicitly_deny_a_tool_with_safe_reason() -> None:
    provider = ToolLoopProvider(
        [ToolProviderResponse(tool_calls=(ToolCall(call_id="call-1", name="act", arguments="{}"),))]
    )
    tool = ToolDefinition(
        name="act",
        description="Act.",
        parameters={"type": "object"},
        handler=lambda _arguments: {"ok": True},
    )
    engine = LLMAgentEngine()
    engine.register_provider("tools", provider)
    agent = engine.create_agent(name="assistant", model="test", provider="tools")

    with pytest.raises(ToolApprovalError, match="operator policy"):
        await agent.run_tools(
            "act",
            [tool],
            approval_handler=lambda _request: ApprovalDecision(
                approved=False,
                reason="operator policy",
            ),
        )
    assert agent.get_metrics()["tool_denials"] == 1


@pytest.mark.asyncio
async def test_tool_loop_applies_output_guardrail_to_final_answer() -> None:
    provider = ToolLoopProvider([ToolProviderResponse(content="blocked final")])
    engine = LLMAgentEngine()
    engine.register_provider("tools", provider)
    agent = engine.create_agent(
        name="assistant",
        model="test",
        provider="tools",
        output_guardrails=(lambda _content, _context: False,),
    )
    tool = ToolDefinition(
        name="read",
        description="Read.",
        parameters={"type": "object"},
        handler=lambda _arguments: None,
        requires_approval=False,
    )

    with pytest.raises(GuardrailError, match="output blocked"):
        await agent.run_tools("read", [tool])
    assert agent.history() == ()


@pytest.mark.asyncio
async def test_explicitly_non_approval_tool_can_run_unattended() -> None:
    provider = ToolLoopProvider(
        [
            ToolProviderResponse(
                tool_calls=(ToolCall(call_id="call-1", name="read_status", arguments="{}"),)
            ),
            ToolProviderResponse(content="All systems operational."),
        ]
    )
    tool = ToolDefinition(
        name="read_status",
        description="Read system status without side effects.",
        parameters={"type": "object"},
        handler=lambda _arguments: {"status": "ok"},
        requires_approval=False,
    )
    engine = LLMAgentEngine()
    engine.register_provider("tools", provider)
    agent = engine.create_agent(name="assistant", model="test", provider="tools")

    assert await agent.run_tools("status", [tool]) == "All systems operational."
    assert "tool.approved" not in {event.event_type for event in agent.events()}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("call", "message"),
    [
        (ToolCall(call_id="call-1", name="missing", arguments="{}"), "unavailable tool"),
        (ToolCall(call_id="call-1", name="act", arguments="not-json"), "invalid bounded JSON"),
        (ToolCall(call_id="call-1", name="act", arguments="[]"), "must be a JSON object"),
    ],
)
async def test_tool_loop_rejects_unavailable_or_invalid_calls(
    call: ToolCall,
    message: str,
) -> None:
    provider = ToolLoopProvider([ToolProviderResponse(tool_calls=(call,))])
    tool = ToolDefinition(
        name="act",
        description="Act.",
        parameters={"type": "object"},
        handler=lambda _arguments: {"ok": True},
        requires_approval=False,
    )
    engine = LLMAgentEngine()
    engine.register_provider("tools", provider)
    agent = engine.create_agent(name="assistant", model="test", provider="tools")

    with pytest.raises(ToolExecutionError, match=message):
        await agent.run_tools("act", [tool])
    assert agent.get_metrics()["tool_failures"] == 1


@pytest.mark.asyncio
async def test_tool_handler_and_approval_errors_are_sanitized() -> None:
    def fail_tool(_: dict[str, JsonValue]) -> JsonValue:
        raise RuntimeError("secret-bearing tool failure")

    tool = ToolDefinition(
        name="act",
        description="Act.",
        parameters={"type": "object"},
        handler=fail_tool,
        requires_approval=False,
    )
    provider = ToolLoopProvider(
        [ToolProviderResponse(tool_calls=(ToolCall(call_id="call-1", name="act", arguments="{}"),))]
    )
    engine = LLMAgentEngine()
    engine.register_provider("tools", provider)
    agent = engine.create_agent(name="assistant", model="test", provider="tools")

    with pytest.raises(ToolExecutionError, match="handler failed") as handler_error:
        await agent.run_tools("act", [tool])
    assert "secret-bearing" not in str(handler_error.value)

    provider = ToolLoopProvider(
        [ToolProviderResponse(tool_calls=(ToolCall(call_id="call-2", name="act", arguments="{}"),))]
    )
    engine = LLMAgentEngine()
    engine.register_provider("tools", provider)
    agent = engine.create_agent(name="assistant", model="test", provider="tools")
    approval_tool = ToolDefinition(
        name="act",
        description="Act.",
        parameters={"type": "object"},
        handler=lambda _arguments: {"ok": True},
    )

    def fail_approval(_: ApprovalRequest) -> bool:
        raise RuntimeError("secret-bearing approval failure")

    with pytest.raises(ToolApprovalError, match="approval handler failed") as approval_error:
        await agent.run_tools("act", [approval_tool], approval_handler=fail_approval)
    assert "secret-bearing" not in str(approval_error.value)

    provider = ToolLoopProvider(
        [ToolProviderResponse(tool_calls=(ToolCall(call_id="call-3", name="act", arguments="{}"),))]
    )
    engine = LLMAgentEngine()
    engine.register_provider("tools", provider)
    agent = engine.create_agent(name="assistant", model="test", provider="tools")
    with pytest.raises(ToolApprovalError, match="approval handler failed"):
        await agent.run_tools(
            "act",
            [approval_tool],
            approval_handler=lambda _request: object(),  # type: ignore[arg-type,return-value]
        )


@pytest.mark.asyncio
async def test_tool_rejects_non_finite_handler_result() -> None:
    provider = ToolLoopProvider(
        [
            ToolProviderResponse(
                tool_calls=(ToolCall(call_id="call-1", name="read", arguments="{}"),)
            )
        ]
    )
    tool = ToolDefinition(
        name="read",
        description="Read.",
        parameters={"type": "object"},
        handler=lambda _arguments: {"value": float("nan")},
        requires_approval=False,
    )
    engine = LLMAgentEngine()
    engine.register_provider("tools", provider)
    agent = engine.create_agent(name="assistant", model="test", provider="tools")

    with pytest.raises(ToolExecutionError, match="invalid JSON"):
        await agent.run_tools("read", [tool])


@pytest.mark.asyncio
async def test_tool_loop_enforces_round_call_argument_and_result_limits() -> None:
    tool = ToolDefinition(
        name="act",
        description="Act.",
        parameters={"type": "object"},
        handler=lambda _arguments: "result-too-long",
        requires_approval=False,
    )

    provider = ToolLoopProvider(
        [ToolProviderResponse(tool_calls=(ToolCall(call_id="call-1", name="act", arguments="{}"),))]
    )
    engine = LLMAgentEngine(max_tool_rounds=1)
    engine.register_provider("tools", provider)
    agent = engine.create_agent(name="assistant", model="test", provider="tools")
    with pytest.raises(BudgetExceededError, match="model-round limit"):
        await agent.run_tools("act", [tool])

    provider = ToolLoopProvider(
        [
            ToolProviderResponse(
                tool_calls=(
                    ToolCall(call_id="call-1", name="act", arguments="{}"),
                    ToolCall(call_id="call-2", name="act", arguments="{}"),
                )
            )
        ]
    )
    engine = LLMAgentEngine(max_tool_calls=1)
    engine.register_provider("tools", provider)
    agent = engine.create_agent(name="assistant", model="test", provider="tools")
    with pytest.raises(BudgetExceededError, match="tool-call limit"):
        await agent.run_tools("act", [tool])

    provider = ToolLoopProvider(
        [
            ToolProviderResponse(
                tool_calls=(ToolCall(call_id="call-1", name="act", arguments='{"x":1}'),)
            )
        ]
    )
    engine = LLMAgentEngine(max_tool_argument_chars=2)
    engine.register_provider("tools", provider)
    agent = engine.create_agent(name="assistant", model="test", provider="tools")
    with pytest.raises(BudgetExceededError, match="arguments exceeded"):
        await agent.run_tools("act", [tool])

    provider = ToolLoopProvider(
        [ToolProviderResponse(tool_calls=(ToolCall(call_id="call-1", name="act", arguments="{}"),))]
    )
    engine = LLMAgentEngine(max_tool_result_chars=2)
    engine.register_provider("tools", provider)
    agent = engine.create_agent(name="assistant", model="test", provider="tools")
    with pytest.raises(BudgetExceededError, match="result exceeded"):
        await agent.run_tools("act", [tool])


@pytest.mark.asyncio
async def test_tool_does_not_execute_without_budget_for_final_response() -> None:
    executed = False

    def act(_: dict[str, JsonValue]) -> JsonValue:
        nonlocal executed
        executed = True
        return {"ok": True}

    tool = ToolDefinition(
        name="act",
        description="Act.",
        parameters={"type": "object"},
        handler=act,
        requires_approval=False,
    )
    provider = ToolLoopProvider(
        [ToolProviderResponse(tool_calls=(ToolCall(call_id="call-1", name="act", arguments="{}"),))]
    )
    engine = LLMAgentEngine(max_requests_per_session=1)
    engine.register_provider("tools", provider)
    agent = engine.create_agent(name="assistant", model="test", provider="tools")

    with pytest.raises(BudgetExceededError, match="final model response"):
        await agent.run_tools("act", [tool])
    assert executed is False


@pytest.mark.asyncio
async def test_tool_loop_validates_tool_collection_and_approval_handler() -> None:
    tool = ToolDefinition(
        name="act",
        description="Act.",
        parameters={"type": "object"},
        handler=lambda _arguments: None,
    )
    engine = LLMAgentEngine()
    agent = engine.create_agent(name="assistant", model="echo")

    with pytest.raises(InputValidationError, match="1-32"):
        await agent.run_tools("act", [])
    with pytest.raises(InputValidationError, match="unique"):
        await agent.run_tools("act", [tool, tool])
    with pytest.raises(InputValidationError, match="approval_handler"):
        await agent.run_tools("act", [tool], approval_handler=object())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_agent_streams_deltas_then_commits_history_and_usage() -> None:
    provider = StreamingProvider()
    engine = LLMAgentEngine()
    engine.register_provider("streaming", provider)
    agent = engine.create_agent(name="assistant", model="test", provider="streaming")

    chunks = [chunk async for chunk in agent.stream("Hello", session_id="thread-1")]

    assert chunks == ["hel", "lo"]
    assert [message.content for message in agent.history("thread-1")] == ["Hello", "hello"]
    assert agent.get_metrics() | {"last_latency_ms": None} == {
        "requests": 1,
        "successes": 1,
        "failures": 0,
        "guardrail_blocks": 0,
        "tool_calls": 0,
        "tool_failures": 0,
        "tool_denials": 0,
        "input_tokens": 3,
        "output_tokens": 2,
        "last_latency_ms": None,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("chunks", "message"),
    [
        ((ProviderStreamChunk(delta="unfinished"),), "final event"),
        ((object(),), "invalid stream event"),
        (
            (
                ProviderStreamChunk(delta="done"),
                ProviderStreamChunk(final=True),
                ProviderStreamChunk(delta="late"),
            ),
            "after the final",
        ),
    ],
)
async def test_agent_rejects_invalid_streams_without_committing_history(
    chunks: tuple[ProviderStreamChunk | object, ...],
    message: str,
) -> None:
    provider = StreamingProvider(chunks)
    engine = LLMAgentEngine()
    engine.register_provider("streaming", provider)
    agent = engine.create_agent(name="assistant", model="test", provider="streaming")

    with pytest.raises(ProviderError, match=message):
        _ = [chunk async for chunk in agent.stream("Hello")]

    assert agent.history() == ()
    assert agent.get_metrics()["failures"] == 1


@pytest.mark.asyncio
async def test_agent_rejects_stream_over_character_limit() -> None:
    provider = StreamingProvider(
        (
            ProviderStreamChunk(delta="too"),
            ProviderStreamChunk(delta=" long"),
            ProviderStreamChunk(final=True),
        )
    )
    engine = LLMAgentEngine(max_response_chars=3)
    engine.register_provider("streaming", provider)
    agent = engine.create_agent(name="assistant", model="test", provider="streaming")

    with pytest.raises(ProviderError, match="character limit"):
        _ = [chunk async for chunk in agent.stream("Hello")]
    assert agent.history() == ()


@pytest.mark.asyncio
async def test_agent_parses_and_validates_structured_output() -> None:
    provider = RecordingProvider('{"priority": 2, "queue": "billing"}')
    engine = LLMAgentEngine()
    engine.register_provider("recording", provider)
    agent = engine.create_agent(name="assistant", model="test", provider="recording")

    assert await agent.invoke_json("Classify") == {"priority": 2, "queue": "billing"}
    agent.clear_history()

    def priority(value: JsonValue) -> int:
        if not isinstance(value, dict):
            raise ValueError("expected an object")
        result = value.get("priority")
        if isinstance(result, bool) or not isinstance(result, int):
            raise ValueError("expected an integer priority")
        return result

    assert (
        await agent.invoke_structured(
            "Classify",
            priority,
        )
        == 2
    )
    assert len(agent.history()) == 2


@pytest.mark.asyncio
async def test_invalid_structured_output_is_counted_but_not_committed() -> None:
    provider = RecordingProvider('{"priority": NaN}')
    engine = LLMAgentEngine()
    engine.register_provider("recording", provider)
    agent = engine.create_agent(name="assistant", model="test", provider="recording")

    with pytest.raises(StructuredOutputError, match="non-finite"):
        await agent.invoke_json("Classify")

    assert agent.history() == ()
    assert agent.get_metrics() | {"last_latency_ms": None} == {
        "requests": 1,
        "successes": 0,
        "failures": 1,
        "guardrail_blocks": 0,
        "tool_calls": 0,
        "tool_failures": 0,
        "tool_denials": 0,
        "input_tokens": 4,
        "output_tokens": 2,
        "last_latency_ms": None,
    }


@pytest.mark.asyncio
async def test_structured_validator_errors_are_sanitized() -> None:
    provider = RecordingProvider('{"priority": 2}')
    engine = LLMAgentEngine()
    engine.register_provider("recording", provider)
    agent = engine.create_agent(name="assistant", model="test", provider="recording")

    def reject(_: object) -> object:
        raise RuntimeError("secret-bearing validator failure")

    with pytest.raises(StructuredOutputError, match="validation failed") as captured:
        await agent.invoke_structured("Classify", reject)
    assert "secret-bearing" not in str(captured.value)
    assert agent.history() == ()


@pytest.mark.asyncio
async def test_structured_depth_is_validated_before_provider_call() -> None:
    provider = RecordingProvider("null")
    engine = LLMAgentEngine()
    engine.register_provider("recording", provider)
    agent = engine.create_agent(name="assistant", model="test", provider="recording")

    with pytest.raises(InputValidationError, match="max_depth"):
        await agent.invoke_json("Classify", max_depth=0)
    assert provider.calls == []


@pytest.mark.asyncio
async def test_history_and_session_limits_evict_oldest_state() -> None:
    engine = LLMAgentEngine(max_history_messages=2, max_sessions=1)
    agent = engine.create_agent(name="assistant", model="echo")

    await agent.invoke("one", session_id="a")
    await agent.invoke("two", session_id="a")
    assert [message.content for message in agent.history("a")] == ["two", "Echo: two"]

    await agent.invoke("new", session_id="b")
    assert agent.history("a") == ()
    assert len(agent.history("b")) == 2
    agent.clear_history()
    assert agent.history("b") == ()


@pytest.mark.asyncio
async def test_odd_history_limit_still_retains_only_complete_turns() -> None:
    engine = LLMAgentEngine(max_history_messages=3)
    agent = engine.create_agent(name="assistant", model="echo")

    await agent.invoke("one")
    await agent.invoke("two")

    assert [message.content for message in agent.history()] == ["two", "Echo: two"]


@pytest.mark.asyncio
async def test_session_snapshot_round_trip_restores_history_and_budget() -> None:
    provider = RecordingProvider("first")
    engine = LLMAgentEngine(max_requests_per_session=3)
    engine.register_provider("recording", provider)
    source = engine.create_agent(name="source", model="test", provider="recording")

    await source.invoke("hello", session_id="portable")
    snapshot = await source.export_session("portable")
    serialized = snapshot.to_json()

    restored = engine.create_agent(name="restored", model="test", provider="recording")
    await restored.import_session(SessionSnapshot.from_json(serialized))
    provider.response = "second"
    assert await restored.invoke("again", session_id="portable") == "second"
    assert [message.content for message in provider.calls[-1][0]] == [
        "hello",
        "first",
        "again",
    ]
    assert [event.event_type for event in source.events()][-1] == "session.exported"
    assert next(event.event_type for event in restored.events()) == "session.imported"


@pytest.mark.asyncio
async def test_session_import_rejects_overwrite_and_agent_limit_mismatch() -> None:
    snapshot = SessionSnapshot(
        session_id="portable",
        messages=(
            ChatMessage(role="user", content="hello"),
            ChatMessage(role="assistant", content="hi"),
        ),
        request_count=2,
    )
    engine = LLMAgentEngine(max_history_messages=2, max_requests_per_session=1)
    agent = engine.create_agent(name="assistant", model="echo")

    with pytest.raises(InputValidationError, match="request limit"):
        await agent.import_session(snapshot)

    compatible = SessionSnapshot(
        session_id="portable",
        messages=snapshot.messages,
        request_count=1,
    )
    await agent.import_session(compatible)
    with pytest.raises(InputValidationError, match="already exists"):
        await agent.import_session(compatible)
    await agent.import_session(compatible, replace=True)


@pytest.mark.asyncio
async def test_export_requires_an_existing_session() -> None:
    engine = LLMAgentEngine()
    agent = engine.create_agent(name="assistant", model="echo")
    with pytest.raises(InputValidationError, match="does not exist"):
        await agent.export_session("missing")


@pytest.mark.asyncio
async def test_request_budget_blocks_before_provider_call_and_can_be_reset() -> None:
    provider = RecordingProvider()
    engine = LLMAgentEngine(max_requests_per_session=1)
    engine.register_provider("recording", provider)
    agent = engine.create_agent(name="assistant", model="test", provider="recording")

    await agent.invoke("first")
    with pytest.raises(BudgetExceededError, match="request limit"):
        await agent.invoke("second")
    assert len(provider.calls) == 1

    agent.clear_history("default")
    await agent.invoke("after reset")
    assert len(provider.calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("expected", [True, False])
async def test_provider_failures_are_counted_and_unknown_errors_are_sanitized(
    expected: bool,
) -> None:
    engine = LLMAgentEngine()
    engine.register_provider("failing", FailingProvider(expected=expected))
    agent = engine.create_agent(name="assistant", model="test", provider="failing")

    with pytest.raises(ProviderError) as captured:
        await agent.invoke("hello")
    if not expected:
        assert "secret-bearing" not in str(captured.value)
    assert agent.get_metrics()["requests"] == 1
    assert agent.get_metrics()["failures"] == 1
    assert agent.history() == ()


@pytest.mark.asyncio
async def test_engine_closes_shared_provider_once() -> None:
    provider = RecordingProvider()
    engine = LLMAgentEngine()
    engine.register_provider("one", provider)
    engine.register_provider("two", provider)

    await engine.close()
    await engine.close()
    assert provider.closed == 1


@pytest.mark.asyncio
async def test_engine_closes_replaced_provider_and_rejects_use_after_close() -> None:
    first = RecordingProvider()
    second = RecordingProvider()
    engine = LLMAgentEngine()
    engine.register_provider("recording", first)
    engine.register_provider("recording", second)

    await engine.close()
    assert (first.closed, second.closed) == (1, 1)
    with pytest.raises(ConfigurationError, match="closed"):
        engine.create_agent(name="assistant", model="test")
    with pytest.raises(ConfigurationError, match="closed"):
        engine.register_provider("third", RecordingProvider())


@pytest.mark.asyncio
async def test_engine_closes_all_providers_and_sanitizes_cleanup_failure() -> None:
    failing = FailingCloseProvider()
    healthy = RecordingProvider()
    engine = LLMAgentEngine()
    engine.register_provider("failing", failing)
    engine.register_provider("healthy", healthy)

    with pytest.raises(ProviderError, match="cleanup failed") as captured:
        await engine.close()
    assert "secret-bearing" not in str(captured.value)
    assert healthy.closed == 1


@pytest.mark.asyncio
async def test_engine_context_manager_closes_provider() -> None:
    provider = RecordingProvider()
    async with LLMAgentEngine() as engine:
        engine.register_provider("recording", provider)
    assert provider.closed == 1


@pytest.mark.asyncio
async def test_orchestrator_is_labeled_sequential_and_bounded() -> None:
    engine = LLMAgentEngine()
    first = engine.create_agent(name="first", model="echo")
    second = engine.create_agent(name="second", model="echo")
    orchestrator = AgentOrchestrator(max_agents=2)
    orchestrator.add_agent(first)
    orchestrator.add_agent(second)

    result = await orchestrator.collective_loop(prompt="Plan", max_iterations=1)
    assert result.startswith("first: Echo: Plan\nsecond: Echo: Original task: Plan")
    assert tuple(orchestrator.agents) == (first, second)
    with pytest.raises(BudgetExceededError):
        orchestrator.add_agent(engine.create_agent(name="third", model="echo"))
    with pytest.raises(ConfigurationError, match="between 1 and 5"):
        await orchestrator.collective_loop(prompt="Plan", max_iterations=6)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"max_history_messages": 1}, "max_history_messages"),
        ({"max_sessions": 0}, "max_sessions"),
        ({"max_input_chars": 0}, "max_input_chars"),
        ({"max_requests_per_session": 0}, "max_requests_per_session"),
        ({"max_output_tokens": 0}, "max_output_tokens"),
        ({"max_response_chars": 0}, "max_response_chars"),
        ({"max_events": 0}, "max_events"),
        ({"max_tool_rounds": 0}, "max_tool_rounds"),
        ({"max_tool_calls": 0}, "max_tool_calls"),
        ({"max_tool_argument_chars": 1}, "max_tool_argument_chars"),
        ({"max_tool_result_chars": 0}, "max_tool_result_chars"),
        ({"temperature": 3}, "temperature"),
        ({"default_provider": "bad name"}, "provider name"),
    ],
)
def test_engine_rejects_invalid_configuration(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ConfigurationError, match=message):
        LLMAgentEngine(**kwargs)  # type: ignore[arg-type]


def test_agent_and_provider_registration_validate_public_inputs() -> None:
    engine = LLMAgentEngine(max_input_chars=5)
    with pytest.raises(ConfigurationError, match="inherit"):
        engine.register_provider("bad", object())  # type: ignore[arg-type]
    with pytest.raises(InputValidationError, match="agent name"):
        engine.create_agent(name="bad name", model="echo")
    with pytest.raises(InputValidationError, match="model"):
        engine.create_agent(name="good", model="")
    with pytest.raises(InputValidationError, match="system_prompt"):
        engine.create_agent(name="good", model="echo", system_prompt="123456")
    with pytest.raises(ConfigurationError, match="not registered"):
        engine.create_agent(name="good", model="test", provider="missing")
    with pytest.raises(ConfigurationError, match="input_guardrails"):
        engine.create_agent(
            name="good",
            model="echo",
            input_guardrails=(object(),),  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_agent_validates_prompt_and_session_id() -> None:
    engine = LLMAgentEngine(max_input_chars=5)
    agent = engine.create_agent(name="good", model="echo")
    with pytest.raises(InputValidationError, match="non-empty"):
        await agent.invoke("  ")
    with pytest.raises(InputValidationError, match="character limit"):
        await agent.invoke("123456")
    with pytest.raises(InputValidationError, match="session_id"):
        await agent.invoke("ok", session_id="bad\n")


@pytest.mark.asyncio
async def test_agent_serializes_concurrent_turns() -> None:
    provider = RecordingProvider()
    engine = LLMAgentEngine()
    engine.register_provider("recording", provider)
    agent = engine.create_agent(name="assistant", model="test", provider="recording")

    await asyncio.gather(agent.invoke("one"), agent.invoke("two"))
    assert len(provider.calls[0][0]) == 1
    assert len(provider.calls[1][0]) == 3


@pytest.mark.asyncio
async def test_agent_rejects_custom_provider_response_over_character_limit() -> None:
    provider = RecordingProvider("too long")
    engine = LLMAgentEngine(max_response_chars=3)
    engine.register_provider("recording", provider)
    agent = engine.create_agent(name="assistant", model="test", provider="recording")

    with pytest.raises(ProviderError, match="character limit"):
        await agent.invoke("hello")
    assert agent.history() == ()
