import asyncio
from typing import Any, Awaitable, Callable, List

from concurrent.futures import ThreadPoolExecutor

class DistributedExecutor:
    def __init__(self, max_workers: int = 4) -> None:
        self.max_workers = max_workers
        self._thread_pool = ThreadPoolExecutor(max_workers=max_workers)
        self._task_queue: asyncio.Queue = asyncio.Queue()

    async def submit(self, coro: Awaitable[Any]) -> Any:
        return await coro

    async def map(
        self, func: Callable[[Any], Any], items: List[Any]
    ) -> List[Any]:
        loop = asyncio.get_event_loop()
        futures = [
            loop.run_in_executor(self._thread_pool, func, item) for item in items
        ]
        return await asyncio.gather(*futures, return_exceptions=True)

    async def gather_async(self, *coros: Awaitable[Any]) -> List[Any]:
        return await asyncio.gather(*coros, return_exceptions=True)

    async def shutdown(self) -> None:
        self._thread_pool.shutdown(wait=True)
