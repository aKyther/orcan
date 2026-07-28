# Orcan — agent context for this repository

Official product name: **Orcan** (technical ids: `orcan`, `ORCAN_*`).

This file orients coding agents working **on the Orcan repo itself**.
Cursor also applies `.cursor/rules/agents.mdc` (always on).
Longer map: `docs/en/ai/project-context.md` (Polish: `docs/pl/ai/project-context.md`).

## What Orcan is

**Work-context orchestrator** for Cursor CLI (`agent`) and Claude Code (`claude`) in Docker:

- workspaces (named sets of projects) + path-parity mounts
- ignore / instruction seeds (context pack)
- browser terminal (ttyd) → launcher → tmux → **zsh**
- Image: `orcan:latest` / `orcan:<VERSION>` (both agents). Single-agent local: `orcan build --claude` → `orcan:<VERSION>-claude`

User-facing story: `docs/en/why-orcan.md`, `docs/en/ideas/core-ideas.md`, `docs/en/ideas/mental-model.md`.

**Not** a model manager — do not add model-selection or provider abstractions.
**Not** an image registry product — users install the CLI (`install.sh`) and run `orcan build` (pull or local build; publish is manual via `orcan publish`).

## Ritual (host)

```bash
orcan context wizard        # or edit ORCAN_HOME/orcan.config.json / orcan context add
# worktrees: orcan context worktrees | add --from-worktree | worktree create
orcan sync                  # apply config → .env, .orcan/*, mounts
orcan build                 # once / after Dockerfile|rootfs changes
orcan up                    # daily; does NOT run orcan sync
```

After config edits with a running container: `orcan sync && orcan down && orcan up`.

Release (maintainers): `make bump-patch` → update `CHANGELOG.md` → commit → `make release`.

## Config

- **Only** `orcan.config.json` (stdlib JSON — no PyYAML / host venv for config).
- Default location: `~/.config/orcan/home/orcan.config.json` (`ORCAN_HOME`).
- Template: `orcan.config.example.json`.
- Docker Compose YAML and `mkdocs.yml` stay YAML — that is fine.
- Do **not** reintroduce YAML user profiles or `host-deps` / `requirements-host.txt`.

## Runtime stack (inside container)

```text
ttyd → cursor-launcher → tmux (default-shell zsh)
                      → Starship + zsh plugins
                      → aliases in /etc/orcan/shell/aliases.sh
```

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
