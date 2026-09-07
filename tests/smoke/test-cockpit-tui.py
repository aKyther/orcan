#!/usr/bin/env python3
"""Exercise the real Textual cockpit and its embedded tmux PTY."""

import asyncio
import subprocess
from unittest.mock import patch

from textual.widgets import Button, ListItem, ListView, Static

from orcan_cockpit.app import CockpitApp, format_placeholder_text
from orcan_cockpit.picker import WorkspaceList
from orcan_cockpit.pty_terminal import PtyTerminal
from orcan_cockpit.rail import UtilityRail


async def main() -> None:
    assert "No workspaces yet" in format_placeholder_text(0)
    assert "orcan init" in format_placeholder_text(0)
    assert "1 workspace available" in format_placeholder_text(1)
    assert "2 workspaces available" in format_placeholder_text(2)
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
        for widget_id in ("#top-bar", "#rail", "#status-bar", "#workspace-trigger"):
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
        assert app.screen.query_one("#center-stack").has_class("focused")
        # Selecting closes the combobox-like overlay at every viewport size.
        # The terminal keeps the same dimensions whether it is open or not.
        assert not app.screen.query_one("#workspaces").display

        rail = app.screen.query_one("#rail", UtilityRail)
        assert len(rail.query("Button")) == 2
        assert str(rail.query_one("#rail-shortcuts").label) == "? Help"
        assert str(rail.query_one("#rail-exit").label) == "Exit"
        assert app.screen.query_one("#top-bar-right").tooltip
        assert app.screen.query_one("#top-bar-identity").tooltip

        # The top-bar wordmark opens About (separate from F1/? shortcuts,
        # checked further down) — its own screen, not a shared modal.
        await pilot.click("#top-bar-identity")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "AboutModal"
        # Browser/ttyd may reserve Escape, so About must also expose a
        # pointer-safe way back to the cockpit.
        await pilot.click("#about-close")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "MainScreen"

        # The current-workspace pill opens one overlay picker at every tier;
        # F4 shares the state and no longer changes the terminal's geometry.
        workspace_trigger = app.screen.query_one("#workspace-trigger", Static)
        assert "dev-ux" in str(workspace_trigger._Static__content)
        terminal_size = terminal.size
        app.screen.action_toggle_workspaces()
        await pilot.pause()
        assert app.screen.query_one("#workspaces").display
        assert terminal.size == terminal_size
        assert app.screen.query_one("#workspace-list-widget").has_class("focused")
        assert not app.screen.query_one("#center-stack").has_class("focused")
        # The modern picker is decision-first: metadata stays out of the way
        # until explicitly requested for the highlighted workspace.
        assert not workspaces._expanded
        assert not app.screen.query_one("#workspace-details").display
        assert not app.screen.query_one("#workspace-glance").display
        await pilot.press("i")
        await pilot.pause()
        assert workspaces._expanded
        assert app.screen.query_one("#workspace-details").display
        assert app.screen.query_one("#workspace-glance").display
        # Confirming the already-attached row closes the picker too; it must
        # not restart the PTY merely because Enter was used as confirmation.
        process = terminal._process
        await pilot.press("enter")
        await pilot.pause()
        assert not app.screen.query_one("#workspaces").display
        assert terminal.size == terminal_size
        assert terminal._process is process
        assert terminal.has_focus
        assert app.screen.query_one("#center-stack").has_class("focused")

        await pilot.press("f1")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "ShortcutsModal"
        assert app.screen.query_one("#shortcuts-close")
        await pilot.click("#shortcuts-close")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "MainScreen"

        await pilot.press("f5")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "PeekModal"
        assert app.screen.query_one("#peek-close")
        await pilot.click("#peek-close")
        await pilot.pause()
        assert app.screen.__class__.__name__ == "MainScreen"

        app.screen._apply_tier("compact")
        await pilot.pause()
        assert app.screen.has_class("tier-compact")
        assert not app.screen.query_one("#workspaces").display
        app.screen._apply_tier("minimal")
        await pilot.pause()
        assert app.screen.has_class("tier-minimal")
        # After attaching a workspace, the narrow layout is terminal-first:
        # only the workspace pill remains, while the status chrome returns
        # its rows to tmux. It must remain that way while F4 is open so the
        # terminal never jumps underneath the overlay.
        assert app.screen.has_class("terminal-first")
        assert not app.screen.query_one("#top-bar-identity").display
        assert not app.screen.query_one("#status-bar").display
        assert app.screen.query_one("#workspace-trigger").display
        terminal_size = terminal.size
        assert not app.screen.query_one("#workspaces").display
        assert app.screen.query_one("#center").display
        app.screen.action_toggle_workspaces()
        await pilot.pause()
        assert app.screen.query_one("#workspaces").display
        assert app.screen.query_one("#center").display
        assert app.screen.has_class("terminal-first")
        assert terminal.size == terminal_size
        app.screen.action_toggle_workspaces()
        await pilot.pause()
        assert not app.screen.query_one("#workspaces").display
        assert app.screen.query_one("#center").display
        # The rail is CSS-hidden at minimal tier; its computed visibility is
        # covered by the browser/a11y checks.
        app.screen._apply_tier("full")
        await pilot.pause()
        assert app.screen.has_class("tier-full")
        assert not app.screen.query_one("#workspaces").display

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
        # Return to a configured workspace before testing reconnect. The
        # synthetic regression sessions above deliberately are not picker
        # rows, and stale/non-configured state must be ignored.
        await app.select_workspace(base)
        await pilot.pause(1.0)
        assert app.screen.query_one("#terminal", PtyTerminal)._session == "dev-ux"

        # An unsuccessful bootstrap must not leave the old workspace identity
        # in the chrome or trap the user on an error screen. The concise error
        # itself is pointer-safe recovery; F4 remains an equivalent shortcut.
        failed = {**base, "session": "dev-ux-bootstrap-failure"}
        with patch(
            "orcan_cockpit.app.bootstrap_workspace",
            return_value=subprocess.CompletedProcess([], 1),
        ):
            await app.select_workspace(failed)
        await pilot.pause()
        error = app.screen.query_one("#error", Static)
        assert "Could not open" in str(error._Static__content)
        assert "(no workspace)" in str(
            app.screen.query_one("#status-body", Static)._Static__content
        )
        await pilot.click("#error")
        await pilot.pause()
        assert app.screen.query_one("#workspaces").display
        assert app.screen.query_one("#workspace-list", ListView).has_focus
        await app.select_workspace(base)
        await pilot.pause(1.0)
        assert app.screen.query_one("#terminal", PtyTerminal)._session == "dev-ux"

    # A ttyd reconnect launches a new cockpit process in the same container.
    # It should consume the /tmp hint written above and attach without making
    # the user pick the workspace again; tmux owns the retained window/pane.
    reconnected = CockpitApp()
    async with reconnected.run_test(size=(140, 42)) as pilot:
        for _ in range(30):
            await pilot.pause(0.1)
            terminals = reconnected.screen.query(PtyTerminal)
            if terminals and terminals.first()._ready:
                break
        terminal = reconnected.screen.query_one("#terminal", PtyTerminal)
        assert terminal._session == "dev-ux"
        assert terminal._process is not None and terminal._process.poll() is None

    print("Cockpit Textual + tmux PTY smoke OK")


asyncio.run(main())
