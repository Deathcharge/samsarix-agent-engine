# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Built-in provider implementations.

The network provider intentionally targets the small OpenAI-compatible chat
surface instead of embedding many vendor SDKs. Applications can implement
``BaseLLMProvider`` when their provider uses a different protocol.
"""

from __future__ import annotations

import asyncio
import json
import math
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from typing import Any
from urllib.parse import urlsplit

import httpx

from .errors import ConfigurationError, InputValidationError, ProviderError
from .models import (
    ChatMessage,
    ProviderResponse,
    ProviderStreamChunk,
    ToolCall,
    ToolDefinition,
    ToolMessage,
    ToolProviderResponse,
)

_RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}


class BaseLLMProvider(ABC):
    """Minimal extension point for model providers."""

    @abstractmethod
    async def invoke(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> ProviderResponse | str:
        """Return one complete model response."""

    async def close(self) -> None:
        """Release provider resources. Stateless providers need no cleanup."""
        return None

    async def invoke_tools(
        self,
        messages: Sequence[ToolMessage],
        model: str,
        tools: Sequence[ToolDefinition],
        *,
        max_tokens: int,
        temperature: float,
    ) -> ToolProviderResponse:
        """Return tool calls or final text; providers opt in by overriding this method."""

        del messages, model, tools, max_tokens, temperature
        raise ProviderError("provider does not support tool calls")

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[ProviderStreamChunk]:
        """Stream normalized events, falling back to one complete invocation.

        Existing custom providers remain compatible without implementing native
        streaming. Providers that override this method must emit exactly one final
        chunk.
        """

        response = await self.invoke(
            messages,
            model,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if isinstance(response, str):
            response = ProviderResponse(content=response, model=model)
        yield ProviderStreamChunk(
            delta=response.content,
            final=True,
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
        )


class EchoProvider(BaseLLMProvider):
    """Deterministic offline provider for setup checks, examples, and tests.

    EchoProvider is not an LLM and is never selected as a hidden fallback after
    a network provider fails.
    """

    def __init__(self, prefix: str = "Echo") -> None:
        if not isinstance(prefix, str) or not prefix.strip():
            raise ConfigurationError("echo prefix must be a non-empty string")
        self.prefix = prefix.strip()

    async def invoke(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> ProviderResponse:
        del max_tokens, temperature
        user_messages = [message.content for message in messages if message.role == "user"]
        if not user_messages:
            raise ProviderError("echo provider received no user message")
        return ProviderResponse(content=f"{self.prefix}: {user_messages[-1]}", model=model)


class OpenAICompatibleProvider(BaseLLMProvider):
    """Bounded client for an OpenAI-compatible ``chat/completions`` endpoint."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 30.0,
        max_retries: int = 2,
        retry_backoff: float = 0.5,
        max_response_bytes: int = 2_000_000,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.endpoint = self._validate_endpoint(base_url)
        if api_key is not None and (not isinstance(api_key, str) or not api_key.strip()):
            raise ConfigurationError("api_key must be a non-empty string when supplied")
        if not 0 < timeout <= 300:
            raise ConfigurationError("timeout must be greater than 0 and at most 300 seconds")
        if not isinstance(max_retries, int) or not 0 <= max_retries <= 5:
            raise ConfigurationError("max_retries must be an integer between 0 and 5")
        if not 0 <= retry_backoff <= 10:
            raise ConfigurationError("retry_backoff must be between 0 and 10 seconds")
        if not 1_024 <= max_response_bytes <= 10_000_000:
            raise ConfigurationError("max_response_bytes must be between 1024 and 10000000")

        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.max_response_bytes = max_response_bytes
        self._owns_client = client is None
        headers = {"Accept": "application/json", "User-Agent": "samsarix-agent-engine/0.1"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key.strip()}"
        self._client = client or httpx.AsyncClient(
            headers=headers,
            timeout=httpx.Timeout(timeout),
            follow_redirects=False,
        )

    @staticmethod
    def _validate_endpoint(base_url: str) -> str:
        if not isinstance(base_url, str) or not base_url.strip():
            raise ConfigurationError("base_url must be a non-empty URL")
        if len(base_url) > 2_048:
            raise ConfigurationError("base_url is too long")
        parsed = urlsplit(base_url.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ConfigurationError("base_url must be an absolute http or https URL")
        if parsed.username is not None or parsed.password is not None:
            raise ConfigurationError("base_url must not contain credentials")
        if parsed.query or parsed.fragment:
            raise ConfigurationError("base_url must not contain a query string or fragment")
        normalized = base_url.strip().rstrip("/")
        if parsed.path.rstrip("/").endswith("/chat/completions"):
            return normalized
        return f"{normalized}/chat/completions"

    async def invoke(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> ProviderResponse:
        payload = {
            "model": model,
            "messages": [message.as_dict() for message in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }

        response = await self._send_with_retries(payload)
        try:
            try:
                data = await self._read_bounded_json(response)
            except httpx.TimeoutException as exc:
                raise ProviderError("provider response timed out", retryable=True) from exc
            except httpx.RequestError as exc:
                raise ProviderError("provider response failed", retryable=True) from exc
        finally:
            await response.aclose()

        return self._normalize_response(data, requested_model=model)

    async def invoke_tools(
        self,
        messages: Sequence[ToolMessage],
        model: str,
        tools: Sequence[ToolDefinition],
        *,
        max_tokens: int,
        temperature: float,
    ) -> ToolProviderResponse:
        """Request OpenAI-compatible function calls with parallel execution disabled."""

        payload = {
            "model": model,
            "messages": [message.as_dict() for message in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
            "tools": [tool.as_dict() for tool in tools],
            "tool_choice": "auto",
            "parallel_tool_calls": False,
        }
        response = await self._send_with_retries(payload)
        try:
            try:
                data = await self._read_bounded_json(response)
            except httpx.TimeoutException as exc:
                raise ProviderError("provider response timed out", retryable=True) from exc
            except httpx.RequestError as exc:
                raise ProviderError("provider response failed", retryable=True) from exc
        finally:
            await response.aclose()
        return self._normalize_tool_response(data, requested_model=model)

    async def stream(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> AsyncIterator[ProviderStreamChunk]:
        """Stream bounded text deltas from an OpenAI-compatible SSE response."""

        payload = {
            "model": model,
            "messages": [message.as_dict() for message in messages],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        response = await self._send_with_retries(payload)
        emitted = False
        served_model = model
        input_tokens: int | None = None
        output_tokens: int | None = None
        try:
            try:
                async for data in self._iter_sse_json(response):
                    event_model = data.get("model")
                    if isinstance(event_model, str):
                        served_model = event_model
                    usage = data.get("usage")
                    if isinstance(usage, dict):
                        prompt_tokens = usage.get("prompt_tokens")
                        completion_tokens = usage.get("completion_tokens")
                        if isinstance(prompt_tokens, int) and not isinstance(prompt_tokens, bool):
                            input_tokens = prompt_tokens
                        if isinstance(completion_tokens, int) and not isinstance(
                            completion_tokens, bool
                        ):
                            output_tokens = completion_tokens

                    choices = data.get("choices")
                    if choices in (None, []):
                        continue
                    if not isinstance(choices, list) or not isinstance(choices[0], dict):
                        raise ProviderError(
                            "provider stream did not match the chat completion schema"
                        )
                    delta_object = choices[0].get("delta")
                    if not isinstance(delta_object, dict):
                        raise ProviderError(
                            "provider stream did not match the chat completion schema"
                        )
                    delta = delta_object.get("content")
                    if delta is None:
                        continue
                    if not isinstance(delta, str):
                        raise ProviderError("provider stream contained invalid text content")
                    if delta:
                        emitted = True
                        yield ProviderStreamChunk(delta=delta, model=served_model)
            except httpx.TimeoutException as exc:
                raise ProviderError("provider stream timed out", retryable=True) from exc
            except httpx.RequestError as exc:
                raise ProviderError("provider stream failed", retryable=True) from exc
        finally:
            await response.aclose()

        if not emitted:
            raise ProviderError("provider stream contained no text content")
        yield ProviderStreamChunk(
            final=True,
            model=served_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

    async def _send_with_retries(self, payload: dict[str, Any]) -> httpx.Response:
        for attempt in range(self.max_retries + 1):
            try:
                request = self._client.build_request("POST", self.endpoint, json=payload)
                response = await self._client.send(request, stream=True)
            except httpx.TimeoutException as exc:
                if attempt < self.max_retries:
                    await self._sleep_before_retry(attempt)
                    continue
                raise ProviderError("provider request timed out", retryable=True) from exc
            except httpx.RequestError as exc:
                if attempt < self.max_retries:
                    await self._sleep_before_retry(attempt)
                    continue
                raise ProviderError("provider request failed", retryable=True) from exc

            status = response.status_code
            if status in _RETRYABLE_STATUS_CODES and attempt < self.max_retries:
                retry_after = self._bounded_retry_after(response.headers.get("retry-after"))
                await response.aclose()
                await self._sleep_before_retry(attempt, retry_after)
                continue
            if not 200 <= status < 300:
                request_id = self._safe_request_id(response.headers.get("x-request-id"))
                suffix = f" (request {request_id})" if request_id else ""
                await response.aclose()
                raise ProviderError(
                    f"provider returned HTTP {status}{suffix}",
                    status_code=status,
                    retryable=status in _RETRYABLE_STATUS_CODES,
                )
            return response

        raise ProviderError("provider request exhausted its retry budget", retryable=True)

    async def _iter_sse_json(self, response: httpx.Response) -> AsyncIterator[dict[str, Any]]:
        buffer = bytearray()
        event_data: list[bytes] = []
        size = 0

        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > self.max_response_bytes:
                raise ProviderError("provider stream exceeded the configured size limit")
            buffer.extend(chunk)
            while True:
                newline = buffer.find(b"\n")
                if newline < 0:
                    break
                line = bytes(buffer[:newline]).rstrip(b"\r")
                del buffer[: newline + 1]
                if not line:
                    if event_data:
                        payload = b"\n".join(event_data)
                        event_data.clear()
                        if payload.strip() == b"[DONE]":
                            return
                        yield self._decode_sse_payload(payload)
                    continue
                if line.startswith(b"data:"):
                    event_data.append(line[5:].lstrip())

        if buffer:
            line = bytes(buffer).rstrip(b"\r")
            if line.startswith(b"data:"):
                event_data.append(line[5:].lstrip())
        if event_data:
            payload = b"\n".join(event_data)
            if payload.strip() != b"[DONE]":
                yield self._decode_sse_payload(payload)

    @staticmethod
    def _decode_sse_payload(payload: bytes) -> dict[str, Any]:
        try:
            data: Any = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderError("provider stream contained invalid JSON") from exc
        if not isinstance(data, dict):
            raise ProviderError("provider stream contained an invalid event")
        return data

    async def _read_bounded_json(self, response: httpx.Response) -> Any:
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > self.max_response_bytes:
                raise ProviderError("provider response exceeded the configured size limit")
            chunks.append(chunk)
        try:
            return json.loads(b"".join(chunks))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProviderError("provider returned invalid JSON") from exc

    @staticmethod
    def _normalize_response(data: Any, *, requested_model: str) -> ProviderResponse:
        try:
            choice = data["choices"][0]
            content = choice["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                "provider response did not match the chat completion schema"
            ) from exc
        if not isinstance(content, str) or not content:
            raise ProviderError("provider response contained no text content")

        usage = data.get("usage", {}) if isinstance(data, dict) else {}
        input_tokens = usage.get("prompt_tokens") if isinstance(usage, dict) else None
        output_tokens = usage.get("completion_tokens") if isinstance(usage, dict) else None
        model = data.get("model", requested_model) if isinstance(data, dict) else requested_model
        return ProviderResponse(
            content=content,
            model=model if isinstance(model, str) else requested_model,
            input_tokens=input_tokens if isinstance(input_tokens, int) else None,
            output_tokens=output_tokens if isinstance(output_tokens, int) else None,
        )

    @staticmethod
    def _normalize_tool_response(data: Any, *, requested_model: str) -> ToolProviderResponse:
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(
                "provider response did not match the tool completion schema"
            ) from exc
        if not isinstance(message, dict):
            raise ProviderError("provider response did not match the tool completion schema")
        content = message.get("content")
        if content is not None and (not isinstance(content, str) or not content):
            raise ProviderError("provider tool response contained invalid text content")
        raw_calls = message.get("tool_calls") or []
        if not isinstance(raw_calls, list):
            raise ProviderError("provider response did not match the tool completion schema")
        calls: list[ToolCall] = []
        for raw_call in raw_calls:
            try:
                if not isinstance(raw_call, dict) or raw_call.get("type") != "function":
                    raise TypeError
                function = raw_call["function"]
                if not isinstance(function, dict):
                    raise TypeError
                call = ToolCall(
                    call_id=raw_call["id"],
                    name=function["name"],
                    arguments=function["arguments"],
                )
            except (KeyError, TypeError, InputValidationError) as exc:
                raise ProviderError(
                    "provider response contained an invalid function tool call"
                ) from exc
            calls.append(call)

        usage = data.get("usage", {}) if isinstance(data, dict) else {}
        input_tokens = usage.get("prompt_tokens") if isinstance(usage, dict) else None
        output_tokens = usage.get("completion_tokens") if isinstance(usage, dict) else None
        served_model = (
            data.get("model", requested_model) if isinstance(data, dict) else requested_model
        )
        try:
            return ToolProviderResponse(
                content=content,
                tool_calls=tuple(calls),
                model=served_model if isinstance(served_model, str) else requested_model,
                input_tokens=(
                    input_tokens
                    if isinstance(input_tokens, int)
                    and not isinstance(input_tokens, bool)
                    and input_tokens >= 0
                    else None
                ),
                output_tokens=(
                    output_tokens
                    if isinstance(output_tokens, int)
                    and not isinstance(output_tokens, bool)
                    and output_tokens >= 0
                    else None
                ),
            )
        except InputValidationError as exc:
            raise ProviderError("provider tool response contained no usable output") from exc

    @staticmethod
    def _bounded_retry_after(value: str | None) -> float | None:
        if value is None:
            return None
        try:
            parsed = float(value)
            return min(max(parsed, 0.0), 10.0) if math.isfinite(parsed) else None
        except ValueError:
            return None

    @staticmethod
    def _safe_request_id(value: str | None) -> str | None:
        if value is None:
            return None
        sanitized = "".join(
            character
            for character in value[:256]
            if character.isascii() and (character.isalnum() or character in "-_.:")
        )
        return sanitized[:128] or None

    async def _sleep_before_retry(self, attempt: int, retry_after: float | None = None) -> None:
        delay = retry_after if retry_after is not None else self.retry_backoff * (2**attempt)
        if delay:
            await asyncio.sleep(min(delay, 10.0))

    async def close(self) -> None:
        """Close the internally created HTTP client."""

        if self._owns_client and not self._client.is_closed:
            await self._client.aclose()
