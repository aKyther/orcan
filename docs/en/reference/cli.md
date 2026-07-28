# CLI reference

Public interface for Orcan is the **`orcan`** command (Bash). Make targets remain for **maintainers** only (docs, tests, release).

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/aKyther/orcan/main/install.sh | bash
```

| Path | Role |
| --- | --- |
| `~/.local/share/orcan` | Git clone (`ORCAN_ROOT`) |
| `~/.local/bin/orcan` | Launcher |
| `~/.config/orcan/home` | Config + `.env` + `.orcan/*` (`ORCAN_HOME`) — **always** the default |
| `~/.config/orcan` | Tool data / logins (`ORCAN_DATA`) |

Override only if needed: `ORCAN_HOME=/path` or `ORCAN_USE_CWD=1` (use `./orcan.config.json` in the current directory).

## Host dependencies

The `orcan` command is **Bash**, but config work on the host uses **Python 3** (stdlib only — no pip/venv):

| Need | Used by |
| --- | --- |
| Bash, Git | CLI, install, `orcan update` |
| **Python 3** | `orcan sync`, `init`, `context` (wizard / show / add) |
| Docker Compose v2 | `orcan build`, `up`, `down`, … |

Check with `orcan doctor`. Details: [Installation](../getting-started/installation.md).

## Commands

| Command | Role |
| --- | --- |
| `orcan init [PATH]` | First run: scaffold config, sync, show |
| `orcan sync` | Apply `orcan.config.json` → `.env` + `.orcan/*` |
| `orcan context show` | List workspaces + path-parity summary |
| `orcan context wizard` | Interactive config editor |
| `orcan context add PATH` | Add a project (`--workspace`, `--force`) |
| `orcan up [--with-docker] [--with-git]` | Start browser terminal (socket / host SSH only with flags); hints if a newer release exists |
| `orcan down` | Stop containers |
| `orcan build [--claude|--cursor] [--force] [--no-cache]` | Both agents → `orcan:latest` + `orcan:<VERSION>` (pull or build). `--claude` / `--cursor` → `orcan:<VERSION>-claude\|cursor` (no pull; does not overwrite `latest`). Never publishes |
| `orcan pull` | Pull both-agents `orcan:<VERSION>` → `orcan:latest` |
| `orcan publish` | Push both-agents `orcan:latest` (**manual**; not `-claude`/`-cursor`) |
| `orcan url` | Print terminal URL |
| `orcan logs` | Follow logs |
| `orcan update [--release\|--main]` | Newest release tag `vX.Y.Z` (default); `--main` for bleeding edge |
| `orcan doctor` | Host / config health report |
| `orcan uninstall [--purge-data]` | Remove CLI (optional wipe of `ORCAN_DATA`) |
| `orcan version` / `orcan help` | Version / help |

### Optional

| Command | Role |
| --- | --- |
| `orcan seed [--all] [--dry-run]` | Copy ignore/templates into git checkouts — **rarely needed**; the workspace context pack is enough |

## Ritual

```bash
orcan init
orcan build
orcan up
```

After config edits:

```bash
# edit ~/.config/orcan/home/orcan.config.json
orcan sync
orcan down && orcan up
```

`orcan up` does **not** run `sync`.

### `orcan up` flags

| Flag | Effect |
| --- | --- |
| *(none)* | Browser terminal only — no Docker socket, no host SSH |
| `--with-docker` | Mount `/var/run/docker.sock` (Docker-from-Docker) |
| `--with-git` | Mount host `~/.ssh` read-only (+ SSH agent when `SSH_AUTH_SOCK` is set) for push/pull |

Flags combine: `orcan up --with-docker --with-git`.

Git **author** identity is always synced by `orcan sync` (`GIT_AUTHOR_*` from host `user.name` / `user.email`). SSH keys are only attached with `--with-git`. Both optional flags print a security warning — agents inside can use the mounted socket or keys. See [Security](security.md) and [Workflows](../guides/workflows.md).

## Maintainer Make

From a git checkout: `make validate`, `make test-host`, `make docs*`, `make release*`, `make registry-*`. See [Development](../development/overview.md).
