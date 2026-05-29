import asyncio
from pydantic_ai import Agent
import pydantic_ai.messages as m

agent = Agent("test")

async def main():
    async for event in agent.run_stream_events("Say 'Hello world'"):
        if isinstance(event, m.PartStartEvent):
            print(f"Start: {type(event.part)} content={getattr(event.part, 'content', None)}")
        elif isinstance(event, m.PartDeltaEvent):
            delta = event.delta
            if isinstance(delta, m.TextPartDelta):
                print(f"Delta: '{delta.content_delta}'")
        elif isinstance(event, m.PartEndEvent):
            print(f"End: {type(event.part)} content={getattr(event.part, 'content', None)}")

asyncio.run(main())
