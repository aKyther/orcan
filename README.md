# Orcan

**Work-context orchestrator** for coding agents. Run **Cursor CLI** (`agent`) and **Claude Code** (`claude`) in Docker with path-parity mounts, workspaces (named sets of projects), and a browser tmux terminal.

Models are out of scope — each CLI picks its own.

[Documentation (EN)](https://akyther.github.io/orcan/latest/) · [Dokumentacja (PL)](https://akyther.github.io/orcan/latest/pl/) · [Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md)

## Status

Version **0.2.0**. Distributed as a **CLI** (`orcan`). `orcan build` pulls the image for this version when available, otherwise builds locally. Publishing images is **manual** (`orcan publish`) and not part of build. CI validates and publishes docs; it does **not** publish container images.

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
| Python 3 | Host config: `sync`, `init`, `context` (wizard / show / add) — stdlib only, no pip |
| Git | Install clone + your projects |
| Docker (Compose v2) | Image + browser terminal |

`orcan` itself is Bash; several commands call small Python helpers on the host. `orcan doctor` checks all of the above.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/aKyther/orcan/main/install.sh | bash
```

Adds `orcan` to `~/.local/bin` (ensure that directory is on your `PATH`).

## Quickstart

```bash
orcan doctor
orcan init /absolute/path/to/your/repo
orcan build
orcan up
```

Open `http://localhost:7681`. After any config edit: `orcan sync && orcan down && orcan up` (`up` does not run `sync`).

### Useful commands

| Command | Role |
| --- | --- |
| `orcan sync` | Apply `orcan.config.json` → `.env` + `.orcan/*` |
| `orcan context wizard` | Interactive config |
| `orcan up` / `orcan up --with-docker` / `orcan down` | Start (optional DinD) / stop browser terminal |
| `orcan build [--claude\|--cursor]` | Both → `latest`+`<VERSION>`; flags → `<VERSION>-claude\|cursor` |
| `orcan publish` | Manual image push (maintainers) |
| `orcan update` | Update the CLI install from Git |
| `orcan uninstall` | Remove CLI (`--purge-data` also deletes logins/caches) |

Config lives in `~/.config/orcan/home/` by default (install clone: `~/.local/share/orcan`).

## Documentation

| Topic | Link |
| --- | --- |
| Full docs (EN) | https://akyther.github.io/orcan/latest/ |
| Full docs (PL) | https://akyther.github.io/orcan/latest/pl/ |
| Why Orcan? | [docs/en/why-orcan.md](docs/en/why-orcan.md) |
| Core Ideas | [docs/en/ideas/core-ideas.md](docs/en/ideas/core-ideas.md) |
| Mental Model | [docs/en/ideas/mental-model.md](docs/en/ideas/mental-model.md) |
| Quickstart (source) | [docs/en/getting-started/quickstart.md](docs/en/getting-started/quickstart.md) |
| CLI reference | [docs/en/reference/cli.md](docs/en/reference/cli.md) |
| Development | [docs/en/development/overview.md](docs/en/development/overview.md) |
| AI / agents | [AGENTS.md](AGENTS.md), [docs/en/ai/project-context.md](docs/en/ai/project-context.md) |

```bash
make docs-serve   # maintainers — MkDocs from a git checkout
```

## License

MIT — see [LICENSE](LICENSE).
