"""Isolated Textual smoke: open, refresh and close Jobs without a real executor."""

import asyncio

from orcan_cockpit import jobs_modal
from textual.app import App
from textual.widgets import Static


async def main():
    calls = []

    async def overview():
        calls.append(True)
        return {
            "counts": {"queued": 2},
            "settings": {"max_running": 2},
            "lanes": {"heavy": {"ready": False, "configured": True}},
            "jobs": [],
        }

    jobs_modal.read_overview = overview
    app = App()
    async with app.run_test(size=(120, 40)) as pilot:
        await app.push_screen(jobs_modal.JobsModal())
        await pilot.pause()
        assert len(calls) == 1
        assert "Queue heavy: configured, unavailable" in str(
            app.screen.query_one("#jobs-body", Static).render()
        )
        await pilot.click("#jobs-refresh")
        await pilot.pause()
        assert len(calls) == 2
        await pilot.press("escape")
        assert not isinstance(app.screen, jobs_modal.JobsModal)


if __name__ == "__main__":
    asyncio.run(main())
