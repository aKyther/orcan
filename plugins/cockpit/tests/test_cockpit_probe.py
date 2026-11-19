"""Cancellation cannot create a new blocking probe while the previous one lives."""

import asyncio
import threading

from orcan_cockpit.probe import SingleFlightProbe


def test_cancelled_waiters_share_one_thread_and_new_keys_receive_fresh_data():
    async def check():
        probe = SingleFlightProbe()
        started, release = threading.Event(), threading.Event()
        calls = []

        def slow():
            calls.append("old")
            started.set()
            assert release.wait(5)
            return "old"

        first = asyncio.create_task(probe.read("old", slow))
        try:
            while not started.is_set():
                await asyncio.sleep(0.001)
            first.cancel()
            await asyncio.gather(first, return_exceptions=True)
            for _ in range(20):
                waiter = asyncio.create_task(probe.read("old", slow))
                await asyncio.sleep(0)
                waiter.cancel()
                await asyncio.gather(waiter, return_exceptions=True)
            assert calls == ["old"]
            latest = asyncio.create_task(probe.read("new", lambda: "new"))
            await asyncio.sleep(0)
            assert not latest.done()
            release.set()
            assert await asyncio.wait_for(latest, 2) == "new"
        finally:
            release.set()

    asyncio.run(check())


def test_obsolete_failure_does_not_replace_a_new_view_with_an_error():
    async def check():
        probe = SingleFlightProbe()
        started, release = threading.Event(), threading.Event()

        def fail():
            started.set()
            assert release.wait(5)
            raise OSError("synthetic unavailable old filesystem")

        old = asyncio.create_task(probe.read("old", fail))
        try:
            while not started.is_set():
                await asyncio.sleep(0.001)
            old.cancel()
            await asyncio.gather(old, return_exceptions=True)
            new = asyncio.create_task(probe.read("new", lambda: "current"))
            await asyncio.sleep(0)
            release.set()
            assert await asyncio.wait_for(new, 2) == "current"
        finally:
            release.set()

    asyncio.run(check())
