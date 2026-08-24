# Orcan — agent context for this repository

Official product name: **Orcan** (technical ids: `orcan`, `ORCAN_*`).

This file orients coding agents working **on the Orcan repo itself**.
Cursor also applies `.cursor/rules/agents.mdc` (always on).
Longer map: `docs/en/ai/project-context.md` (Polish: `docs/pl/ai/project-context.md`).

## What Orcan is

**Work-context orchestrator** for Cursor CLI (`agent`), Claude Code (`claude`), and Codex CLI (`codex`) in Docker:

- workspaces (named sets of projects) + path-parity mounts
- ignore / instruction seeds (context pack)
- local container access by default (`orcan enter`); optional browser terminal (`orcan up --with-ttyd` → ttyd → launcher → tmux → **zsh**)
- Image: `orcan:latest` / `orcan:<VERSION>` (all agents). Single-agent local: `orcan build --claude` → `orcan:<VERSION>-claude` (also `--cursor`, `--codex`)

User-facing story: `docs/en/why-orcan.md`, `docs/en/ideas/core-ideas.md`, `docs/en/ideas/mental-model.md`.

**Not** a model manager — do not add model-selection or provider abstractions.
**Not** an image registry product — users install the CLI (`install.sh`) and run `orcan build` (pull or local build; publish is manual via `orcan publish`).

## Ritual (host)

```bash
orcan init                  # no PATH -> interactive wizard; or: context add / context tui
# many repos in one folder: orcan context tui   # multi-select + optional shared-branch worktrees
# worktrees: orcan context worktrees | add --from-worktree | worktree create
orcan sync                  # apply config → .env, mounts/* (Compose overlays), workspaces/*
orcan build                 # once / after Dockerfile|rootfs changes
orcan up                    # daily; local-only by default (orcan enter); --with-ttyd for browser
orcan migrate [--yes]       # optional: move projects under managed root (dry-run without --yes)
```

After config edits with a running container: `orcan sync` (live reconcile when possible — no recreate needed for projects under `ORCAN_PROJECTS_ROOT`). When overlays/flags change: `orcan down && orcan up`.

Release (maintainers): `make bump-patch` → update `CHANGELOG.md` → commit → `make release`.

## Runtime modification

Adding/removing a project or workspace does not need a container recreate
when it lives under one of the two stable mounts (`$ORCAN_PROJECTS_ROOT`,
`$ORCAN_HOME/workspaces/`) — see [Mental Model](docs/en/ideas/mental-model.md).

- Mechanism: `orcan.reconcile.apply_workspaces()` — same function at
  container boot (`init-workspace`) and on demand (`orcan-runtime-reconcile`,
  invoked by `orcan sync` via `docker exec` into a running container)
- Tmux: `orcan-tmux-reconcile-sessions` — creates missing sessions; reports
  (never kills by default) orphaned ones. `orcan sync --prune-orphans` opts in
- Read-only diff (desired vs. actual): `orcan-runtime-status`
- User docs: `docs/en/ideas/runtime-reconcile.md` (+ PL)

## Config

- **Only** `orcan.config.json` (stdlib JSON — no PyYAML / host venv for config).
- Default location: `~/.config/orcan/orcan.config.json` (`ORCAN_HOME`).
- Template: `orcan.config.example.json`.
- Docker Compose YAML and `mkdocs.yml` stay YAML — that is fine.
- Do **not** reintroduce YAML user profiles or `host-deps` / `requirements-host.txt`.

## Runtime stack (inside container)

Default path (local `orcan up` — no published ttyd port):

```text
orcan enter → agent-launcher → tmux 3.6a (default-shell zsh)
                            → Starship + zsh plugins + fzf
                            → aliases in /etc/orcan/shell/aliases.sh
                            → lazygit (navy/cyan) + delta
```

Optional browser path (`orcan up --with-ttyd` on the host):

```text
ttyd → agent-launcher → tmux … (same session stack as above)
```

Terminal look (palette, file map, agent checklist):
`docs/en/guides/terminal-ui.md` (+ PL). Cursor rule: `.cursor/rules/terminal-ui.mdc`.

## Agent handoff (in-container)

Filesystem task queue under `<workspace>/.orcan/tasks/` — structured manifests, not full chat transcripts.

- CLI: `orcan-inbox` (`propose`, `approve`, `claim`, `complete`, `list`, `watch`)
- Library: `docker/rootfs/usr/local/lib/orcan/agent_inbox.py`, `agent_executor.py`
- User docs: `docs/en/ideas/agent-inbox.md` (+ PL)
- Policies: `draft` (proposals only), `approve` (human gate), `auto` (straight to inbox)

Separate from Context Assertions (`.orcan/context-inbox/` → `CONTEXT-ASSERTIONS.md`).

## File map (this repo)

| Path | Role |
| --- | --- |
| `bin/orcan`, `cli/` | Public CLI |
| `install.sh` | curl\|bash installer |
| `Dockerfile` | Image build |
| `docker-compose*.yml` | Runtime |
| `docker/rootfs/` | Image filesystem |
| `scripts/repository/` | Host helpers |
| `Makefile` | Maintainer targets only |
| `docs/` | MkDocs EN+PL (`docs/en/`, `docs/pl/`) |
| `README.md` | Short entry only |
| `.cursor/rules/` | Rules for developing Orcan |
| `docker/rootfs/opt/cursor-defaults/` | Defaults seeded into user containers |

## Validation before done

- `make validate`
- `make test-host`
- `make docs-check`
- `./bin/orcan help` / `./bin/orcan doctor`
- `make test` when Docker behaviour changes and Docker is available

Report what ran, what did not, and environment limits.

## Commits

If you create a git commit, do not add a `Co-Authored-By` (or similar
AI-attribution) trailer. The human is the sole author of record.
