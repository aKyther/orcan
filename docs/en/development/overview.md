# Development overview

Guide for people and coding agents who change the **Orcan** repository.

## Local setup

```bash
git clone https://github.com/aKyther/orcan.git
cd orcan
make setup PROJECT_DIR="$(pwd)"
make validate
make test-host
```

Build and smoke (needs Docker; builds the full image):

```bash
make build
make test
```

Docs:

```bash
make docs-check
make docs-serve
```

## Repository map

| Path | Role |
| --- | --- |
| `Dockerfile` | Image build |
| `docker-compose*.yml` | Runtime overlays |
| `docker/rootfs/` | Files copied into the image |
| `scripts/repository/` | Host-only helpers |
| `Makefile` | Thin host UI |
| `orcan.config.example.json` | Config template |
| `docs/` | MkDocs site |
| `tests/` | Host unit tests + smoke + path-parity |
| `AGENTS.md` | AI orientation for **this** repo |
| `.cursor/rules/` | Cursor rules for **this** repo |

## Separation rules

- Repo rules (`.cursor/`) ≠ image defaults (`docker/rootfs/opt/cursor-defaults/`)
- Container scripts live under `docker/rootfs/usr/local/bin/`
- Host scripts live under `scripts/repository/`
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
6. `VERSION` only when cutting a release

## Where to read next

- [Testing](testing.md)
- [Release process](release.md)
- [AI project context](../ai/project-context.md)
- [Architecture](../concepts/architecture.md)
