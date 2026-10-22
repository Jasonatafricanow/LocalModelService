"""A bounded, process-local inference queue shared by native and compatible chat."""
import asyncio
import os

from fastapi import HTTPException


class InferenceQueue:
    def __init__(self, concurrency=1, max_waiting=8, timeout=30.0):
        if concurrency < 1 or max_waiting < 0 or timeout <= 0:
            raise ValueError("invalid inference queue limits")
        self._slots = asyncio.Semaphore(concurrency)
        self._waiting = 0
        self._max_waiting = max_waiting
        self._timeout = timeout

    async def acquire(self):
        if self._slots.locked() and self._waiting >= self._max_waiting:
            raise HTTPException(503, "Inference queue is full", headers={"Retry-After": "3"})
        if not self._slots.locked():
            # Semaphore.acquire completes without suspending when a slot is free.
            await self._slots.acquire()
        else:
            self._waiting += 1
            try:
                await asyncio.wait_for(self._slots.acquire(), self._timeout)
            except TimeoutError as exc:
                raise HTTPException(503, "Inference queue timed out", headers={"Retry-After": "3"}) from exc
            finally:
                self._waiting -= 1
        released = False

        def release():
            nonlocal released
            if not released:
                released = True
                self._slots.release()
        return release


inference_queue = InferenceQueue(
    int(os.getenv("OPENCLAW_INFERENCE_CONCURRENCY", "1")),
    int(os.getenv("OPENCLAW_INFERENCE_MAX_WAITING", "8")),
    float(os.getenv("OPENCLAW_INFERENCE_WAIT_SECONDS", "30")),
)
