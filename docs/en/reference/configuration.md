# Configuration reference

Host file: `orcan.config.json` (stdlib JSON only).

Apply with `orcan sync`. Schema enforcement lives in `scripts/repository/apply-config.py`.
Machine-readable draft: [`orcan.config.schema.json`](https://github.com/aKyther/orcan/blob/main/orcan.config.schema.json).

## Top-level keys

| Key | Required | Description |
| --- | --- | --- |
| `workspaces` | yes | List of workspace objects; may be empty while preparing a container |
| `image` | no | Docker image used for builds and startup |
| `projects_root` | no | Absolute shared source catalog; default is the data root sandbox |
| `data_root` | no | Absolute host directory for persistent agent data; default `~/.config/orcan` |
| `timezone` | no | Container timezone; default `UTC` |
| `registry` | no | Image registry `host`, `repository`, optional `tag` |
| `plugins` | no | Grouped startup activation and settings; see [Startup plugins](../guides/plugins.md) |
| `executor` | legacy | Read as `plugins.redis` settings; does not enable the plugin |
| `executor_port` | legacy | Read as `plugins.redis.port`; default `8765` |
| `tmux` | no | Default window layout |
| `ttyd` | legacy | Read as `plugins.ttyd` settings; does not enable the plugin |
| `resources` | no | Container limits (default **2** CPU / **4g** RAM — raise in config when needed) |

Legacy accepted and normalized: single `workspace` object, or top-level `projects[]` (one workspace).

## Workspace object

| Key | Required | Description |
| --- | --- | --- |
| `name` | yes | tmux session + `/home/developer/workspaces/<name>` |
| `enabled` | no | Default true |
| `projects` | yes | List of `{ name, path }` |

### Project object

| Key | Required | Description |
| --- | --- | --- |
| `name` | yes | Symlink name under the workspace |
| `path` | yes | Absolute host path (path-parity mount) |

## Rejected keys (errors)

Do not use: `projects_dir`, `default_project`, `default_workspace`, project `alias` / `mount` / `role` / `windows`, workspace `root` / `meta_path` / `mount_mode`, per-workspace `tmux`.

## Derived (not user-settable)

- Workspace root: `/home/developer/workspaces/<name>`
- Host meta: `workspaces/<name>/`
- tmux session name = workspace `name`
- Primary workspace = first enabled entry

## Tools

| Command | Role |
| --- | --- |
| `orcan init` | Interactive editor |
| `orcan context add` | Non-interactive add |
| `orcan context add --from-worktree` | Add an existing git worktree |
| `orcan context worktrees` | List worktrees for a repo |
| `orcan context worktree create` | Create a worktree and pin it in config |
| `orcan context show` | List workspaces |
| `scripts/repository/config_io.py` | Load/dump/discover |

User guide: [Getting started — Configuration](../getting-started/configuration.md).

## Executor settings

Use `plugins.redis` for executor settings. `enabled: true` selects it for plain
`orcan up`; `--with-redis` enables it for one start. Workers, lanes, admission
limits, timeouts, retention and dashboard port belong to the same package.
The old `executor` and `executor_port` fields remain compatibility fallbacks.
See [Startup plugins](../guides/plugins.md) and
[Background executor](../guides/background-executor.md#configure-queues-and-execution-budgets).

## Persistent ownership exclusions

`orcan sync --no-chown 'external*'` saves name patterns in
`ownership.excluded_names`. `--chown-exclude /absolute/path` saves lexical paths
in `ownership.excluded_paths`. Both flags are also accepted by `orcan init` and
forwarded to its automatic sync. Repeated calls merge and deduplicate exclusions.
Every ownership update reloads these rules, so adding a project does not bypass
an existing exclusion. Directories are pruned before their type is inspected;
symlink targets are not followed. Edit the arrays to remove an exclusion.

```json
{
  "ownership": {
    "excluded_names": ["external*"],
    "excluded_paths": ["/data/remote mount"]
  }
}
```

Invalid ownership configuration stops sync before runtime files are generated or
data ownership is changed. Flags require an existing configuration; first-time
setup runs `orcan init /absolute/project`, then `orcan sync --no-chown 'external*'`. Init never runs sync or changes data ownership. Saved policies
apply to all workspaces using that configuration. They affect ownership only.

Host settings are resolved from JSON at command time. `resources.nofile` and
`resources.nproc` set process limits (integers >= 1024, default 65536).
Legacy `.env` files are ignored; see [migration](../getting-started/configuration.md#upgrade-from-dotenv-configuration).
