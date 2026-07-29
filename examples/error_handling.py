#!/usr/bin/env python3
"""Handle a local request-budget error without a surprise network fallback."""

import asyncio

from samsarix_agent_engine import BudgetExceededError, LLMAgentEngine


async def main():
    """Show the deterministic failure and recovery contract."""

    engine = LLMAgentEngine(max_requests_per_session=1)
    agent = engine.create_agent(
        name="bounded_agent",
        model="echo",
        system_prompt="You are a helpful assistant.",
    )

    print(await agent.invoke("first request"))
    try:
        await agent.invoke("second request")
    except BudgetExceededError as exc:
        print(f"blocked: {exc}")

    agent.clear_history()
    print(await agent.invoke("after explicit reset"))
    await engine.close()


if __name__ == "__main__":
    asyncio.run(main())
