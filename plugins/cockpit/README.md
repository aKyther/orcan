# Cockpit

Provide the installed workspace launcher over tmux.

## Configuration and activation

Configuration: `orcan.config.json` → `plugins.cockpit`. The package's
`plugin.json` defines its fields, defaults, aliases and conflicts. Use
`orcan settings` to choose defaults; CLI flags override only one start.

Flags: `orcan enter --launcher`.

## Operating rules

This is an interface entry, not a configurable startup capability. Use orcan enter --shell or --tmux for direct access.

## Authentication and data

No hosting credentials. Never infer readiness from availability alone.

## Lifecycle and diagnostics

`runtime.sh` owns this package's host hooks. The shared lifecycle resolves,
validates, prepares, starts, verifies and reports. Sourcing a package performs no
external actions. `orcan plugins doctor --plugin cockpit` reports bounded runtime
facts; it does not prove remote authentication or invoke an agent.
