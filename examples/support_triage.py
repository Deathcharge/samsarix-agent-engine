#!/usr/bin/env python3
"""Route a support ticket with strict output, guardrails, events, and a snapshot."""

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

from samsarix_agent_engine import (
    BaseLLMProvider,
    ChatMessage,
    GuardrailContext,
    GuardrailResult,
    JsonValue,
    LLMAgentEngine,
    ProviderResponse,
)


class DeterministicTriageProvider(BaseLLMProvider):
    """Offline fixture standing in for a model that was prompted to return JSON."""

    async def invoke(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> ProviderResponse:
        del messages, max_tokens, temperature
        return ProviderResponse(
            content='{"priority":2,"queue":"billing","summary":"Duplicate charge"}',
            model=model,
            input_tokens=18,
            output_tokens=12,
        )


@dataclass(frozen=True)
class TicketRoute:
    queue: str
    priority: int
    summary: str


def validate_route(value: JsonValue) -> TicketRoute:
    """Validate every model-owned field before downstream automation uses it."""

    if not isinstance(value, dict):
        raise ValueError("route must be an object")
    queue = value.get("queue")
    priority = value.get("priority")
    summary = value.get("summary")
    if queue not in {"billing", "technical", "general"}:
        raise ValueError("unsupported queue")
    if isinstance(priority, bool) or not isinstance(priority, int) or priority not in {1, 2, 3}:
        raise ValueError("priority must be 1, 2, or 3")
    if not isinstance(summary, str) or not 1 <= len(summary) <= 120:
        raise ValueError("summary must contain 1-120 characters")
    return TicketRoute(queue=queue, priority=priority, summary=summary)


def reject_credentials(text: str, context: GuardrailContext) -> GuardrailResult:
    """Example policy that blocks obvious credential material on either boundary."""

    lowered = text.lower()
    if "api_key=" in lowered or "private key" in lowered:
        return GuardrailResult(allowed=False, reason=f"credential-like {context.stage}")
    return GuardrailResult(allowed=True)


async def main() -> None:
    engine = LLMAgentEngine(max_requests_per_session=5)
    engine.register_provider("triage", DeterministicTriageProvider())
    agent = engine.create_agent(
        name="support_triage",
        model="offline-triage-fixture",
        provider="triage",
        system_prompt="Return only a support routing JSON object.",
        input_guardrails=(reject_credentials,),
        output_guardrails=(reject_credentials,),
    )

    route = await agent.invoke_structured(
        "Customer reports a duplicate charge on invoice INV-42.",
        validate_route,
        session_id="ticket-T-42",
    )
    snapshot = await agent.export_session("ticket-T-42")

    print(f"route={route.queue} priority={route.priority} summary={route.summary}")
    print("events=" + ",".join(event.event_type for event in agent.events()))
    print(f"snapshot_chars={len(snapshot.to_json())}")
    await engine.close()


if __name__ == "__main__":
    asyncio.run(main())
