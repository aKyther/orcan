# Orcan

**Work-context orchestrator** for coding agents. Run **Cursor CLI** (`agent`), **Claude Code** (`claude`), and **Codex CLI** (`codex`) in Docker with path-parity mounts, workspaces (named sets of projects), and an optional browser tmux terminal.

Models are out of scope — each CLI picks its own.

[Documentation](https://akyther.github.io/orcan/latest/) · [Changelog](CHANGELOG.md) · [Contributing](CONTRIBUTING.md)

## Status

Version **4.0.20**. Distributed as a **CLI** (`orcan`). `orcan build` pulls the image for this version when available, otherwise builds locally. Publishing images is **manual** (`orcan publish`) and not part of build. CI validates and publishes docs; it does **not** publish container images.

## Features

- Workspaces (one tmux session per workspace)
- Path parity (same absolute paths host ↔ container)
- Images: `orcan:latest` / `orcan:<VERSION>` (all agents); optional local `orcan:<VERSION>-claude` / `-cursor` / `-codex`
- Local container by default (`orcan enter` on the same machine)
- Optional browser terminal (`orcan up --web-terminal` → ttyd → launcher → tmux → zsh)
- Optional GitHub/GitLab API access (`orcan up --github` / `--gitlab`; [CLI](docs/en/reference/cli.md))
- Host data under `~/.config/orcan` (`ORCAN_DATA`)
- JSON config + wizard (`orcan.config.json`)
- Documentation in clear English

## Requirements

| Tool | Role |
| --- | --- |
| Bash | `orcan` CLI dispatcher |
| Python 3 | Host config: `sync`, `init` (incl. wizard), `context` (show / add / hook) — stdlib only, no pip |
| Git | Install clone + your projects |
| Docker (Compose v2) | Container runtime (`orcan up`, optional `--web-terminal`) |

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
orcan sync                               # after later edits to orcan.config.json
orcan build --agent codex
orcan up                                 # local — use `orcan enter` on the same machine
# remote browser: orcan up --web-terminal && orcan url
```

After config edits: `orcan sync` then `orcan up` (or `orcan down && orcan up`). Rebuild the image only when the Dockerfile or agent install set changed — not for workspace/project changes.

### Useful commands

| Command | Role |
| --- | --- |
| `orcan sync` | Apply `orcan.config.json` → `.env` + `mounts/*` |
| `orcan init` | Interactive config wizard (no PATH: create or edit) |
| `orcan up` / `orcan up --web-terminal` / `orcan up --docker-socket \| --network NAME` / `orcan up --ssh` / `orcan down` | Start container (local by default; optional browser / DinD **or** network / SSH) / stop |
| `orcan build --agent NAME [...]` / `--all-agents` | Explicit client selection in standard `latest` + `<VERSION>` tags; inspect it with `orcan status` |
| `orcan publish` | Manual image push (maintainers) |
| `orcan upgrade [--to VERSION]` / `orcan downgrade` | Newest release / pin / one step back |
| `orcan update` | Dev channel: fast-forward to `origin/main` |
| `orcan uninstall` | Remove Orcan (`--purge-data` removes logins/cache, `--purge-images` images; projects stay) |

Config lives in `~/.config/orcan/` by default (install clone: `~/.local/share/orcan`).

## Documentation

| Topic | Link |
| --- | --- |
| Full docs (EN) | https://akyther.github.io/orcan/latest/ |
| Why Orcan? | [docs/en/why-orcan.md](docs/en/why-orcan.md) |
| Core Ideas | [docs/en/ideas/core-ideas.md](docs/en/ideas/core-ideas.md) |
| Mental Model | [docs/en/ideas/mental-model.md](docs/en/ideas/mental-model.md) |
| Agent inbox | [docs/en/ideas/agent-inbox.md](docs/en/ideas/agent-inbox.md) |
| Runtime reconcile | [docs/en/ideas/runtime-reconcile.md](docs/en/ideas/runtime-reconcile.md) |
| Quickstart (source) | [docs/en/getting-started/quickstart.md](docs/en/getting-started/quickstart.md) |
| CLI reference | [docs/en/reference/cli.md](docs/en/reference/cli.md) |
| Development | [docs/en/development/overview.md](docs/en/development/overview.md) |
| AI / agents | [AGENTS.md](AGENTS.md), [docs/en/llms.txt](docs/en/llms.txt), [docs/en/ai/project-context.md](docs/en/ai/project-context.md) |

```bash
make docs-serve   # maintainers — MkDocs from a git checkout
```

## License

MIT — see [LICENSE](LICENSE).


### Optional background checks

`orcan up --with-redis` enables an internal Redis broker, a background executor and
[a local read-only dashboard](docs/en/guides/background-executor.md). Agents can
submit committed snapshots for Python, Java, Scala and project-defined procedures,
then continue the conversation. Workspace AGENTS.md / CLAUDE.md explain availability,
submission, small results, bounded log reading and the default one-hour retention.
Plain `orcan up` keeps the existing direct workflow.


### Choose image contents

Set `build.agents` and optional `build.tools` in
`orcan.config.json`, preview with `orcan build --plan`, then run `orcan build`.
Claude and Cursor context files are generated only for clients installed in the
image. See [Image profiles](docs/en/guides/image-profiles.md) for precedence,
workspace updates and safe preservation of custom files.


### Runtime plugins, memory and interfaces

`orcan plugins list|validate|doctor` describes and checks built-in SSH, Docker,
ttyd, Redis and cockpit capabilities. Prefer `--with-ssh` for SSH access.
`orcan memory` manages explicit knowledge, bounded retrieval and archived handoff
recaps; project knowledge follows the Git common directory across worktrees.
See [Orcan flow](docs/en/guides/orcan-flow.md) for commands, source/version selection,
cockpit I/O budgets, and the separation between build-time and runtime choices.
