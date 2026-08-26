"""Command palette (Ctrl+P, Textual's built-in) — fuzzy workspace switch.
Fixed actions (toggle panel, shortcuts, context review) are registered
via App.get_system_commands in app.py instead, since they don't need fuzzy
search and some are conditional on there being an attached session."""

from __future__ import annotations

from functools import partial

from textual.command import Hit, Hits, Provider

from orcan_cockpit.picker import list_workspace_rows


class WorkspaceCommands(Provider):
    """Fuzzy "switch to workspace <name>" — reuses the same row lookup and
    attach path WorkspaceList itself uses, no duplicated logic."""

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        try:
            rows = list_workspace_rows()
        except (OSError, ValueError):
            return
        for row in rows:
            score = matcher.match(row["name"])
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(row["name"]),
                    partial(self.app.select_workspace, row),  # type: ignore[attr-defined]
                    help=f"session {row['session']}",
                )
