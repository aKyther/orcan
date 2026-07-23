# orcan — agent context for this repository

This file orients coding agents working **on the orcan repo itself**.
Cursor also applies `.cursor/rules/agents.mdc` (always on).

## What orcan is

**Context orchestrator** for Cursor CLI (`agent`) and Claude Code (`claude`) in Docker:

- workspaces + path-parity mounts
- ignore / instruction seeds
- browser terminal (ttyd) → launcher → tmux → **zsh**
- Image variants: `orcan:latest` (Claude+Cursor), `orcan:claude` (Claude only)

**Not** a model manager — do not add model-selection or provider abstractions.

## Ritual (host)

```bash
make config-wizard          # or edit orcan.config.json / config-scaffold
make env                    # apply config → .env, .orcan/*, mounts
make build                  # once / after Dockerfile|rootfs changes
make terminal-docker        # daily; does NOT run make env
```

After config edits with a running container: `make env && make down && make terminal-docker`.

## Config

- **Only** `orcan.config.json` (stdlib JSON — no PyYAML / host venv for config).
- Template: `orcan.config.example.json`.
- Docker Compose YAML (`docker-compose*.yml`, `mkdocs.yml`, generated `.orcan/*.yml`) stays YAML — that is fine.
- Do **not** reintroduce YAML user profiles or `host-deps` / `requirements-host.txt`.

## Runtime stack (inside container)

```text
ttyd → cursor-launcher → tmux (default-shell zsh)
                      → Starship + zsh plugins (autosuggestions, syntax, fzf)
                      → aliases in /etc/orcan/shell/aliases.sh
```

- tmux config: `docker/rootfs/etc/tmux/` (2-row status; right-click menus unbound).
- Shell skel: `docker/rootfs/etc/skel/.zshrc` + `.zshrc.d/`.
- Git defaults seed: `/opt/orcan/gitconfig` → `~/.gitconfig` (missing-only).

## Layout (edit here)

| Area | Path |
| --- | --- |
| Image filesystem | `docker/rootfs/` |
| Host Make / scripts | `Makefile`, `scripts/repository/` |
| Docs | `README.md`, `docs/` |
| Repo Cursor rules | `.cursor/rules/` |
| Image Cursor defaults | `docker/rootfs/opt/cursor-defaults/` |

## Do / don’t

- Work only under this repo (`PROJECT_DIR` when developing orcan).
- After Make/Compose/rootfs interface changes: update docs + `make validate`.
- Do not modify `.env` unless asked; do not claim build success without `make build` / `make rebuild`.

Details: `docs/development.md`, `docs/architecture/context.md`, `docs/config.md`.
