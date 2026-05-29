import asyncio

async def test():
    queue = asyncio.Queue()
    queue.put_nowait(1)
    queue.put_nowait(2)

    async def run():
        pass # Completes immediately

    run_task = asyncio.create_task(run())

    while True:
        queue_task = asyncio.create_task(queue.get())
        done, pending = await asyncio.wait(
            {queue_task, run_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        print("done:", len(done), "pending:", len(pending))
        if queue_task in done:
            print("yield:", queue_task.result())
            continue
        if run_task in done:
            print("run_task done, break")
            queue_task.cancel()
            break

asyncio.run(test())
