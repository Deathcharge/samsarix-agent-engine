from __future__ import annotations

import httpx
import pytest

from samsarix_agent_engine import (
    ChatMessage,
    ConfigurationError,
    EchoProvider,
    OpenAICompatibleProvider,
    ProviderError,
)


def _messages() -> list[ChatMessage]:
    return [ChatMessage(role="user", content="hello")]


@pytest.mark.asyncio
async def test_echo_provider_is_explicitly_deterministic() -> None:
    provider = EchoProvider(prefix="Offline")
    response = await provider.invoke(_messages(), "echo", max_tokens=10, temperature=0)
    assert response.content == "Offline: hello"
    assert response.input_tokens is None
    with pytest.raises(ProviderError, match="no user"):
        await provider.invoke(
            [ChatMessage(role="system", content="system")],
            "echo",
            max_tokens=10,
            temperature=0,
        )


@pytest.mark.asyncio
async def test_openai_compatible_provider_normalizes_success() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "model": "served-model",
                "choices": [{"message": {"content": "answer"}}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3},
            },
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        base_url="https://models.example.test/v1",
        client=client,
    )
    response = await provider.invoke(_messages(), "asked-model", max_tokens=20, temperature=0.1)

    assert str(seen[0].url) == "https://models.example.test/v1/chat/completions"
    assert response.content == "answer"
    assert response.model == "served-model"
    assert response.input_tokens == 7
    assert response.output_tokens == 3
    await provider.close()
    assert not client.is_closed
    await client.aclose()


@pytest.mark.asyncio
async def test_retryable_status_retries_with_a_hard_cap() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"retry-after": "0"}, request=request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "ok"}}]},
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        base_url="http://localhost:9000/v1", max_retries=1, client=client
    )
    assert (
        await provider.invoke(_messages(), "local", max_tokens=10, temperature=0)
    ).content == "ok"
    assert attempts == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_timeout_is_retried_then_sanitized() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("token=do-not-copy", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        base_url="https://models.example.test/v1",
        max_retries=1,
        retry_backoff=0,
        client=client,
    )
    with pytest.raises(ProviderError, match="timed out") as captured:
        await provider.invoke(_messages(), "test", max_tokens=10, temperature=0)
    assert "do-not-copy" not in str(captured.value)
    assert captured.value.retryable is True
    assert attempts == 2
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(401, headers={"x-request-id": "req-1"}), "HTTP 401"),
        (httpx.Response(200, content=b"not-json"), "invalid JSON"),
        (httpx.Response(200, json={"choices": []}), "chat completion schema"),
        (httpx.Response(200, json={"choices": [{"message": {"content": ""}}]}), "no text"),
    ],
)
async def test_provider_rejects_error_and_malformed_responses(
    response: httpx.Response,
    message: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        response.request = request
        return response

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        base_url="https://models.example.test/v1/chat/completions",
        max_retries=0,
        client=client,
    )
    with pytest.raises(ProviderError, match=message):
        await provider.invoke(_messages(), "test", max_tokens=10, temperature=0)
    await client.aclose()


@pytest.mark.asyncio
async def test_provider_sanitizes_untrusted_request_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            headers={"x-request-id": "req-safe\r\nterminal-injection"},
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        base_url="https://models.example.test/v1", max_retries=0, client=client
    )
    with pytest.raises(ProviderError) as captured:
        await provider.invoke(_messages(), "test", max_tokens=10, temperature=0)
    assert "\r" not in str(captured.value)
    assert "\n" not in str(captured.value)
    await client.aclose()


def test_retry_after_rejects_non_finite_values() -> None:
    assert OpenAICompatibleProvider._bounded_retry_after("nan") is None
    assert OpenAICompatibleProvider._bounded_retry_after("inf") is None


@pytest.mark.asyncio
async def test_provider_rejects_oversized_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 1_025, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        base_url="https://models.example.test/v1",
        max_response_bytes=1_024,
        client=client,
    )
    with pytest.raises(ProviderError, match="size limit"):
        await provider.invoke(_messages(), "test", max_tokens=10, temperature=0)
    await client.aclose()


@pytest.mark.parametrize(
    "base_url",
    [
        "",
        "ftp://models.example.test/v1",
        "https://user:pass@models.example.test/v1",
        "https://models.example.test/v1?token=secret",
    ],
)
def test_provider_rejects_unsafe_or_invalid_base_urls(base_url: str) -> None:
    with pytest.raises(ConfigurationError):
        OpenAICompatibleProvider(base_url=base_url)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"api_key": ""},
        {"timeout": 0},
        {"max_retries": 6},
        {"retry_backoff": -1},
        {"max_response_bytes": 100},
    ],
)
def test_provider_rejects_invalid_limits(kwargs: dict[str, object]) -> None:
    with pytest.raises(ConfigurationError):
        OpenAICompatibleProvider(**kwargs)  # type: ignore[arg-type]
