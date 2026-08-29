#!/usr/bin/env python3
"""Exercise the real Textual cockpit and its embedded tmux PTY."""

import asyncio

from textual.widgets import Button, ListItem, ListView, Static

from orcan_cockpit.activity import WorkspaceActivity
from orcan_cockpit.app import CockpitApp
from orcan_cockpit.picker import WorkspaceList
from orcan_cockpit.pty_terminal import PtyTerminal
from orcan_cockpit.rail import UtilityRail


async def main() -> None:
    app = CockpitApp()
    async with app.run_test(size=(140, 42)) as pilot:
        await pilot.pause(0.4)
        # First-run tips intentionally sit above the cockpit once per profile;
        # dismiss them so the smoke test exercises the actual workspace UI.
        if app.screen.__class__.__name__ == "FirstRunModal":
            await pilot.press("escape")
            await pilot.pause()
        workspaces = app.screen.query_one("#workspace-list-widget", WorkspaceList)
        rows = workspaces.rows
        assert rows, "workspace picker is empty"
        assert any(row["name"] == "dev-ux" for row in rows), rows
        assert app.screen.query_one("#workspace-list", ListView).has_focus
        for widget_id in ("#top-bar", "#workspace-activity", "#hint-strip", "#rail", "#status-bar"):
            assert app.screen.query_one(widget_id), f"missing cockpit widget: {widget_id}"

        await app.select_workspace(next(row for row in rows if row["name"] == "dev-ux"))
        for _ in range(30):
            await pilot.pause(0.1)
            terminals = app.screen.query(PtyTerminal)
            if terminals and terminals.first()._ready:
                break
        terminal = app.screen.query_one("#terminal", PtyTerminal)
        assert terminal._process is not None and terminal._process.poll() is None
        assert terminal._session == "dev-ux"
        assert terminal._screen is not None
        assert terminal._screen.columns > 20 and terminal._screen.lines > 5

        activity = app.screen.query_one("#workspace-activity", WorkspaceActivity)
        rail = app.screen.query_one("#rail", UtilityRail)
        # Git/lazygit was intentionally removed from the rail; it remains
        # available through the `lg` shell alias inside the terminal.
        assert len(rail.query("Button")) == 2
        rail.set_pending_count(3)
        assert str(rail.query_one("#rail-assertions").label) == "🔔 3 Assertions"
        rail_tooltip = str(rail.query_one("#rail-assertions").tooltip)
        assert rail_tooltip and any(
            token in rail_tooltip for token in ("pending", "dirty", "reflect")
        ), rail_tooltip
        assert app.screen.query_one("#top-bar-right").tooltip
        assert app.screen.query_one("#top-bar-identity").tooltip
        assert app.screen.query_one("#activity-pause-btn").tooltip
        assert activity.display
        await pilot.press("f2")
        await pilot.pause()
        assert not activity.display
        await pilot.press("f2")
        await pilot.pause()
        assert activity.display

        # Exercise the real rail event path, not only the helper method.
        await pilot.press("f2")
        await pilot.pause()
        await pilot.click("#rail-assertions")
        await pilot.pause()
        assert activity.display

        # The top-bar wordmark opens About (separate from F1/? shortcuts,
        # checked further down) — its own screen, not a shared modal.
        await pilot.click("#top-bar-identity")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "AboutModal"
        await pilot.press("escape")
        await pilot.pause()

        # Edge-of-panel toggle arrow (replaces the old rail hamburger; a
        # plain Static, not a Button — see app.py's CSS comment on why):
        # F4 and the arrow drive the same state, so both must agree.
        toggle_arrow = app.screen.query_one("#sidebar-toggle", Static)
        assert toggle_arrow._Static__content == "‹"
        app.screen.action_toggle_workspaces()
        await pilot.pause()
        assert not app.screen.query_one("#workspaces").display
        assert toggle_arrow._Static__content == "›"
        app.screen.action_toggle_workspaces()
        await pilot.pause()
        assert app.screen.query_one("#workspaces").display
        assert toggle_arrow._Static__content == "‹"

        await pilot.press("f1")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "ShortcutsModal"
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "MainScreen"

        app.screen._apply_tier("compact")
        await pilot.pause()
        assert app.screen.has_class("tier-compact")
        # Compact tier hides the secondary assertions surface through CSS;
        # the browser visual check owns the computed-visibility assertion.
        app.screen._apply_tier("minimal")
        await pilot.pause()
        assert app.screen.has_class("tier-minimal")
        assert not app.screen.query_one("#workspaces").display
        assert app.screen.query_one("#center").display
        app.screen.action_toggle_workspaces()
        await pilot.pause()
        assert app.screen.query_one("#workspaces").display
        assert not app.screen.query_one("#center").display
        assert toggle_arrow._Static__content == "‹"
        app.screen.action_toggle_workspaces()
        await pilot.pause()
        assert not app.screen.query_one("#workspaces").display
        assert app.screen.query_one("#center").display
        assert toggle_arrow._Static__content == "›"
        # The rail is CSS-hidden at minimal tier; its computed visibility is
        # covered by the browser/a11y checks.
        app.screen._apply_tier("full")
        await pilot.pause()
        assert app.screen.has_class("tier-full")
        assert app.screen.query_one("#workspaces").display

        # Idle workspace-list refresh must not tear down ListItems when
        # nothing changed — that clear()+rebuild was the main cockpit
        # flicker. Two back-to-back refresh_rows() calls with stable data
        # should keep the same widget identities.
        list_view = app.screen.query_one("#workspace-list", ListView)
        before = [id(item) for item in list_view.query(ListItem)]
        assert before, "workspace list has no rows to paint-skip against"
        workspaces.refresh_rows()
        workspaces.refresh_rows()
        after = [id(item) for item in list_view.query(ListItem)]
        assert after == before, "no-op refresh_rows rebuilt ListItems (flicker)"

        # Regression: switching to a second workspace without waiting for
        # the first one's #center-stack teardown to finish used to crash
        # with DuplicateIds on "loading"/"terminal" — remove_children()
        # only *posts* the removal, it doesn't apply it synchronously, so
        # a bare (unawaited) call let the next mount() collide with the
        # not-yet-gone widget (confirmed via a real user crash report and
        # by reproducing it against the pre-fix code). No second configured
        # workspace needed — any row with a different tmux session will do.
        base = next(r for r in rows if r["name"] == "dev-ux")
        row_b = {**base, "session": "dev-ux-regress-b"}
        row_c = {**base, "session": "dev-ux-regress-c"}
        # No pilot.pause() between these two — that's the point: each await
        # must fully settle its own teardown/mount before the next call's
        # mount() can run, or this raises DuplicateIds just like it did for
        # the real user.
        await app.select_workspace(row_b)
        await app.select_workspace(row_c)
        await pilot.pause(1.0)
        assert len(app.screen.query(PtyTerminal)) == 1
        assert app.screen.query_one("#terminal", PtyTerminal)._session == "dev-ux-regress-c"

    print("Cockpit Textual + tmux PTY smoke OK")


asyncio.run(main())
