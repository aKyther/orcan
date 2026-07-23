# AI project context

Single orientation page for coding agents working **on the Orcan repository**.

Also read root [`AGENTS.md`](https://github.com/aKyther/orcan/blob/main/AGENTS.md) and `.cursor/rules/agents.mdc` (always on in Cursor). Do not invent a second conflicting ritual.

## Product identity

- Official name: **Orcan** (display). Technical ids use lowercase `orcan` (`orcan:latest`, `ORCAN_DATA`, `orcan.config.json`).
- Do **not** reintroduce old product names: Sint, Orkan, cind (except migration notes / cleanup code).
- **Cursor** means the Cursor editor / Cursor CLI — not the product name.
- Orcan is a **context orchestrator**, not a model manager.

## Goals

- Workspaces + path-parity mounts
- Context pack (ignores, AGENTS/CLAUDE)
- Browser terminal: ttyd → launcher → tmux → zsh
- Image variants: full (Claude+Cursor) and Claude-only

## Non-goals

- Model selection UI / provider abstraction
- Auto-routing between `agent` and `claude`
- Publishing images from CI
- Auto-modifying mounted git repos on every container start

## Ritual (host)

```bash
make config-wizard          # or edit orcan.config.json
make env
make build                  # when image inputs change
make terminal-docker        # daily; does NOT run make env
```

After config edits with a running container: `make env && make down && make terminal-docker`.

## Where to change what

| Change | Place |
| --- | --- |
| Host UX / targets | `Makefile`, `scripts/repository/` |
| Container runtime | `docker/rootfs/usr/local/bin/` |
| Image packages | `Dockerfile` |
| Global agent defaults in image | `docker/rootfs/opt/cursor-defaults/` |
| Rules for developing Orcan | `.cursor/rules/`, `AGENTS.md` |
| User docs | `docs/` + short `README.md` |

## Documentation map

| Topic | Doc |
| --- | --- |
| Architecture | [concepts/architecture.md](../concepts/architecture.md) |
| Config schema | [reference/configuration.md](../reference/configuration.md) |
| Make targets | [reference/makefile.md](../reference/makefile.md) |
| Security | [reference/security.md](../reference/security.md) |
| Release | [development/release.md](../development/release.md) |
| Tests | [development/testing.md](../development/testing.md) |

## Definition of done

Code change is incomplete without updating the matching docs when behaviour or interface changes. Run `make validate` and `make docs-check` before claiming done.
