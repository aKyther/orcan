# Orcan

**Work-context orchestrator** for coding agents. Run **Cursor CLI** (`agent`) and **Claude Code** (`claude`) in Docker with path-parity mounts, workspaces (named sets of projects), and a browser tmux terminal.

Models are out of scope — each CLI picks its own.

[Documentation (EN)](https://akyther.github.io/orcan/latest/) · [Dokumentacja (PL)](https://akyther.github.io/orcan/latest/pl/) · [Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md)

## Status

Version **0.4.2**. Distributed as a **CLI** (`orcan`). `orcan build` pulls the image for this version when available, otherwise builds locally. Publishing images is **manual** (`orcan publish`) and not part of build. CI validates and publishes docs; it does **not** publish container images.

## Features

- Workspaces (one tmux session per workspace)
- Path parity (same absolute paths host ↔ container)
- Images: `orcan:latest` / `orcan:<VERSION>` (both agents); optional local `orcan:<VERSION>-claude` / `-cursor`
- Browser terminal (ttyd → launcher → tmux → zsh)
- Host data under `~/.config/orcan` (`ORCAN_DATA`)
- JSON config + wizard (`orcan.config.json`)
- Docs in **English** and **Polish** (language switcher on the site)

## Requirements

| Tool | Role |
| --- | --- |
| Bash | `orcan` CLI dispatcher |
| Python 3 | Host config: `sync`, `init` (incl. wizard), `context` (show / add / hook) — stdlib only, no pip |
| Git | Install clone + your projects |
| Docker (Compose v2) | Image + browser terminal |

`orcan` itself is Bash; several commands call small Python helpers on the host. `orcan doctor` checks all of the above.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/aKyther/orcan/main/install.sh | bash
```

Adds `orcan` to `~/.local/bin` and appends that directory to your shell rc (`~/.zshrc` / `~/.bashrc`) if needed.

## Quickstart

```bash
orcan doctor
orcan init /absolute/path/to/your/repo   # or just `orcan init` for the interactive wizard
orcan build
orcan up
```

Open `http://localhost:7681`. After any config edit: `orcan init && orcan down && orcan up` (`up` does not sync).

### Useful commands

| Command | Role |
| --- | --- |
| `orcan sync` | Apply `orcan.config.json` → `.env` + `mounts/*` |
| `orcan init` | Interactive config wizard (no PATH: create or edit) |
| `orcan up` / `orcan up --with-docker` / `orcan up --with-git` / `orcan up --with-network NAME` / `orcan down` | Start (optional DinD / host SSH / join a Docker network) / stop browser terminal |
| `orcan build [--claude\|--cursor]` | Both → `latest`+`<VERSION>`; flags → `<VERSION>-claude\|cursor` |
| `orcan publish` | Manual image push (maintainers) |
| `orcan update` | Newest release tag `vX.Y.Z` (`--main` for bleeding edge) |
| `orcan uninstall` | Remove CLI (`--purge-data` also deletes logins/caches) |

Config lives in `~/.config/orcan/` by default (install clone: `~/.local/share/orcan`).

## Documentation

| Topic | Link |
| --- | --- |
| Full docs (EN) | https://akyther.github.io/orcan/latest/ |
| Full docs (PL) | https://akyther.github.io/orcan/latest/pl/ |
| Why Orcan? | [docs/en/why-orcan.md](docs/en/why-orcan.md) |
| Core Ideas | [docs/en/ideas/core-ideas.md](docs/en/ideas/core-ideas.md) |
| Mental Model | [docs/en/ideas/mental-model.md](docs/en/ideas/mental-model.md) |
| Context Assertions | [docs/en/ideas/context-assertions.md](docs/en/ideas/context-assertions.md) |
| Quickstart (source) | [docs/en/getting-started/quickstart.md](docs/en/getting-started/quickstart.md) |
| CLI reference | [docs/en/reference/cli.md](docs/en/reference/cli.md) |
| Development | [docs/en/development/overview.md](docs/en/development/overview.md) |
| AI / agents | [AGENTS.md](AGENTS.md), [docs/en/ai/project-context.md](docs/en/ai/project-context.md) |

```bash
make docs-serve   # maintainers — MkDocs from a git checkout
```

## License

MIT — see [LICENSE](LICENSE).
