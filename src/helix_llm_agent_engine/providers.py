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
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlsplit

import httpx

from .errors import ConfigurationError, ProviderError
from .models import ChatMessage, ProviderResponse

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
        headers = {"Accept": "application/json", "User-Agent": "helix-llm-agent-engine/0.1"}
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

            try:
                status = response.status_code
                if status in _RETRYABLE_STATUS_CODES and attempt < self.max_retries:
                    retry_after = self._bounded_retry_after(response.headers.get("retry-after"))
                    await response.aclose()
                    await self._sleep_before_retry(attempt, retry_after)
                    continue
                if not 200 <= status < 300:
                    request_id = self._safe_request_id(response.headers.get("x-request-id"))
                    suffix = f" (request {request_id})" if request_id else ""
                    raise ProviderError(
                        f"provider returned HTTP {status}{suffix}",
                        status_code=status,
                        retryable=status in _RETRYABLE_STATUS_CODES,
                    )
                data = await self._read_bounded_json(response)
            finally:
                await response.aclose()

            return self._normalize_response(data, requested_model=model)

        raise ProviderError("provider request exhausted its retry budget", retryable=True)

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
