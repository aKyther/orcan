# Security

## Isolation limits

Orcan is convenient isolation for a **single trusted user on their own
machine**, **not** a hard multi-tenant security boundary.

- Bind mounts give the container write access to your projects
- `orcan up --with-docker` mounts `/var/run/docker.sock` → control of the host
  Docker engine (effectively host-level reach for anyone who can run Docker)
- `orcan up --with-git` mounts host `~/.ssh` (read-only) and may mount the SSH
  agent socket
- `orcan up --with-network NAME` joins an existing Docker network →
  network-level reachability to whatever else is on it, but **no** socket and
  **no** host Docker control

Agent rules and Cursor/Claude permission files guide behaviour. They are **not**
a sandbox.

## Capability ladder (intentional tradeoffs)

Prefer the weakest flag that still does the job:

| Need | Flag | Tradeoff |
| --- | --- | --- |
| Local container only (`orcan enter`) | *(none)* — default `orcan up` | Smallest blast radius — no published ttyd port |
| Browser terminal (remote / phone) | `--with-ttyd` | Publishes ttyd (`TTYD_BIND` defaults to loopback); use Tailscale for remote |
| Reach another compose stack by name/IP | `--with-network NAME` | Network reach only — **mutually exclusive with `--with-docker`** |
| Run nested `docker` / Compose against the host engine | `--with-docker` | **Known high risk** — opt-in; **mutually exclusive with `--with-network`** |
| `git push` / `pull` over SSH from inside | `--with-git` | Keys / agent exposed to the container — opt-in; combines with any mode above |

!!! warning
    Use `orcan up --with-docker` only when you need Docker-from-Docker. Prefer
    plain `orcan up`, or `--with-network`, when you do not need the socket.
    The flag exists so **you** accept that risk; Orcan prints a warning on
    start.

!!! warning
    Use `orcan up --with-git` only when you need push/pull from inside the
    container. It exposes your SSH keys (and agent) to the container.

There is no safe substitute for a mounted Docker socket that still grants full
engine control. If you only need reachability, use `--with-network`.
`--with-docker` and `--with-network` cannot be combined on one `orcan up`.

## Mount layout tradeoffs

Stable binds favour **dynamic workspace and project changes without recreating
the container**. That is intentional:

| Bind | Role | Tradeoff |
| --- | --- | --- |
| `$ORCAN_PROJECTS_ROOT` (default `…/sandbox`) | Anchor for managed project clones and `.worktrees/` | Everything under the sandbox is visible in the container — one stable mount, no recreate when you add a checkout |
| `$ORCAN_HOME/workspaces/` → `/home/developer/workspaces/` | Workspace UX roots (symlinks, context pack, inbox) | **All** configured workspaces share one parent mount — an agent in workspace A can see paths under workspace B. That enables adding/removing workspaces at runtime |
| `$ORCAN_DATA/context/` | Git-versioned Context Assertions store | **Not** mounted into the container — agents only drop into the workspace inbox; `orcan sync` on the host imports |

!!! warning
    Removing a workspace from config deletes its entire on-disk tree on the
    next reconcile (`orcan-runtime-reconcile`, or container boot) — not just
    the managed symlinks. Any `.orcan/session-brief.md`, agent-inbox tasks, or
    Context Assertions drops not yet synced under that workspace root are
    deleted with it, with no undo. This is intentional (no quarantine step),
    not a bug — see `reconcile.py`.

Orcan assumes a **single-user trust model** (you + agents on your host). Inbox
JSON is not cryptographically signed; malformed drops are quarantined, and
only a human accept/reject moves knowledge into the store. See
[Context Assertions](../ideas/context-assertions.md).

## Agent inbox / task execution

The [agent inbox](../ideas/agent-inbox.md) (`<workspace_root>/.orcan/tasks/`) hands
structured task manifests from a planning agent to an execution agent. Same
trust model as Context Assertions — unsigned JSON files, single host:

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

**Recommended remote access:** keep the publish address on loopback and reach
the machine over **Tailscale** (or another private VPN), then open
`http://localhost:<port>` on that host. That is the default product
recommendation.

!!! warning
    By default the ttyd port is published on **loopback only**
    (`TTYD_BIND=127.0.0.1`). ttyd has **no authentication** unless you set
    `TTYD_CREDENTIAL=user:password` in `.env`. Do not expose the port to the
    public Internet without auth and TLS.

Optional HTTP basic auth (`TTYD_CREDENTIAL`) is supported for cases where you
must publish beyond loopback (`TTYD_BIND=0.0.0.0`). Prefer Tailscale first;
treat credentials as a secondary layer, not the primary remote-access story.

Config: `ttyd.bind` in `orcan.config.json` (default `127.0.0.1`) → `TTYD_BIND`
via `orcan sync`. Credentials stay env-only so secrets stay out of committed
config.

!!! warning
    `orcan up --with-ttyd-auth USER:PASS` sets the same `TTYD_CREDENTIAL` as
    above, but as a **command-line argument** — it lands in your shell
    history and is visible to anything that can list processes on the host
    (`ps`) for as long as `orcan up` runs. Prefer `TTYD_CREDENTIAL` in `.env`
    (`--with-ttyd`, no argument) when you can; reach for `--with-ttyd-auth`
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
