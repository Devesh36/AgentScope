"""An actual local agent execution: no fabricated LLM usage or responses."""

import asyncio
import os

from agentscope_sdk import AgentScope


async def main():
    with AgentScope(
        endpoint=os.getenv("AGENTSCOPE_ENDPOINT", "http://localhost:8000"),
        api_key=os.environ["AGENTSCOPE_API_KEY"],
        agent_name="local-calculator",
    ) as scope:

        @scope.trace_tool
        async def calculate_total(values):
            await asyncio.sleep(0.05)
            return sum(values)

        @scope.trace_agent
        async def run_agent():
            values = [3, 5, 8, 13]
            total = await calculate_total(values)
            scope.heartbeat("calculation complete")
            return total

        print("Computed total:", await run_agent())
    print("Exporter counters:", scope.stats)


if __name__ == "__main__":
    asyncio.run(main())
