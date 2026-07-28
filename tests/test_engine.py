from __future__ import annotations

import asyncio

import pytest

from helix_llm_agent_engine import (
    AgentOrchestrator,
    BaseLLMProvider,
    BudgetExceededError,
    ChatMessage,
    ConfigurationError,
    InputValidationError,
    LLMAgentEngine,
    ProviderError,
    ProviderResponse,
)


class RecordingProvider(BaseLLMProvider):
    def __init__(self, response: str = "done") -> None:
        self.response = response
        self.calls: list[tuple[list[ChatMessage], str, int, float]] = []
        self.closed = 0

    async def invoke(
        self,
        messages: list[ChatMessage] | tuple[ChatMessage, ...],
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
        messages: list[ChatMessage] | tuple[ChatMessage, ...],
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
        "input_tokens": 8,
        "output_tokens": 4,
        "last_latency_ms": pytest.approx(agent.get_metrics()["last_latency_ms"]),
    }
    assert len(agent.history("thread-1")) == 4


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
