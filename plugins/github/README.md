# GitHub

Provide authentication for the selected GitHub hostname.

## Configuration and activation

Configuration: `orcan.config.json` → `plugins.github`. The package's
`plugin.json` defines its fields, defaults, aliases and conflicts. Use
`orcan settings` to choose defaults; CLI flags override only one start.

Flags: `--github`, `--with-github`.

## Operating rules

Disabled by default. Validate hostname, resolve authentication before stopping the current container, and generate an overlay containing variable references only.

## Authentication and data

Matching process token, then gh auth token for exactly the selected hostname. No token is saved to JSON or logs.

## Lifecycle and diagnostics

`runtime.sh` owns this package's host hooks. The shared lifecycle resolves,
validates, prepares, starts, verifies and reports. Sourcing a package performs no
external actions. `orcan plugins doctor --plugin github` reports bounded runtime
facts; it does not prove remote authentication or invoke an agent.
