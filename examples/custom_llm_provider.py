#!/usr/bin/env python3
"""Register a provider without coupling the engine to a vendor SDK."""

import asyncio
from collections.abc import Sequence

from samsarix_agent_engine import LLMAgentEngine
from samsarix_agent_engine.models import ChatMessage, ProviderResponse
from samsarix_agent_engine.providers import BaseLLMProvider


class CustomLLMProvider(BaseLLMProvider):
    """Small deterministic provider used only by this example."""

    async def invoke(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> ProviderResponse:
        del max_tokens, temperature
        prompt = next(message.content for message in reversed(messages) if message.role == "user")
        return ProviderResponse(content=f"{model} handled: {prompt}", model=model)


async def main():
    """Demonstrate the provider extension point."""

    engine = LLMAgentEngine()
    engine.register_provider("custom", CustomLLMProvider())
    agent = engine.create_agent(
        name="custom_agent",
        model="internal-model",
        system_prompt="You are powered by a custom LLM provider.",
        provider="custom",
    )
    print(await agent.invoke("hello"))
    await engine.close()


if __name__ == "__main__":
    asyncio.run(main())
