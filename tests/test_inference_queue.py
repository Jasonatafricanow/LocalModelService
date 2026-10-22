import asyncio

import pytest
from fastapi import HTTPException

from src.api.inference_queue import InferenceQueue


def test_capacity_waiter_cancellation_and_slot_reuse():
    async def scenario():
        queue = InferenceQueue(concurrency=1, max_waiting=1, timeout=1)
        release = await queue.acquire()
        waiter = asyncio.create_task(queue.acquire())
        await asyncio.sleep(0)
        with pytest.raises(HTTPException, match="full"):
            await queue.acquire()
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        next_waiter = asyncio.create_task(queue.acquire())
        await asyncio.sleep(0)
        assert not next_waiter.done()
        release()
        release()  # cleanup may run from both generator and response completion
        next_release = await next_waiter
        assert queue._slots.locked()
        next_release()
        (await queue.acquire())()
    asyncio.run(scenario())


def test_timeout_does_not_consume_a_later_slot():
    async def scenario():
        queue = InferenceQueue(concurrency=1, max_waiting=1, timeout=0.01)
        release = await queue.acquire()
        with pytest.raises(HTTPException, match="timed out"):
            await queue.acquire()
        release()
        (await queue.acquire())()
    asyncio.run(scenario())
