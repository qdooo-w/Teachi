import asyncio
from pydantic_ai import Agent

agent = Agent("test")

async def main():
    async for event in agent.run_stream_events("Hello"):
        print(event)

asyncio.run(main())
