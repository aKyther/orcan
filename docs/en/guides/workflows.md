---
description: Typical Orcan workflows — day scenarios first, then the Make commands that support them.
---

# Typical workflows

These scenarios assume you already know [Core Ideas](../ideas/core-ideas.md). Commands run on the **host** unless marked **(container)**.

## Scenario: start the day in one context

You already configured workspaces. You want the browser terminal and yesterday’s mounts.

**Idea:** recreate the session without regenerating config.

```bash
cd /absolute/path/to/orcan
make terminal-docker
```

Open `http://localhost:7681` and pick a workspace.

!!! note
    `make terminal*` does **not** run `make env`. If you changed `orcan.config.json`, apply config first.

## Scenario: switch customer or product line

**Problem:** another set of repos is today’s context.  
**Approach:** edit the workspace list (or enable another workspace), apply config, recreate the container.

```bash
make config-wizard    # or edit orcan.config.json
make env
make init-project-all # optional seeds into each project path
make down
make terminal-docker
```

## Scenario: safer terminal without host Docker socket

**Trade-off:** no Docker-from-Docker; smaller blast radius.

```bash
make terminal
```

## Scenario: Claude only

**Idea:** smaller image when Cursor CLI is not needed.

```bash
make build-claude
IMAGE_LOCAL=orcan:claude make terminal-docker
```

## Scenario: rebuild after Dockerfile or rootfs changes

**Idea:** context description stayed the same; the **tooling image** changed.

```bash
make rebuild          # full
# or
make rebuild-claude
make down
make terminal-docker
```

## Scenario: verify path parity

**Why:** nested Docker only works if absolute paths match.

```bash
make path-check
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
make down                 # stop; keep ~/.config/orcan
make clean                # compose down style
make clean-data           # DESTRUCTIVE: deletes ORCAN_DATA (type yes)
```

Full removal: [Uninstall](#uninstall).

## Uninstall { #uninstall }

```bash
cd /absolute/path/to/orcan
make down
make clean-data
docker images 'orcan*'
docker rmi orcan:latest orcan:full orcan:claude   # optional
rm -rf /absolute/path/to/orcan                    # optional
```

Mounted project repos are untouched unless you delete them yourself.

## Upgrade Orcan

```bash
cd /absolute/path/to/orcan
git fetch
git checkout vX.Y.Z       # or main
make env                  # if config schema changed
make rebuild              # if Dockerfile/rootfs changed
make down && make terminal-docker
```

## See also

- [Quick Start](../getting-started/quickstart.md)  
- [Troubleshooting](troubleshooting.md)  
- [Makefile reference](../reference/makefile.md)  
- [FAQ](../faq.md)
