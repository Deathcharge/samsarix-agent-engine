#!/usr/bin/env python3
"""Run a real agent journey without credentials or network access."""

import asyncio

from helix_llm_agent_engine import LLMAgentEngine


async def main():
    """Create an offline agent, invoke it, and inspect the recorded turn."""

    engine = LLMAgentEngine()
    agent = engine.create_agent(
        name="setup_check",
        model="echo",
        system_prompt="Verify that the local package works.",
    )

    response = await agent.invoke("installation complete", session_id="demo")
    print(response)
    print(f"history_messages={len(agent.history('demo'))}")
    print(f"successful_requests={agent.get_metrics()['successes']}")

    await engine.close()


if __name__ == "__main__":
    asyncio.run(main())
