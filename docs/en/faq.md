---
description: Short answers about Orcan — models, images, update, uninstall, bugs, and contributing.
---

# FAQ

Short answers to common Orcan questions.

## What is Orcan?

Orcan is a **work-context orchestrator**. It runs Cursor CLI (`agent`) and Claude Code (`claude`) in Docker with workspaces (named sets of projects), path-parity mounts, and a browser terminal.

Read [Why Orcan?](why-orcan.md) and [Core Ideas](ideas/core-ideas.md) before the rest of this FAQ.

## Does Orcan choose AI models?

**No.** Models stay with each CLI / account. Orcan does not pin or route models.

## How do I switch projects?

Edit `orcan.config.json` (or `make config-wizard`), then:

```bash
make env
make down && make terminal-docker
```

Do **not** pass `PROJECT_DIR=…` to `make terminal*`.

## Why does `make terminal` ignore my config edits?

`make terminal*` does not run `make env`. Always apply config first.

## Full image vs Claude-only?

=== "Full (default)"

    ```bash
    make build
    make terminal-docker
    ```

    Image: `orcan:latest` — Claude + Cursor (`agent`).

=== "Claude only"

    ```bash
    make build-claude
    IMAGE_LOCAL=orcan:claude make terminal-docker
    ```

    Image: `orcan:claude` — Claude only (`agent` is not installed).

## Is there a published Docker image?

**No** (not from CI). Clone the repo and `make build`. Optional private registry helpers exist for advanced use.

## Where is my login / cache data?

Under `$ORCAN_DATA` (default `~/.config/orcan`).

## Can I turn off tmux?

Not as a supported switch. The launcher starts tmux. Use multiple tmux windows/panes instead.

## How do I update?

```bash
git fetch && git checkout vX.Y.Z   # or: main
make env                           # when config schema changed
make rebuild                       # when Dockerfile/rootfs changed
make down && make terminal-docker
```

## How do I uninstall? { #uninstall }

```bash
cd /absolute/path/to/orcan
make down
make clean-data          # destructive: deletes ~/.config/orcan (type yes)
docker images 'orcan*'   # optional: docker rmi …
# then remove the git clone directory if you no longer need it
```

Details: [Workflows — uninstall](guides/workflows.md#uninstall).

## How do I report a bug?

Open a GitHub Issue with OS, Docker version, the Make target you ran, and relevant logs (`make logs`, `make path-check`):

https://github.com/aKyther/orcan/issues

## How do I contribute / add code?

1. Read [Contributing](https://github.com/aKyther/orcan/blob/main/CONTRIBUTING.md).
2. Follow [Development overview](development/overview.md).
3. Open a PR against `main`.

## See also

- [Quick start](getting-started/quickstart.md)
- [Troubleshooting](guides/troubleshooting.md)
- [Configuration](getting-started/configuration.md)
- [GitHub Issues](https://github.com/aKyther/orcan/issues)
