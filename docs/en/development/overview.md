# Development overview

Guide for people and coding agents who change the **Orcan** repository.

## Local setup

```bash
git clone https://github.com/aKyther/orcan.git
cd orcan
orcan init "$(pwd)"
make validate
make test-host
```

Build and smoke (needs Docker; builds the full image):

```bash
orcan build
make test
```

Docs:

```bash
make docs-check
make docs-serve
```

Manual UX testing runs in a separate development container:

```bash
make dev-start
# edit UX, then:
make dev-restart
make dev-doctor
make dev-smoke
make dev-stop
```

## Repository map

| Path | Role |
| --- | --- |
| `bin/orcan`, `cli/` | Public CLI |
| `install.sh` | curl\|bash installer |
| `Dockerfile` | Image build |
| `docker-compose*.yml` | Runtime overlays |
| `docker/rootfs/` | Files copied into the image |
| `cockpit/` | Cockpit TUI (agent-launcher) |
| `scripts/repository/` | Host-only helpers (config, release, validate) |
| `scripts/dev/` | Checkout-local previews; discover via `make dev-*` |
| `Makefile` | Maintainer targets |
| `orcan.config.example.json` | Config template |
| `docs/` | MkDocs site |
| `tests/` | Host unit tests + smoke + path-parity + `dev-test` |
| `AGENTS.md` / `CLAUDE.md` | AI orientation for **this** repo (keep identical) |
| `.cursor/rules/` | Cursor rules for **this** repo |

## Separation rules

- Repo rules (`.cursor/`) ≠ image defaults (`docker/rootfs/opt/cursor-defaults/`)
- Container scripts live under `docker/rootfs/usr/local/bin/`
- Host product helpers live under `scripts/repository/`
- Checkout-only UX / tmux previews live under `scripts/dev/` (never install into `PATH` as `orcan`)
- User config is JSON only (`orcan.config.json`) — no PyYAML host stack

## Coding style

- Small, focused diffs
- Prefer Makefile targets that already exist
- B1–B2 English in user docs
- Follow [docs/STYLE_GUIDE.md](https://github.com/aKyther/orcan/blob/main/docs/STYLE_GUIDE.md)
- Do not document commands that do not exist
- Do not invent features in docs

## Definition of done

For a behaviour change, update as needed:

1. Code / scripts / Compose / Dockerfile
2. Tests (`make validate`, and `make test` when Docker behaviour changes)
3. Docs under `docs/` (and short README pointers)
4. `AGENTS.md` / `.cursor/rules` if agent ritual or boundaries change
5. `CHANGELOG.md` for user-visible changes
6. `cockpit/pyproject.toml` version only when cutting a release

## Where to read next

- [Testing](testing.md)
- [Release process](release.md)
- [AI project context](../ai/project-context.md)
- [Architecture](../architecture.md)
