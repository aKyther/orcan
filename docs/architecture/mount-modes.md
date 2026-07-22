# Mount modes: parity vs workspace

cind supports two ways to expose project repos inside a workspace. Pick per workspace or per project depending on what you need that session for.

## When to use which

| Goal | Mount mode | Example |
| --- | --- | --- |
| Run `docker compose` via host socket | `parity` | Dev workspace with microservices |
| Bind mounts must match host paths 1:1 | `parity` | CI-like local stacks |
| Read code, search, debug, AI review | `workspace` | Temporary audit of a foreign repo |
| Host path is awkward or impossible to mirror | `workspace` | Windows share, mismatched WSL layout |
| Mix both in one container | per-project override | Parity for app repo, workspace for docs clone |

## `parity` (default)

Host and container share the **same absolute path**:

```text
Host:       /home/you/gotibooks/backend
Container:  /home/you/gotibooks/backend
Docker daemon sees: /home/you/gotibooks/backend
```

Workspace symlinks still provide ergonomic aliases under the workspace root, but the canonical path exists at both sides.

Use this when the agent or you will run Docker against the host daemon from inside cind.

## `workspace`

Host path is bound to a **container-only path** under the workspace root:

```text
Host:       /mnt/share/upstream-app
Container:  /home/developer/workspaces/review/upstream-app
Docker daemon: does NOT know /home/developer/workspaces/...
```

Default workspace root for `mount_mode: "workspace"` is `/home/developer/workspaces/<name>` (override with `root`).

Use this for analysis sessions where path parity is unnecessary or impossible. **Do not** run host Docker compose from these paths expecting bind mounts to work.

## Configuration

### Workspace default

```json
{
  "name": "code-review",
  "mount_mode": "workspace",
  "tmux": "review",
  "projects": [
    {
      "name": "upstream",
      "path": "/absolute/host/path/to/repo",
      "alias": "upstream"
    }
  ]
}
```

### Per-project override

```json
{
  "name": "gotibooks",
  "mount_mode": "parity",
  "projects": [
    {
      "name": "backend",
      "path": "/home/you/gotibooks/backend",
      "alias": "backend",
      "mount": "parity"
    },
    {
      "name": "vendor-fork",
      "path": "/mnt/vendor/read-only-copy",
      "alias": "vendor-fork",
      "mount": "workspace"
    }
  ]
}
```

## Generated runtime fields

Each project in `.cind/runtime-config.json` includes:

| Field | Meaning |
| --- | --- |
| `path` | Host absolute path (always) |
| `container_path` | Path to use inside the container |
| `alias_path` | Workspace alias (`<root>/<alias>`) |
| `mount` | `parity` or `workspace` |

`.env` sets:

| Variable | Role |
| --- | --- |
| `PROJECT_DIR` | Default project's **host** path (validation on host) |
| `CONTAINER_PROJECT_DIR` | Default project's path **inside** the container (`working_dir`) |

## Agents

Read `.manifest.json` in the workspace root. Respect `mount` when suggesting Docker commands:

- `parity` → `path` is safe for host Docker bind sources
- `workspace` → use `container_path` for file operations only

See also: [Path parity](../path-parity.md) · [Virtual workspace](workspace.md)
