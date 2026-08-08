import pytest

from samsarix_agent_engine import (
    AgentMetrics,
    ApprovalDecision,
    ChatMessage,
    GuardrailResult,
    InputValidationError,
    ProviderResponse,
    ProviderStreamChunk,
    RunEvent,
    SamsarixAgentError,
    SessionSnapshot,
    StructuredOutputError,
    ToolCall,
    ToolDefinition,
    ToolMessage,
    ToolProviderResponse,
    parse_json_output,
)


def test_chat_message_validation_and_serialization() -> None:
    assert issubclass(InputValidationError, SamsarixAgentError)
    assert ChatMessage(role="user", content="hello").as_dict() == {
        "role": "user",
        "content": "hello",
    }
    with pytest.raises(InputValidationError, match="role"):
        ChatMessage(role="tool", content="hello")  # type: ignore[arg-type]
    with pytest.raises(InputValidationError, match="content"):
        ChatMessage(role="user", content="")


def test_provider_response_validates_usage() -> None:
    assert ProviderResponse(content="ok", input_tokens=0, output_tokens=1).content == "ok"
    with pytest.raises(InputValidationError, match="non-empty"):
        ProviderResponse(content="")
    with pytest.raises(InputValidationError, match="input_tokens"):
        ProviderResponse(content="ok", input_tokens=-1)
    with pytest.raises(InputValidationError, match="input_tokens"):
        ProviderResponse(content="ok", input_tokens=True)


def test_metrics_snapshot_is_stable() -> None:
    metrics = AgentMetrics(requests=1, successes=1, last_latency_ms=2.5)
    assert metrics.as_dict() == {
        "requests": 1,
        "successes": 1,
        "failures": 0,
        "guardrail_blocks": 0,
        "tool_calls": 0,
        "tool_failures": 0,
        "tool_denials": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "last_latency_ms": 2.5,
    }


def test_guardrail_result_validates_safe_reason() -> None:
    assert GuardrailResult(allowed=False, reason="policy").reason == "policy"
    with pytest.raises(InputValidationError, match="must not include"):
        GuardrailResult(allowed=True, reason="unused")
    with pytest.raises(InputValidationError, match="control"):
        GuardrailResult(allowed=False, reason="unsafe\nreason")
    with pytest.raises(InputValidationError, match="boolean"):
        GuardrailResult(allowed=1)  # type: ignore[arg-type]


def test_run_event_is_content_free_and_validated() -> None:
    event = RunEvent(
        event_type="request.succeeded",
        occurred_at="2026-08-08T00:00:00Z",
        agent_name="assistant",
        session_id="demo",
        provider_name="echo",
        model="echo",
        request_number=1,
        latency_ms=1.25,
    )
    assert event.as_dict()["event_type"] == "request.succeeded"
    assert "content" not in event.as_dict()
    with pytest.raises(InputValidationError, match="request_number"):
        RunEvent(
            event_type="request.started",
            occurred_at="now",
            agent_name="assistant",
            session_id="demo",
            provider_name="echo",
            model="echo",
            request_number=0,
        )
    with pytest.raises(InputValidationError, match="latency_ms"):
        RunEvent(
            event_type="request.failed",
            occurred_at="now",
            agent_name="assistant",
            session_id="demo",
            provider_name="echo",
            model="echo",
            latency_ms=float("inf"),
        )
    with pytest.raises(InputValidationError, match="supplied together"):
        RunEvent(
            event_type="tool.requested",
            occurred_at="now",
            agent_name="assistant",
            session_id="demo",
            provider_name="echo",
            model="echo",
            tool_name="lookup",
        )
    with pytest.raises(InputValidationError, match="unsupported"):
        RunEvent(
            event_type="unknown",  # type: ignore[arg-type]
            occurred_at="now",
            agent_name="assistant",
            session_id="demo",
            provider_name="echo",
            model="echo",
        )


def test_tool_models_validate_and_serialize_openai_contract() -> None:
    tool = ToolDefinition(
        name="lookup_ticket",
        description="Look up a support ticket.",
        parameters={
            "type": "object",
            "properties": {"ticket_id": {"type": "string"}},
            "required": ["ticket_id"],
            "additionalProperties": False,
        },
        handler=lambda arguments: {"found": bool(arguments)},
    )
    definition = tool.as_dict()
    assert definition["type"] == "function"
    function_definition = definition["function"]
    assert isinstance(function_definition, dict)
    assert function_definition["strict"] is True

    call = ToolCall(call_id="call-1", name="lookup_ticket", arguments='{"ticket_id":"T-1"}')
    assistant = ToolMessage(role="assistant", tool_calls=(call,))
    assert assistant.as_dict()["content"] is None
    assert assistant.as_dict()["tool_calls"] == [call.as_dict()]
    result = ToolMessage(role="tool", content='{"found":true}', tool_call_id="call-1")
    assert result.as_dict()["tool_call_id"] == "call-1"
    response = ToolProviderResponse(tool_calls=(call,), input_tokens=2, output_tokens=1)
    assert response.tool_calls == (call,)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": "bad name"},
        {"description": ""},
        {"parameters": []},
        {"parameters": {"value": float("nan")}},
        {"handler": object()},
        {"requires_approval": 1},
    ],
)
def test_tool_definition_rejects_invalid_configuration(kwargs: dict[str, object]) -> None:
    values: dict[str, object] = {
        "name": "safe_tool",
        "description": "Safe tool.",
        "parameters": {"type": "object"},
        "handler": lambda _arguments: None,
    }
    values.update(kwargs)
    with pytest.raises(InputValidationError):
        ToolDefinition(**values)  # type: ignore[arg-type]


def test_tool_messages_and_responses_reject_ambiguous_shapes() -> None:
    with pytest.raises(InputValidationError, match="require content"):
        ToolMessage(role="user")
    with pytest.raises(InputValidationError, match="neither"):
        ToolProviderResponse()
    with pytest.raises(InputValidationError, match="tool name"):
        ToolCall(call_id="call-1", name="bad name", arguments="{}")
    with pytest.raises(InputValidationError, match="call id"):
        ToolCall(call_id="", name="safe", arguments="{}")
    with pytest.raises(InputValidationError, match="arguments"):
        ToolCall(call_id="call-1", name="safe", arguments="")
    with pytest.raises(InputValidationError, match="tool result messages"):
        ToolMessage(role="tool", content="{}", tool_call_id=1)  # type: ignore[arg-type]
    with pytest.raises(InputValidationError, match="non-empty"):
        ToolProviderResponse(content="")
    with pytest.raises(InputValidationError, match="input_tokens"):
        ToolProviderResponse(content="done", input_tokens=True)


def test_approval_decision_rejects_unsafe_or_ambiguous_reason() -> None:
    assert ApprovalDecision(approved=False, reason="operator denied").approved is False
    with pytest.raises(InputValidationError, match="must not include"):
        ApprovalDecision(approved=True, reason="unused")
    with pytest.raises(InputValidationError, match="control"):
        ApprovalDecision(approved=False, reason="unsafe\nreason")
    with pytest.raises(InputValidationError, match="boolean"):
        ApprovalDecision(approved=1)  # type: ignore[arg-type]


def test_session_snapshot_round_trips_versioned_json() -> None:
    snapshot = SessionSnapshot(
        session_id="demo",
        messages=(
            ChatMessage(role="user", content="hello"),
            ChatMessage(role="assistant", content="hi"),
        ),
        request_count=1,
    )
    restored = SessionSnapshot.from_json(snapshot.to_json())
    assert restored == snapshot
    assert restored.as_dict()["format"] == "samsarix-agent-session"


@pytest.mark.parametrize(
    "value",
    [
        {"format": "wrong", "version": 1, "session_id": "x", "request_count": 0, "messages": []},
        {
            "format": "samsarix-agent-session",
            "version": 1,
            "session_id": "x",
            "request_count": 0,
            "messages": [{"role": "system", "content": "unsafe"}],
        },
    ],
)
def test_session_snapshot_rejects_untrusted_formats(value: dict[str, object]) -> None:
    with pytest.raises(InputValidationError):
        SessionSnapshot.from_dict(value)


def test_session_snapshot_rejects_incomplete_turns_and_oversized_json() -> None:
    with pytest.raises(InputValidationError, match="complete"):
        SessionSnapshot(
            session_id="demo",
            messages=(ChatMessage(role="user", content="hello"),),
            request_count=1,
        )
    with pytest.raises(InputValidationError, match="at most"):
        SessionSnapshot.from_json("x" * (SessionSnapshot.MAX_SERIALIZED_CHARS + 1))
    with pytest.raises(InputValidationError, match="valid bounded JSON"):
        SessionSnapshot.from_json("not-json")
    with pytest.raises(InputValidationError, match="size limit"):
        SessionSnapshot(
            session_id="demo",
            messages=(
                ChatMessage(
                    role="user",
                    content="x" * SessionSnapshot.MAX_SERIALIZED_CHARS,
                ),
                ChatMessage(role="assistant", content="reply"),
            ),
            request_count=1,
        )


def test_stream_chunks_validate_terminal_contract_and_usage() -> None:
    assert ProviderStreamChunk(delta="hello").delta == "hello"
    assert ProviderStreamChunk(final=True, output_tokens=2).final is True
    with pytest.raises(InputValidationError, match="empty stream"):
        ProviderStreamChunk()
    with pytest.raises(InputValidationError, match="delta"):
        ProviderStreamChunk(delta=1)  # type: ignore[arg-type]
    with pytest.raises(InputValidationError, match="boolean"):
        ProviderStreamChunk(delta="hello", final=1)  # type: ignore[arg-type]
    with pytest.raises(InputValidationError, match="output_tokens"):
        ProviderStreamChunk(final=True, output_tokens=True)


def test_strict_json_parser_accepts_values_and_rejects_ambiguity() -> None:
    assert parse_json_output('{"priority": 2, "tags": ["support"]}') == {
        "priority": 2,
        "tags": ["support"],
    }
    with pytest.raises(StructuredOutputError, match="duplicate"):
        parse_json_output('{"priority": 1, "priority": 2}')
    with pytest.raises(StructuredOutputError, match="non-finite"):
        parse_json_output('{"score": NaN}')
    with pytest.raises(StructuredOutputError, match="nesting"):
        parse_json_output('[[["too deep"]]]', max_depth=2)
    with pytest.raises(InputValidationError, match="max_depth"):
        parse_json_output("null", max_depth=0)
    with pytest.raises(StructuredOutputError, match="no structured output"):
        parse_json_output("")
    with pytest.raises(StructuredOutputError, match="valid bounded JSON"):
        parse_json_output("not-json")
    with pytest.raises(StructuredOutputError, match="invalid Unicode"):
        parse_json_output(r'{"value": "\ud800"}')
    with pytest.raises(StructuredOutputError, match="invalid Unicode"):
        parse_json_output(r'{"\ud800": "value"}')
    assert parse_json_output("1.25") == 1.25
