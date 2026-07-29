#!/usr/bin/env python3
"""Run a bounded two-agent collaboration using the offline provider."""

import asyncio

from samsarix_agent_engine import AgentOrchestrator, LLMAgentEngine


async def main():
    """Demonstrate explicit amplification limits."""

    engine = LLMAgentEngine(max_requests_per_session=2)
    sage = engine.create_agent(
        name="sage",
        model="echo",
        system_prompt="Identify one useful constraint.",
    )
    architect = engine.create_agent(
        name="architect",
        model="echo",
        system_prompt="Turn the prior contribution into a next step.",
    )

    orchestrator = AgentOrchestrator(max_agents=2)
    orchestrator.add_agent(sage)
    orchestrator.add_agent(architect)

    result = await orchestrator.collective_loop(
        prompt="Design a safe setup check",
        max_iterations=1,
    )
    print(result)
    await engine.close()


if __name__ == "__main__":
    asyncio.run(main())
