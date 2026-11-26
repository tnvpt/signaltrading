"""Single-consumer, bounded async writer. Never silently discard records."""

import asyncio
from pathlib import Path

from .core import Recorder


class StorageOverloaded(RuntimeError):
    """The recording queue cannot accept another event safely."""


class StorageFailure(RuntimeError):
    """Disk failures must not be retried as exchange connection failures."""


class AsyncRecorder:
    def __init__(self, directory: Path, capacity=4096, batch_size=128):
        if capacity <= 0 or batch_size <= 0:
            raise ValueError("Writer capacity and batch size must be positive")
        self.recorder = Recorder(directory)
        self.queue = asyncio.Queue(maxsize=capacity)
        self.batch_size = batch_size
        self.task = None
        self.high_watermark = 0

    async def __aenter__(self):
        self.task = asyncio.create_task(self._run(), name="market-writer")
        return self

    def submit(self, kind, value, received_ms):
        if self.task is None:
            raise RuntimeError("Writer is not started")
        if self.task.done():
            self.task.result()  # Surface disk errors immediately.
            raise RuntimeError("Writer has stopped")
        try:
            self.queue.put_nowait((kind, value, received_ms))
        except asyncio.QueueFull as exc:
            raise StorageOverloaded("Recording queue full; capture aborted") from exc
        self.high_watermark = max(self.high_watermark, self.queue.qsize())

    def _write_batch(self, batch):
        try:
            for item in batch:
                self.recorder.write(*item)
        except OSError as exc:
            raise StorageFailure(str(exc)) from exc

    async def _run(self):
        try:
            while True:
                first = await self.queue.get()
                if first is None:
                    return
                batch = [first]
                while len(batch) < self.batch_size and not self.queue.empty():
                    item = self.queue.get_nowait()
                    if item is None:
                        await asyncio.to_thread(self._write_batch, batch)
                        return
                    batch.append(item)
                await asyncio.to_thread(self._write_batch, batch)
        finally:
            self.recorder.close()

    async def _close(self):
        if not self.task.done():
            put = asyncio.create_task(self.queue.put(None))
            done, _ = await asyncio.wait((put, self.task), return_when=asyncio.FIRST_COMPLETED)
            if self.task in done:
                put.cancel()
                await asyncio.gather(put, return_exceptions=True)
            else:
                await put
        await self.task

    async def __aexit__(self, exc_type, exc, tb):
        # Finish outstanding disk writes even on capture cancellation.
        closing = asyncio.create_task(self._close())
        try:
            await asyncio.shield(closing)
        except asyncio.CancelledError:
            await closing
            raise