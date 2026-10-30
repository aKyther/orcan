"""UI input must work while discovery/details/brief filesystem probes are blocked."""

import asyncio
import threading
from unittest.mock import patch

from orcan_cockpit import peek_modal, picker
from textual.app import App, ComposeResult
from textual.widgets import Button, ListView, Static


async def until(predicate):
    async with asyncio.timeout(4):
        while not predicate():
            await asyncio.sleep(0.01)


async def check():
    rows_started, rows_release = threading.Event(), threading.Event()
    details_started, details_release = threading.Event(), threading.Event()
    calls = []
    rows = [
        {
            "name": name,
            "root": f"/fixture/{name}",
            "session": name,
            "live": False,
            "repo_count": 1,
            "projects": [{"name": name}],
        }
        for name in ("a", "b")
    ]

    def discover():
        calls.append(True)
        rows_started.set()
        assert rows_release.wait(5)
        return rows

    def project_label(project):
        if project["name"] == "a":
            details_started.set()
            assert details_release.wait(5)
            return "stale-branch"
        return "current-branch"

    class Harness(App):
        CSS = "#ping {dock:top;height:3;} WorkspaceList {height:1fr;}"
        presses = 0

        def compose(self) -> ComposeResult:
            yield Button("Ping", id="ping")
            yield picker.WorkspaceList()

        def on_button_pressed(self, event):
            if event.button.id == "ping":
                self.presses += 1

    try:
        with (
            patch.object(picker, "list_workspace_rows", discover),
            patch.object(picker, "read_recent_sessions", list),
            patch.object(picker, "project_git_label", project_label),
            patch.object(picker, "glance_lines", lambda *a, **k: []),
        ):
            app = Harness()
            async with app.run_test(size=(120, 40)) as pilot:
                listing = app.query_one(picker.WorkspaceList)
                await until(rows_started.is_set)
                for _ in range(20):
                    listing.refresh_rows()
                    await asyncio.sleep(0)
                await pilot.click("#ping")
                assert app.presses == 1 and len(calls) == 1
                rows_release.set()
                await until(lambda: len(listing.rows) == 2)
                view = listing.query_one(ListView)
                view.index = 0
                view.focus()
                await pilot.press("i")
                await until(details_started.is_set)
                await pilot.pause(0.3)
                await pilot.click("#ping")
                assert app.presses == 2
                view.index = 1
                await pilot.pause()
                details_release.set()
                details = listing.query_one("#workspace-details", Static)
                await until(lambda: "current-branch" in str(details.render()))
                assert "stale-branch" not in str(details.render())

                brief_started, brief_release = threading.Event(), threading.Event()

                def brief(_root):
                    brief_started.set()
                    assert brief_release.wait(5)
                    return "fixture brief"

                try:
                    with patch.object(peek_modal, "build_peek_text", brief):
                        await app.push_screen(peek_modal.PeekModal("/fixture"))
                        await until(brief_started.is_set)
                        await pilot.press("escape")
                        assert not isinstance(app.screen, peek_modal.PeekModal)
                finally:
                    brief_release.set()
    finally:
        rows_release.set()
        details_release.set()


async def check_restore():
    from orcan_cockpit import app as cockpit_app

    started, release = threading.Event(), threading.Event()
    selected = []
    row = {
        "name": "saved",
        "session": "saved",
        "root": "/fixture",
        "live": False,
        "repo_count": 0,
        "projects": [],
    }

    def discover():
        started.set()
        assert release.wait(5)
        return [row]

    async def attach(screen, selected_row):
        selected.append(selected_row["session"])
        screen._current_session = selected_row["session"]

    try:
        with (
            patch.object(picker, "list_workspace_rows", discover),
            patch.object(picker, "read_recent_sessions", list),
            patch.object(cockpit_app, "read_last_session", lambda: "saved"),
            patch.object(cockpit_app, "onboarding_already_seen", lambda: True),
            patch.object(cockpit_app.MainScreen, "select_workspace", attach),
        ):
            app = cockpit_app.CockpitApp()
            async with app.run_test(size=(120, 40)) as pilot:
                await until(started.is_set)
                await pilot.press("f1")
                await pilot.press("escape")
                assert not selected
                release.set()
                await until(lambda: selected == ["saved"])
    finally:
        release.set()


if __name__ == "__main__":
    asyncio.run(check())
    asyncio.run(check_restore())
    print(
        "Cockpit responsiveness passed: blocked probes, input, bounded work, stale-result rejection, brief dismissal"
    )
