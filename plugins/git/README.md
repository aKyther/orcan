# Git identity

Read global host Git name/email as defaults; repository-specific identity wins.

## Configuration and activation

Configuration: `orcan.config.json` → `plugins.git`. The package's
`plugin.json` defines its fields, defaults, aliases and conflicts. Use
`orcan settings` to choose defaults; CLI flags override only one start.

Flags: `--with-git-identity`.

## Operating rules

Default enabled to preserve existing Git identity behavior. No SSH keys or hosting tokens are exposed.

## Authentication and data

Host global Git configuration; no credentials are persisted.

## Lifecycle and diagnostics

`runtime.sh` owns this package's host hooks. The shared lifecycle resolves,
validates, prepares, starts, verifies and reports. Sourcing a package performs no
external actions. `orcan plugins doctor --plugin git` reports bounded runtime
facts; it does not prove remote authentication or invoke an agent.
