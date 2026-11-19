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
- `compose.yml`: static container additions, when applicable. Resolved plugin
  variables are supplied by the host; overlays do not own separate setting defaults.
- `supervisor.sh`: optional bundled container hook named
  `orcan_plugin_<id>_supervisor`. It selects package-owned `supervisor.d/` templates
  through the shared `install_program` helper. Sourcing defines functions only;
  the hook checks activation before installing programs.
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

## Ownership of settings and tests

Package fields own plugin defaults, ranges and environment variable names.
Host configuration and the legacy ttyd/executor APIs project these fields rather
than maintaining separate rules. Legacy JSON sections remain readable; Settings
writes the package-based configuration.

Host tests exercise the active package editor and CLI lifecycle. Shared shell
fixtures live in `tests/host/_plugin_shell.py`; integration tests do not import
another collected test module. Compatibility tests cover old inputs through the
same resolver, rather than keeping unused editors alive.

## Application code and container integration

`cockpit/` and `executor/` are Python applications with independent dependency
locks. Plugin packages own their integration with Orcan. `plugins/cockpit` is a
built-in interface entry; it does not start a background service. `plugins/redis`
owns the executor's service templates and worker selection. The common Supervisor
launcher loads bundled package hooks without knowing Redis service names.

The executor reads defaults, integer bounds and environment variable names from
`plugins/redis/plugin.json`. Its wheel bundles that descriptor from the same
source, so a standalone installation does not require a host checkout. Host
configuration continues to use the shared plugin resolver. Both applications
remain installed in the runtime image; service activation is a separate choice.
