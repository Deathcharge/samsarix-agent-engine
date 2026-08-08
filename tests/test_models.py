import pytest

from samsarix_agent_engine import (
    AgentMetrics,
    ChatMessage,
    InputValidationError,
    ProviderResponse,
    ProviderStreamChunk,
    SamsarixAgentError,
    StructuredOutputError,
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
        "input_tokens": 0,
        "output_tokens": 0,
        "last_latency_ms": 2.5,
    }


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
