---
description: Security model — single-user isolation limits, mounts, ttyd auth, and capability ladder.
tags:
  - security
  - reference
---

# Security

## Isolation limits

Orcan is convenient isolation for a **single trusted user on their own
machine**, **not** a hard multi-tenant security boundary.

- Bind mounts give the container write access to your projects
- `orcan up --docker-socket` mounts `/var/run/docker.sock` → control of the host
  Docker engine (effectively host-level reach for anyone who can run Docker)
- `orcan up --ssh` mounts host `~/.ssh` (read-only) and may mount the SSH
  agent socket
- `orcan up --network NAME` joins an existing Docker network →
  network-level reachability to whatever else is on it, but **no** socket and
  **no** host Docker control

Agent rules and Cursor/Claude permission files guide behaviour. They are **not**
a sandbox.

## Capability ladder (intentional tradeoffs)

Prefer the weakest flag that still does the job:

| Need | Flag | Tradeoff |
| --- | --- | --- |
| Local container only (`orcan enter`) | *(none)* — default `orcan up` | Smallest blast radius — no published ttyd port |
| Browser terminal (remote / phone) | `--web-terminal` | Publishes ttyd (`TTYD_BIND` defaults to all interfaces); prefer Tailscale + auth |
| Reach another compose stack by name/IP | `--network NAME` | Network reach only — **mutually exclusive with `--docker-socket`** |
| Run nested `docker` / Compose against the host engine | `--docker-socket` | **Known high risk** — opt-in; **mutually exclusive with `--network`** |
| GitLab API / MR review | `--gitlab` | Token available to container agents and Docker administrators; scope it to required projects and permissions |
| GitHub API / PR review | `--github` | Token available to container agents and Docker administrators; scope it to required repositories and permissions |
| `git push` / `pull` over SSH from inside | `--ssh` | Keys / agent exposed to the container — opt-in; combines with any mode above |

!!! warning
    Use `orcan up --docker-socket` only when you need Docker-from-Docker. Prefer
    plain `orcan up`, or `--network`, when you do not need the socket.
    The flag exists so **you** accept that risk; Orcan prints a warning on
    start.

!!! warning
    Use `orcan up --ssh` only when you need push/pull from inside the
    container. It exposes your SSH keys (and agent) to the container.

There is no safe substitute for a mounted Docker socket that still grants full
engine control. If you only need reachability, use `--network`.
`--docker-socket` and `--network` cannot be combined on one `orcan up`.

## Mount layout tradeoffs

Inside the container, the `ssh` launcher overrides `ControlPath` to
`~/.cache/orcan/ssh/%C`. This private, writable directory lets SSH create and
reuse connection sockets even when host `~/.ssh` is mounted read-only.
`ControlMaster` and `ControlPersist` keep their configured values. Host and
container control sockets are separate; keys and configuration remain read-only.
Tools explicitly invoking `/usr/bin/ssh` bypass this launcher.

Stable binds favour **dynamic workspace and project changes without recreating
the container**. That is intentional:

| Bind | Role | Tradeoff |
| --- | --- | --- |
| `$ORCAN_PROJECTS_ROOT` (default `…/sandbox`) | Anchor for managed project clones and `.worktrees/` | Everything under the sandbox is visible in the container — one stable mount, no recreate when you add a checkout |
| `$ORCAN_HOME/workspaces/` → `/home/developer/workspaces/` | Workspace UX roots (symlinks, context pack, inbox) | **All** configured workspaces share one parent mount — an agent in workspace A can see paths under workspace B. That enables adding/removing workspaces at runtime |

## Agent inbox / task execution

- Default policy (`approve`) requires a human `orcan-inbox approve` before a
  task is claimable. `draft` is never claimable. Both are safe to leave
  unattended.
- `policy: auto` skips that gate — a task is claimable the moment it is
  proposed.
- `execution.executor: shell` runs `execution.command` as a real shell
  command in the workspace root. **`auto` + `shell` together mean a task
  file is executed with no human step in between** — treat anything that can
  write into `.orcan/tasks/inbox/` (a script, another agent, a shared
  filesystem) as something that can run commands on your host.
- `orcan-inbox watch` only runs when you start it. Nothing polls the inbox by
  default.

If you don't need unattended execution, stick to the `approve` default and
review each task before approving it.

## Data on the host

Logins and caches live under `$ORCAN_DATA` (default `~/.config/orcan`). Treat
that directory as sensitive.

`orcan uninstall --purge-data` deletes it after confirmation.

## Browser terminal

**Recommended remote access:** reach the machine over **Tailscale** (or
another private VPN) and use HTTP basic auth (`TTYD_CREDENTIAL` or
`--web-terminal-auth`). For a host-local browser only, set
`TTYD_BIND=127.0.0.1`.

!!! warning
    By default the ttyd port is published on **all host interfaces**
    (`TTYD_BIND=0.0.0.0`). ttyd has **no authentication** unless you set
    `TTYD_CREDENTIAL=user:password` in `.env` or use `--web-terminal-auth`.
    Do not expose the port to the public Internet without auth and TLS.

Optional HTTP basic auth (`TTYD_CREDENTIAL`) is the extra layer when the
port is reachable on a LAN or VPN. Prefer Tailscale first; treat
credentials as a secondary layer, not the primary remote-access story.

Config: `ttyd.bind` in `orcan.config.json` (default `0.0.0.0`) → `TTYD_BIND`
via `orcan sync`. Credentials stay env-only so secrets stay out of committed
config. Existing `.env` is not rewritten if `TTYD_BIND` is already set.

!!! warning
    `orcan up --web-terminal-auth USER:PASS` sets the same `TTYD_CREDENTIAL` as
    above, but as a **command-line argument** — it lands in your shell
    history and is visible to anything that can list processes on the host
    (`ps`) for as long as `orcan up` runs. Prefer `TTYD_CREDENTIAL` in `.env`
    (`--web-terminal`, no argument) when you can; reach for `--web-terminal-auth`
    for a quick one-off rather than routine use.

## What not to do

- Do not start `--privileged` containers for Orcan
- Do not mount `/`, `/home`, `/etc`, `/usr`, `/var`, `/opt`, or `/root` (or
  paths under those trees except normal `/home/<user>/…` projects) as
  `PROJECT_DIR`
- Do not commit `.env`, tokens, or `ORCAN_DATA` contents
- Do not run `docker system prune` as part of normal Orcan workflows

## See also

- [Docker](docker.md)
- [Mental model](../ideas/mental-model.md) — sandbox as anchor, workspace mounts
- [Workflows](../guides/workflows.md)
- [Environment variables](environment.md)
