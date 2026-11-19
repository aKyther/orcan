"""Isolated Textual smoke: open, refresh and close Jobs without a real executor."""

import asyncio

from orcan_cockpit import jobs_modal
from textual.app import App
from textual.widgets import Static


async def main():
    calls = []
    unavailable = False

    async def overview():
        calls.append(True)
        if unavailable:
            raise OSError("offline")
        return {
            "counts": {"queued": 2},
            "settings": {"max_running": 2},
            "lanes": {"heavy": {"ready": False, "configured": True}},
            "jobs": [{"id": "abc123", "status": "failed", "task": "Check",
                      "profile": "selected", "repo": "/tmp/project", "sha": "123abc",
                      "acknowledged": None}],
        }

    jobs_modal.read_overview = overview
    app = App()
    async with app.run_test(size=(120, 40)) as pilot:
        await app.push_screen(jobs_modal.JobsModal([
            {"name": "Example", "session": "example", "projects": [{"path": "/tmp/project"}]}
        ]))
        await pilot.pause()
        assert len(calls) == 1
        assert "Queue heavy: configured, unavailable" in str(
            app.screen.query_one("#jobs-body", Static).render()
        )
        await pilot.click("#jobs-refresh")
        await pilot.pause()
        assert len(calls) == 2
        assert "Result awaiting receipt" in str(app.screen.query_one("#jobs-body", Static).render())
        assert app.screen._targets["jobs-workspace-0"]["session"] == "example"
        unavailable = True
        await pilot.pause(0.3)
        await pilot.click("#jobs-refresh")
        await pilot.pause()
        assert not app.screen._targets
        assert not app.screen.query("#jobs-targets Button")
        unavailable = False
        await pilot.pause(0.3)
        await pilot.click("#jobs-refresh")
        await pilot.pause()
        await pilot.click("#jobs-workspace-0")
        assert not isinstance(app.screen, jobs_modal.JobsModal)


if __name__ == "__main__":
    asyncio.run(main())
