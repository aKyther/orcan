# Bundled Orcan plugins

Each `plugins/<id>/` directory groups one integration's metadata, configuration
rules, lifecycle hooks, Compose overlay (when static), and operating documentation.
The user edits only `orcan.config.json`; package files ship with Orcan.

## Package contract

- `plugin.json`: ID, title, functional group, aliases, flags, default activation,
  typed fields with labels/defaults/ranges, dependencies and conflicts.
- `runtime.sh`: optional `orcan_plugin_<id>_prepare`, `_verify`, `_report` hooks.
  Sourcing defines functions only. Hooks are loaded exclusively from the bundled
  catalog, never from configuration-provided paths or third-party downloads.
- `compose.yml`: static container additions, when applicable.
- `README.md`: purpose, operating rules, authentication sources and diagnostics.

The common resolver applies defaults, compatibility sections, `plugins.<id>`, then
explicit CLI overrides. Disabled plugins do not prepare credentials, ports or
mounts. All selection/configuration errors and preparation failures occur before
stopping the current container. Dependencies and conflicts are checked after CLI
selection, so an explicit disable can resolve a configured conflict.

`orcan settings` groups startup plugins as access, services and interfaces. A
reviewed save writes `plugins` and migrates the old executor/ttyd settings into
these sections. Workspaces are preserved. `orcan up` starts the saved selection;
existing flags and `--with NAME` / `--without NAME` override one start only.

Resolved launch records contain validated settings and activation, never tokens
or passwords. `--resume` reuses that record and reacquires authentication. A
password passed as a terminal auth argument must be supplied again.

`orcan plugins list`, `validate` and `doctor` use the same package catalog.
Availability, activation and readiness are separate facts. Redis is the local
broker for the background executor; `executor` remains a compatibility alias.
Session notification destinations must always be explicit. Plugins never start
models, merge, push, deploy or restore failed tasks automatically.
