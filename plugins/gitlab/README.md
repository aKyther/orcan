# GitLab

Provide authentication for the selected GitLab hostname.

## Configuration and activation

Configuration: `orcan.config.json` → `plugins.gitlab`. The package's
`plugin.json` defines its fields, defaults, aliases and conflicts. Use
`orcan settings` to choose defaults; CLI flags override only one start.

Flags: `--gitlab`, `--with-gitlab`.

## Operating rules

Disabled by default. Resolve authentication before lifecycle changes and clear alternative token variables in the container.

## Authentication and data

Matching process token, then glab login for exactly the selected hostname. No token is saved.

## Lifecycle and diagnostics

`runtime.sh` owns this package's host hooks. The shared lifecycle resolves,
validates, prepares, starts, verifies and reports. Sourcing a package performs no
external actions. `orcan plugins doctor --plugin gitlab` reports bounded runtime
facts; it does not prove remote authentication or invoke an agent.
