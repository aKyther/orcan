# Cursor and Claude defaults

## Two layers

| Layer | Path | Role |
| --- | --- | --- |
| Image defaults | `/opt/cursor-defaults` (from `docker/rootfs/opt/cursor-defaults/`) | Seeded into `~/.cursor` at startup (**missing-only**) |
| Mounted projects | Your git repos | Optional seeds via `make init-project` / `init-project-all` |

Orcan does **not** overwrite existing files in `~/.cursor` on every start.

## CLI permissions

Active Cursor CLI permissions file: `cli-config.json` (seeded from defaults).

## Workspace vs project

- **Workspace** context pack: written under `/home/developer/workspaces/<name>/` by `init-workspace`
- **Project** files: only when you run init-project targets

See [Architecture](../architecture.md).

## Status line

Optional AI usage in tmux status: `init-ai-statusline` + `orcan-ai-statusline` (hooks for Claude/Cursor). Thin by design.

## This repository

When you develop **Orcan itself**, also read root `AGENTS.md` and `.cursor/rules/` — those are for the Orcan repo, not for every mounted customer project.

## See also

- [Architecture](../architecture.md)
- [Core Ideas](../ideas/core-ideas.md)
