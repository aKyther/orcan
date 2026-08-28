# Container home map (`~/orcan-map`)

This directory is a **navigation map** of the sandbox. Symlinks only —
tools still use their normal homes (`~/.cursor`, `~/.claude`, …).

| Path | Points to | Role |
| --- | --- | --- |
| `agents/cursor` | `~/.cursor` | Cursor CLI auth / state |
| `agents/cursor-app` | `~/.config/cursor` | Cursor app config |
| `agents/claude` | `~/.claude` | Claude Code auth / settings |
| `agents/codex` | `~/.codex` | Codex CLI auth / state |
| `cache` | `~/.cache` | All tool caches (npm, pnpm, cargo, go, uv, …) |
| `history` | `~/.local/share/orcan/history` | Shell history — one file per workspace in tmux (`history/workspaces/<name>/`) |
| `dotfiles` | `~/.config/orcan/dotfiles` | Your shell/tmux/vim overlays |
| `workspaces` | `~/workspaces` | Workspace navigation roots |

Host side (unchanged root): `$ORCAN_DATA` (default `~/.config/orcan`) binds
`cache/` → `~/.cache`, `history/` → history dir, agent dirs → agent homes.

Work happens under `~/workspaces/<name>/` (and path-parity abs paths).
Host config (`orcan.config.json`, `.env`, `mounts/`) is **not** mounted here.
