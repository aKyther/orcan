---
description: Typical Orcan workflows — day scenarios first, then the orcan CLI commands that support them.
---

# Typical workflows

These scenarios assume you already know [Core Ideas](../ideas/core-ideas.md). Commands run on the **host** unless marked **(container)**.

## Scenario: start the day in one context

You already configured workspaces. You want a dev container with yesterday’s mounts.

**Idea:** recreate the session without regenerating config.

```bash
cd /absolute/path/to/orcan
orcan up              # local — orcan enter on the same machine
# remote browser: orcan up --with-ttyd && orcan url
```

!!! note
    `orcan up` does **not** run `orcan sync`. If you changed `orcan.config.json`, apply config first.

## Scenario: local terminal (not only the browser) { #local-terminal }

**When:** you are on the same machine as the container (laptop), and you want a native terminal — or a second client alongside `--with-ttyd`.

Plain `orcan up` is local-only (no published port). **`orcan enter`** is the default path on the same machine. Add **`--with-ttyd`** when you need the browser (remote / phone).

```bash
orcan enter                 # workspace picker (agent-launcher) — default
orcan enter --tmux          # list sessions; attach if only one
orcan enter --tmux my-ws    # attach a named session
orcan enter --shell         # plain zsh (not in tmux)

# equivalent low-level:
docker exec -it orcan-1 tmux ls
docker exec -it orcan-1 agent-launcher
```

Alias: `orcan go-in` (same as `enter`). Default container name is `orcan-1` (`ORCAN_INSTANCE`). Detach tmux with prefix + `d` — the session keeps running for ttyd and other clients.

!!! tip
    Browser + local terminal can share one session: edit in iTerm/Windows Terminal, keep ttyd open on a phone or second screen.

## Scenario: switch customer or product line

**Problem:** another set of repos is today’s context.  
**Approach:** edit the workspace list (or enable another workspace), apply config, recreate the container.

```bash
orcan init    # or edit orcan.config.json
orcan sync
orcan down
orcan up
```

## Scenario: safer terminal without host Docker socket

**Trade-off:** no Docker-from-Docker; smaller blast radius. This is the **default**.

```bash
orcan up
```

## Scenario: terminal with host Docker socket (DinD)

**When:** nested Compose / Docker from inside the container.

```bash
orcan up --with-docker
```

**Tradeoff:** the socket ≈ control of the host Docker engine. The flag is a
deliberate opt-in (warning on start). There is no “full host Docker but
sandboxed” mode. If you only need to reach other containers, prefer
`--with-network`. Details: [Security](../reference/security.md).

## Scenario: reach containers on an existing Docker network

**When:** the container needs to reach another container by name/IP (e.g. a
project's own `docker compose` stack) but doesn't need to control the host
Docker engine. Lower-risk than `--with-docker` — no socket mounted.

```bash
docker network create my-net   # if it doesn't exist yet
orcan up --with-network my-net
```

## Scenario: git push/pull from inside the container

**When:** commits already match the host identity (via `orcan sync`); you also need SSH keys or an agent for remotes.

```bash
orcan up --with-git
# with DinD:
orcan up --with-docker --with-git
```

## Scenario: optional git worktree

**When:** you want a second checkout without changing the clone you use for `main` / pulls.

In the wizard, after you enter a project path, answer **yes** to the advanced worktree question (default is **no** — just mount the path).

Or non-interactively:

```bash
orcan context worktree create --repo /absolute/path/to/repo \
  --branch topic --workspace my-ws --project backend
orcan sync && orcan down && orcan up
```

Managed paths live under `$ORCAN_PROJECTS_ROOT/.worktrees/`. Clean up: wizard → **clean**, or `orcan context worktree remove --workspace my-ws`.

## Scenario: install only one agent

**Idea:** skip installing an agent you will not use (smaller image, same tags).

```bash
orcan build --claude   # → orcan:<VERSION>-claude
IMAGE_LOCAL=orcan:0.1.1-claude orcan up
# or
orcan build --cursor   # → orcan:<VERSION>-cursor
IMAGE_LOCAL=orcan:0.1.1-cursor orcan up
```

## Scenario: rebuild after Dockerfile or rootfs changes

**Idea:** context description stayed the same; the **tooling image** changed.

```bash
orcan build --force       # full image; skip pull, rebuild locally
# or
orcan build --claude --force
orcan down
orcan up
```

## Scenario: verify path parity

**Why:** nested Docker only works if absolute paths match.

```bash
orcan context show
```

## Inside the container

| Need | Command |
| --- | --- |
| List workspaces | `orcan-workspaces` |
| Context pack status | `orcan-context-status` |
| Seed all projects | `orcan-init-projects` |
| Session brief | `orcan-session-brief` |
| AI status line helper | `orcan-ai-statusline` |
| Cursor CLI | `agent` / `ag` |
| Claude Code | `claude` / `cc` |

Launcher keys: workspace number, `s` = status, `i` = init hint, `q` = quit.

## Stop, clean, uninstall

```bash
orcan down                 # stop; keep ~/.config/orcan
orcan uninstall --purge-data           # DESTRUCTIVE: deletes ORCAN_DATA (type yes)
```

Full removal: [Uninstall](#uninstall).

## Uninstall { #uninstall }

```bash
cd /absolute/path/to/orcan
orcan down
orcan uninstall --purge-data
docker images 'orcan*'
docker rmi orcan:latest 'orcan:*'   # optional: drop local tags
rm -rf /absolute/path/to/orcan                    # optional
```

Mounted project repos are untouched unless you delete them yourself.

## Upgrade Orcan

```bash
cd /absolute/path/to/orcan
orcan update                # newest GitHub Release tag (vX.Y.Z)
# orcan update --main       # follow main instead
orcan sync                  # if config schema changed
orcan build --force         # if Dockerfile/rootfs changed
orcan down && orcan up
```

## See also

- [Quick Start](../getting-started/quickstart.md)  
- [Troubleshooting](troubleshooting.md)  
- [CLI reference](../reference/cli.md)  
- [FAQ](../faq.md)
