# Orcan

**Work-context orchestrator** for coding agents. Run **Cursor CLI** (`agent`) and **Claude Code** (`claude`) in Docker with path-parity mounts, workspaces (named sets of projects), and a browser tmux terminal.

Models are out of scope — each CLI picks its own.

[Documentation (EN)](https://akyther.github.io/orcan/latest/) · [Dokumentacja (PL)](https://akyther.github.io/orcan/latest/pl/) · [Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md)

## Status

Version **0.1.1**. Distributed as **git clone + Makefile**. Build images locally (`make build`). CI validates and publishes docs; it does **not** publish container images.

## Features

- Workspaces (one tmux session per workspace)
- Path parity (same absolute paths host ↔ container)
- Full image (`orcan:latest`) or Claude-only (`orcan:claude`)
- Browser terminal (ttyd → launcher → tmux → zsh)
- Host data under `~/.config/orcan` (`ORCAN_DATA`)
- JSON config + wizard (`orcan.config.json`)
- Docs in **English** and **Polish** (language switcher on the site)

## Requirements

Docker (Compose v2), Make, Git, Python 3.

## Quickstart

```bash
git clone https://github.com/aKyther/orcan.git
cd orcan
make setup PROJECT_DIR=/absolute/path/to/your/repo   # includes make env once
make env                                             # materialise .env + .orcan/* for Compose
make build
make terminal-docker
```

Open `http://localhost:7681`. After any `orcan.config.json` edit: `make env && make down && make terminal-docker` (`terminal*` does not run `make env`).

## Documentation

| Topic | Link |
| --- | --- |
| Full docs (EN) | https://akyther.github.io/orcan/latest/ |
| Full docs (PL) | https://akyther.github.io/orcan/latest/pl/ |
| Why Orcan? | [docs/en/why-orcan.md](docs/en/why-orcan.md) |
| Core Ideas | [docs/en/ideas/core-ideas.md](docs/en/ideas/core-ideas.md) |
| Mental Model | [docs/en/ideas/mental-model.md](docs/en/ideas/mental-model.md) |
| Quickstart (source) | [docs/en/getting-started/quickstart.md](docs/en/getting-started/quickstart.md) |
| Daily work vs release | [docs/en/development/release.md](docs/en/development/release.md) |
| Docs aliases (`dev` / `latest`) | [docs/en/deployment.md](docs/en/deployment.md) |
| Development | [docs/en/development/overview.md](docs/en/development/overview.md) |
| AI / agents | [AGENTS.md](AGENTS.md), [docs/en/ai/project-context.md](docs/en/ai/project-context.md) |

```bash
make docs-serve
```

## License

MIT — see [LICENSE](LICENSE).
