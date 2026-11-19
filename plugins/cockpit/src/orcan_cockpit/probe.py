"""Single in-flight blocking probe, even when its UI awaiter is cancelled."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


class SingleFlightProbe:
    """Keep timer refreshes from piling up executor threads on slow filesystems.

    UI callers cancel obsolete awaiters and check their view generation before
    painting. Cancelling asyncio.to_thread alone cannot stop its underlying I/O.
    """

    def __init__(self) -> None:
        self._task: asyncio.Task[Any] | None = None
        self._key: object = None

    @staticmethod
    def _observe(task: asyncio.Task[Any]) -> None:
        if not task.cancelled():
            task.exception()  # Retrieve errors even if the UI waiter disappeared.

    async def read(self, key: object, function: Callable[[], T]) -> T:
        while True:
            if self._task is None or self._task.done():
                self._key = key
                self._task = asyncio.create_task(asyncio.to_thread(function))
                self._task.add_done_callback(self._observe)
            task, task_key = self._task, self._key
            try:
                result = await asyncio.shield(task)
            except asyncio.CancelledError:
                raise
            except Exception:
                if task_key == key:
                    raise
                continue
            if task_key == key:
                return result
