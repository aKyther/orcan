"""orcan-cockpit: the Textual app behind `agent-launcher`.

Keeps tmux as the real session/window/pane engine — this package only owns
the outer pty (embedding a live `tmux attach` as a child, see
`pty_terminal.py`) and renders a workspace picker around it.

Installed into its own isolated venv at build time (`uv sync`, see
../pyproject.toml and the repo Dockerfile) — never the container's system
Python.
"""
