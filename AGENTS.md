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
- Image variants: `orcan:latest` (Claude+Cursor), `orcan:claude` (Claude only)

User-facing story: `docs/en/why-orcan.md`, `docs/en/ideas/core-ideas.md`, `docs/en/ideas/mental-model.md`.

**Not** a model manager — do not add model-selection or provider abstractions.
**Not** an image registry product — users `git clone` + `make build`.

## Ritual (host)

```bash
make config-wizard          # or edit orcan.config.json / config-scaffold
make env                    # apply config → .env, .orcan/*, mounts
make build                  # once / after Dockerfile|rootfs changes
make terminal-docker        # daily; does NOT run make env
```

After config edits with a running container: `make env && make down && make terminal-docker`.

Release: `make bump-patch` → update `CHANGELOG.md` → commit → `make release` (GitHub Release only).

## Config

- **Only** `orcan.config.json` (stdlib JSON — no PyYAML / host venv for config).
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
| `Dockerfile` | Image build |
| `docker-compose*.yml` | Runtime |
| `docker/rootfs/` | Image filesystem |
| `scripts/repository/` | Host helpers |
| `docs/` | MkDocs EN+PL (`docs/en/`, `docs/pl/`) |
| `README.md` | Short entry only |
| `.cursor/rules/` | Rules for developing Orcan |
| `docker/rootfs/opt/cursor-defaults/` | Defaults seeded into user containers |

## Validation before done

- `make validate`
- `make test-host`
- `make docs-check`
- `make test` when Docker behaviour changes and Docker is available

Report what ran, what did not, and environment limits.
