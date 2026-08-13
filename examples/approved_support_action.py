#!/usr/bin/env python3
"""Execute an in-memory support action only after an explicit operator decision."""

import asyncio
import json
from collections.abc import Sequence

from samsarix_agent_engine import (
    ApprovalDecision,
    ApprovalRequest,
    BaseLLMProvider,
    ChatMessage,
    JsonValue,
    LLMAgentEngine,
    ProviderError,
    ProviderResponse,
    ToolCall,
    ToolDefinition,
    ToolMessage,
    ToolProviderResponse,
)

TICKETS: dict[str, dict[str, str]] = {"T-42": {"status": "open", "owner": "billing"}}


class DeterministicSupportToolProvider(BaseLLMProvider):
    """Offline protocol fixture that requests one tool and then summarizes its result."""

    async def invoke(
        self,
        messages: Sequence[ChatMessage],
        model: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> ProviderResponse:
        del messages, model, max_tokens, temperature
        raise ProviderError("this fixture supports the explicit tool path only")

    async def invoke_tools(
        self,
        messages: Sequence[ToolMessage],
        model: str,
        tools: Sequence[ToolDefinition],
        *,
        max_tokens: int,
        temperature: float,
    ) -> ToolProviderResponse:
        del tools, max_tokens, temperature
        if messages[-1].role == "user":
            return ToolProviderResponse(
                tool_calls=(
                    ToolCall(
                        call_id="call-close-T-42",
                        name="close_ticket",
                        arguments='{"ticket_id":"T-42"}',
                    ),
                ),
                model=model,
            )
        if messages[-1].role != "tool" or messages[-1].content is None:
            raise ProviderError("unexpected deterministic tool transcript")
        result = json.loads(messages[-1].content)
        return ToolProviderResponse(
            content=f"Ticket {result['ticket_id']} is now {result['status']}.",
            model=model,
        )


def close_ticket(arguments: dict[str, JsonValue]) -> JsonValue:
    """Validate arguments and perform an idempotent in-memory state transition."""

    ticket_id = arguments.get("ticket_id")
    if not isinstance(ticket_id, str) or ticket_id not in TICKETS:
        raise ValueError("ticket_id must identify an existing ticket")
    TICKETS[ticket_id]["status"] = "closed"
    return {"ticket_id": ticket_id, "status": TICKETS[ticket_id]["status"]}


async def approve_known_ticket(request: ApprovalRequest) -> ApprovalDecision:
    """A real application would present this request to an authenticated operator."""

    approved = request.arguments.get("ticket_id") == "T-42"
    return ApprovalDecision(
        approved=approved,
        reason=None if approved else "ticket is outside the demo policy",
    )


async def main() -> None:
    engine = LLMAgentEngine(max_requests_per_session=4, max_tool_rounds=3, max_tool_calls=1)
    engine.register_provider("support-tools", DeterministicSupportToolProvider())
    agent = engine.create_agent(
        name="support_operator",
        model="offline-tool-fixture",
        provider="support-tools",
        system_prompt="Use the approved support tools and report the final state.",
    )
    close_tool = ToolDefinition(
        name="close_ticket",
        description="Close an existing support ticket after operator approval.",
        parameters={
            "type": "object",
            "properties": {"ticket_id": {"type": "string"}},
            "required": ["ticket_id"],
            "additionalProperties": False,
        },
        handler=close_ticket,
    )

    answer = await agent.run_tools(
        "Close ticket T-42.",
        [close_tool],
        approval_handler=approve_known_ticket,
        session_id="operator-demo",
    )

    print(answer)
    print(f"stored_status={TICKETS['T-42']['status']}")
    print("events=" + ",".join(event.event_type for event in agent.events()))
    await engine.close()


if __name__ == "__main__":
    asyncio.run(main())
