"""orcan-cockpit: the Textual app behind `agent-launcher`.

Keeps tmux as the real session/window/pane engine — this package only owns
the outer pty (embedding a live `tmux attach` as a child, see
`pty_terminal.py`) and renders a workspace picker + side panel around it.

Installed into its own isolated venv at build time (`uv sync`, see
../pyproject.toml and the repo Dockerfile) — never the container's system
Python. Its one dependency outside this package, `orcan.context_inbox`
(stdlib-only), stays vendored under /usr/local/lib because
`orcan-context-review` — a separate, stdlib-only script — needs it too; see
cli.py for how that path is added to sys.path at the one entry point.
"""
