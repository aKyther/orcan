# cind

**cind** orchestrates **environment and context** for coding agents: workspaces, path-parity mounts, instruction/ignore seeds, and a browser tmux launcher.

Cursor CLI (`agent`) and Claude Code (`claude`) are **pluggable tools** inside that environment. **Models are out of scope** — configure them in each CLI / account, not in cind.

## What this project is

A ready-to-run container image and Compose setup where:

* workspaces group one or more repos into one context unit (tmux session)
* projects mount with path parity (same absolute path on host and in the container)
* agents get a **context pack** (`AGENTS.md` / `CLAUDE.md`, ignores, manifest) at the workspace root
* the host stays free of global language toolchains
* optional Docker socket access is an explicit choice

## Who should use it

* Developers who want Cursor and/or Claude CLI in one isolated toolbox
* Teams that want the same toolchain and context layout on every machine
* Anyone who wants clearer boundaries between agent work and the host OS

## Project goals

1. Keep the host clean.
2. Own **where** agents work and **what** they should see — not which model they use.
3. Make everyday commands short (`make build`, `make terminal`).
4. Be honest about security limits.

## Start here

| Page | Content |
| --- | --- |
| [Getting started](getting-started.md) | Ritual: wizard → `make env` → `make terminal-docker` |
| [Config](config.md) | `cind.config.yaml` + interactive wizard |
| [Context orchestration](architecture/context.md) | Product boundary, context pack, non-goals |
| [Virtual workspace](architecture/workspace.md) | Workspace = context unit |
| [Installation](installation.md) | Requirements and setup |
| [Docker](docker.md) | Image, Compose, binds, users |
| [Makefile](makefile.md) | Every Make command |
| [Cursor](cursor.md) | Global profile, image defaults, project init |
| [Security](security.md) | What is and is not isolated |
| [Development](development.md) | Repository vs container layout |
| [FAQ](faq.md) | Common questions |
| [Troubleshooting](troubleshooting.md) | Fixes for common failures |
