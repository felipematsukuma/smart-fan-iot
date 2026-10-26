"""Bound caller latency even when an OS DNS lookup ignores socket timeouts."""

from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore
from typing import Callable, TypeVar

T = TypeVar("T")


class BoundedIO:
    """No waiting queue: busy or timed-out callers fail without spawning work.

    Python cannot interrupt DNS in a worker. The slot stays occupied until the
    underlying operation finishes, so repeated timeouts cannot grow the queue.
    """

    def __init__(self, workers: int, timeout_seconds: float):
        self._slots = BoundedSemaphore(workers)
        self._executor = ThreadPoolExecutor(max_workers=workers)
        self._timeout_seconds = timeout_seconds

    def call(self, operation: Callable[[], T]) -> T:
        if not self._slots.acquire(blocking=False):
            raise TimeoutError("Storage operation capacity exhausted")

        def run() -> T:
            try:
                return operation()
            finally:
                self._slots.release()

        try:
            future = self._executor.submit(run)
        except RuntimeError:
            self._slots.release()
            raise
        return future.result(timeout=self._timeout_seconds)

    def close(self) -> None:
        self._executor.shutdown(wait=True)
