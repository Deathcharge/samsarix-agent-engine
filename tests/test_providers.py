from __future__ import annotations

from collections.abc import Sequence

import httpx
import pytest

from samsarix_agent_engine import (
    BaseLLMProvider,
    ChatMessage,
    ConfigurationError,
    EchoProvider,
    OpenAICompatibleProvider,
    ProviderError,
    ToolCall,
    ToolDefinition,
    ToolMessage,
)


def _messages() -> list[ChatMessage]:
    return [ChatMessage(role="user", content="hello")]


class StringProvider(BaseLLMProvider):
    async def invoke(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> str:
        del messages, model, max_tokens, temperature
        return "plain string"


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

    chunks = [
        chunk
        async for chunk in provider.stream(
            _messages(),
            "echo",
            max_tokens=10,
            temperature=0,
        )
    ]
    assert [(chunk.delta, chunk.final) for chunk in chunks] == [("Offline: hello", True)]

    string_chunks = [
        chunk
        async for chunk in StringProvider().stream(
            _messages(),
            "fallback-model",
            max_tokens=10,
            temperature=0,
        )
    ]
    assert string_chunks[0].delta == "plain string"
    assert string_chunks[0].model == "fallback-model"

    with pytest.raises(ProviderError, match="does not support"):
        await provider.invoke_tools(
            [ToolMessage(role="user", content="hello")],
            "echo",
            [
                ToolDefinition(
                    name="lookup",
                    description="Lookup.",
                    parameters={"type": "object"},
                    handler=lambda _arguments: None,
                )
            ],
            max_tokens=10,
            temperature=0,
        )


def test_echo_provider_rejects_empty_prefix() -> None:
    with pytest.raises(ConfigurationError, match="prefix"):
        EchoProvider(" ")


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
async def test_openai_provider_normalizes_function_tool_calls() -> None:
    seen_payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_payloads.append(httpx.Response(200, request=request, content=request.content).json())
        return httpx.Response(
            200,
            json={
                "model": "served-model",
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "lookup",
                                        "arguments": '{"ticket_id":"T-1"}',
                                    },
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2},
            },
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(base_url="https://models.example.test/v1", client=client)
    tool = ToolDefinition(
        name="lookup",
        description="Lookup a ticket.",
        parameters={"type": "object"},
        handler=lambda _arguments: None,
    )
    response = await provider.invoke_tools(
        [ToolMessage(role="user", content="find T-1")],
        "asked-model",
        [tool],
        max_tokens=20,
        temperature=0,
    )

    assert response.tool_calls == (
        ToolCall(call_id="call-1", name="lookup", arguments='{"ticket_id":"T-1"}'),
    )
    assert response.input_tokens == 5
    assert response.output_tokens == 2
    assert seen_payloads[0]["parallel_tool_calls"] is False
    assert seen_payloads[0]["tool_choice"] == "auto"
    await client.aclose()


@pytest.mark.asyncio
async def test_openai_provider_normalizes_final_tool_loop_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": 7,
                "choices": [{"message": {"content": "final answer"}}],
                "usage": {"prompt_tokens": True, "completion_tokens": -1},
            },
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(base_url="https://models.example.test/v1", client=client)
    tool = ToolDefinition(
        name="lookup",
        description="Lookup.",
        parameters={"type": "object"},
        handler=lambda _arguments: None,
    )
    response = await provider.invoke_tools(
        [ToolMessage(role="user", content="hello")],
        "requested-model",
        [tool],
        max_tokens=10,
        temperature=0,
    )
    assert response.content == "final answer"
    assert response.model == "requested-model"
    assert response.input_tokens is None
    assert response.output_tokens is None
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("message", "error"),
    [
        ({"content": None}, "no usable output"),
        ({"content": 7}, "invalid text"),
        ({"tool_calls": "wrong"}, "tool completion schema"),
        (
            {
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {"name": "bad name", "arguments": "{}"},
                    }
                ]
            },
            "invalid function tool call",
        ),
    ],
)
async def test_provider_rejects_malformed_tool_responses(
    message: dict[str, object],
    error: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": message}]}, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(base_url="https://models.example.test/v1", client=client)
    tool = ToolDefinition(
        name="lookup",
        description="Lookup.",
        parameters={"type": "object"},
        handler=lambda _arguments: None,
    )
    with pytest.raises(ProviderError, match=error):
        await provider.invoke_tools(
            [ToolMessage(role="user", content="hello")],
            "test",
            [tool],
            max_tokens=10,
            temperature=0,
        )
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
async def test_openai_compatible_provider_streams_bounded_sse_and_usage() -> None:
    seen_payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_payloads.append(httpx.Response(200, request=request, content=request.content).json())
        body = (
            'data: {"model":"served-model","choices":[{"delta":{"content":"hel"}}]}\n\n'
            'data: {"choices":[{"delta":{"content":"lo"},"finish_reason":"stop"}]}\n\n'
            'data: {"choices":[],"usage":{"prompt_tokens":4,"completion_tokens":2}}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(
            200,
            content=body.encode(),
            headers={"content-type": "text/event-stream"},
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        base_url="https://models.example.test/v1",
        client=client,
    )
    chunks = [
        chunk
        async for chunk in provider.stream(
            _messages(),
            "asked-model",
            max_tokens=20,
            temperature=0.1,
        )
    ]

    assert seen_payloads[0]["stream"] is True
    assert "".join(chunk.delta for chunk in chunks) == "hello"
    assert [chunk.final for chunk in chunks] == [False, False, True]
    assert chunks[-1].model == "served-model"
    assert chunks[-1].input_tokens == 4
    assert chunks[-1].output_tokens == 2
    await client.aclose()


@pytest.mark.asyncio
async def test_provider_accepts_an_sse_event_at_end_of_file() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b'data: {"choices":[{"delta":{"content":"complete"}}]}',
            request=request,
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        base_url="https://models.example.test/v1",
        client=client,
    )

    chunks = [
        chunk
        async for chunk in provider.stream(
            _messages(),
            "test",
            max_tokens=10,
            temperature=0,
        )
    ]
    assert "".join(chunk.delta for chunk in chunks) == "complete"
    assert chunks[-1].final is True
    await client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "message"),
    [
        (b"data: not-json\n\n", "invalid JSON"),
        (b"data: []\n\n", "invalid event"),
        (b'data: {"choices":"wrong"}\n\n', "chat completion schema"),
        (b'data: {"choices":[{"delta":"wrong"}]}\n\n', "chat completion schema"),
        (b'data: {"choices":[{"delta":{"content":7}}]}\n\n', "invalid text"),
        (b"data: [DONE]\n\n", "no text content"),
    ],
)
async def test_provider_rejects_malformed_streams(body: bytes, message: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        base_url="https://models.example.test/v1",
        client=client,
    )
    with pytest.raises(ProviderError, match=message):
        _ = [
            chunk
            async for chunk in provider.stream(
                _messages(),
                "test",
                max_tokens=10,
                temperature=0,
            )
        ]
    await client.aclose()


@pytest.mark.asyncio
async def test_provider_rejects_oversized_stream() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 1_025, request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        base_url="https://models.example.test/v1",
        max_response_bytes=1_024,
        client=client,
    )
    with pytest.raises(ProviderError, match="size limit"):
        _ = [
            chunk
            async for chunk in provider.stream(
                _messages(),
                "test",
                max_tokens=10,
                temperature=0,
            )
        ]
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
async def test_request_error_is_retried_then_sanitized() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ConnectError("token=do-not-copy", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider(
        base_url="https://models.example.test/v1",
        max_retries=1,
        retry_backoff=0,
        client=client,
    )
    with pytest.raises(ProviderError, match="request failed") as captured:
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
    assert OpenAICompatibleProvider._bounded_retry_after(None) is None
    assert OpenAICompatibleProvider._bounded_retry_after("nan") is None
    assert OpenAICompatibleProvider._bounded_retry_after("inf") is None
    assert OpenAICompatibleProvider._bounded_retry_after("invalid") is None
    assert OpenAICompatibleProvider._bounded_retry_after("-1") == 0
    assert OpenAICompatibleProvider._bounded_retry_after("100") == 10


def test_request_id_sanitizer_rejects_empty_values() -> None:
    assert OpenAICompatibleProvider._safe_request_id(None) is None
    assert OpenAICompatibleProvider._safe_request_id("\r\n") is None


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


def test_provider_rejects_overlong_base_url() -> None:
    with pytest.raises(ConfigurationError, match="too long"):
        OpenAICompatibleProvider(base_url=f"https://example.test/{'x' * 2_100}")


@pytest.mark.asyncio
async def test_provider_adds_auth_to_and_closes_its_internal_client() -> None:
    provider = OpenAICompatibleProvider(api_key=" secret ")
    assert provider._client.headers["authorization"] == "Bearer secret"
    await provider.close()
    assert provider._client.is_closed


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
