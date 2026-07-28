import pytest

from helix_llm_agent_engine import AgentMetrics, ChatMessage, InputValidationError, ProviderResponse


def test_chat_message_validation_and_serialization() -> None:
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
