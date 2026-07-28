---
description: Typical Orcan workflows — day scenarios first, then the orcan CLI commands that support them.
---

# Typical workflows

These scenarios assume you already know [Core Ideas](../ideas/core-ideas.md). Commands run on the **host** unless marked **(container)**.

## Scenario: start the day in one context

You already configured workspaces. You want the browser terminal and yesterday’s mounts.

**Idea:** recreate the session without regenerating config.

```bash
cd /absolute/path/to/orcan
orcan up
```

Open `http://localhost:7681` and pick a workspace.

!!! note
    `orcan up` does **not** run `orcan sync`. If you changed `orcan.config.json`, apply config first.

## Scenario: switch customer or product line

**Problem:** another set of repos is today’s context.  
**Approach:** edit the workspace list (or enable another workspace), apply config, recreate the container.

```bash
orcan context wizard    # or edit orcan.config.json
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
orcan update                # or: git fetch && git checkout vX.Y.Z
orcan sync                  # if config schema changed
orcan build --force         # if Dockerfile/rootfs changed
orcan down && orcan up
```

## See also

- [Quick Start](../getting-started/quickstart.md)  
- [Troubleshooting](troubleshooting.md)  
- [CLI reference](../reference/cli.md)  
- [FAQ](../faq.md)
