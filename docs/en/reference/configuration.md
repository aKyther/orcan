# Configuration reference

Host file: `orcan.config.json` (stdlib JSON only).

Apply with `make env`. Schema enforcement lives in `scripts/repository/apply-config.py`.
Machine-readable draft: [`orcan.config.schema.json`](https://github.com/aKyther/orcan/blob/main/orcan.config.schema.json).

## Top-level keys

| Key | Required | Description |
| --- | --- | --- |
| `workspaces` | yes (non-empty) | List of workspace objects |
| `tmux` | no | Default window layout |
| `ttyd` | no | Browser terminal settings |
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
- Host meta: `.orcan/workspaces/<name>/`
- tmux session name = workspace `name`
- Primary workspace = first enabled entry

## Tools

| Command | Role |
| --- | --- |
| `make config-wizard` | Interactive editor |
| `make config-scaffold` | Non-interactive add |
| `make config-show` | List workspaces |
| `scripts/repository/config_io.py` | Load/dump/discover |

User guide: [Getting started — Configuration](../getting-started/configuration.md).
