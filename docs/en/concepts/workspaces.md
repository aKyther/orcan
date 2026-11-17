---
description: Deep dive on Orcan workspaces — why they exist, layout, and how they map to config.
---

# Workspaces

## Problem

A single repository is rarely the whole job. Without a name for “these checkouts belong together”, every person rebuilds the set ad hoc — and agents only see whatever directory they were started in.

## Why workspaces exist

A **workspace** is Orcan’s unit of **context**: one name, one session, one shared starter pack for agents, and one or more **projects** (repo paths).

It is more important than a single project when you use coding agents, because the agent needs the **bundle**.

Read [Core Ideas](../ideas/core-ideas.md) first if these terms are new.

## How it works

Each workspace becomes:

- a folder under `/home/developer/workspaces/<name>`
- one **tmux** session with the same name
- a **context pack** at that root (manifest, shared instructions, ignores)

Each project is a symlink for navigation **and** a path-parity bind mount for Docker.

## Example layout

```text
/home/developer/workspaces/myapp/     # workspace root
  .manifest.json
  AGENTS.md
  backend  → symlink to /absolute/path/to/backend
  frontend → symlink to /absolute/path/to/frontend
```

## Config mapping

```json
{
  "name": "myapp",
  "projects": [
    { "name": "backend", "path": "/absolute/path/to/backend" }
  ]
}
```

- `name` → session + workspace directory  
- `projects[].name` → symlink name  
- `projects[].path` → absolute host/container path  

## Primary workspace

The first enabled workspace drives `WORKSPACE_ROOT` / `CONTAINER_PROJECT_DIR` in the launch process environment (entrypoint start directory).

## Trade-offs

- **Gain:** one named context you can recreate.  
- **Cost:** you must keep absolute paths accurate and run `orcan sync` after config edits.  
- **Choice:** Orcan does not rewrite every git checkout on start; seed projects explicitly when you want that.

## Git worktrees

A **git worktree** is another checkout of the same repository (separate path, usually another branch). Most of the time you just mount a normal clone path into a workspace and work on whatever branch is checked out.

Worktrees are **optional advanced help**: useful when you want a second checkout without touching the clone you use for `main` / pulls. Orcan creates those under `$ORCAN_PROJECTS_ROOT/.worktrees/<workspace>/<project>/` (default `~/.config/orcan/sandbox/.worktrees/...`) and records them in `registry.json`. Because that path sits under the stable projects-root bind, adding a worktree does **not** require recreating the container.

```bash
orcan init   # mount paths; optionally create/pick a worktree per project

# Non-interactive (one repo):
orcan context worktree create --repo /abs/repo --branch topic --workspace my-ws --project backend
orcan context worktree remove --workspace my-ws   # or --path /abs/managed/checkout
```

### Worktree from a GitHub fork

In the workspace editor, choose **Worktree** and enter `owner:branch` in the
branch field, for example `alice:fix/login`. Keep **Mount as-is** when you want
to use the original checkout directly.

On **Save changes**, Orcan looks up the owner's fork on GitHub, including forks
with a different repository name, and fetches the exact branch. This needs the
GitHub CLI (`gh`) on the host, API access, and Git access to the fork. Both
`github.com` and company GitHub Enterprise hosts are supported. Orcan reads the
repository and hostname from `origin`, then sends API requests to that hostname.
SSH remotes keep their SSH user and port; HTTPS remotes keep their host and port.
An SSH port is used for Git only, not for API requests.

For a company remote such as `git@github.company.example:team/app.git`, log in
on the host when needed:

```bash
gh auth login --hostname github.company.example
```

This selects a GitHub instance; it does not add GitLab or Bitbucket support.
SSH aliases must also resolve as a reachable GitHub API hostname.

Orcan creates the local branch `fork/alice/fix/login` and a remote named
`orcan-fork-alice`. The branch tracks the fetched fork branch. It preserves the
original checkout, its local changes and `origin`; it does not push anything.
An existing remote pointing elsewhere is never overwritten. Missing, inaccessible
or ambiguous forks and missing branches stop the save; Orcan never substitutes
`HEAD` for an explicit fork source. An existing local fork branch must be mounted
as-is or renamed before creating another checkout.

The same source syntax works from the CLI:

```bash
orcan context worktree create --repo /abs/repo --branch alice:fix/login --workspace review --project backend
```

Plain branch names keep the existing behavior. Fork lookup and fetching happen
only during creation, so editing or discarding a workspace draft makes no remote
changes. A failed fetch may leave the new fork remote configured for retry.

Example after a managed worktree create:

```json
{
  "name": "my-ws",
  "projects": [
    { "name": "backend", "path": "/home/you/.config/orcan/sandbox/.worktrees/my-ws/backend" },
    { "name": "frontend", "path": "/home/you/.config/orcan/sandbox/.worktrees/my-ws/frontend" }
  ]
}
```

## Related

- [Mental Model](../ideas/mental-model.md)  
- [Path parity](path-parity.md)  
- [Architecture](../architecture.md)  
- [Configuration](../getting-started/configuration.md)
