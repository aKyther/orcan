# Docker socket

Mount the host Docker socket.

## Configuration and activation

Configuration: `orcan.config.json` → `plugins.docker`. The package's
`plugin.json` defines its fields, defaults, aliases and conflicts. Use
`orcan settings` to choose defaults; CLI flags override only one start.

Flags: `--with-docker`, `--docker-socket`.

## Operating rules

Disabled by default; conflicts with the network plugin. Check the socket before stopping the current container and verify it after launch.

## Authentication and data

No stored credentials; the socket grants control of the host Docker engine.

## Lifecycle and diagnostics

`runtime.sh` owns this package's host hooks. The shared lifecycle resolves,
validates, prepares, starts, verifies and reports. Sourcing a package performs no
external actions. `orcan plugins doctor --plugin docker` reports bounded runtime
facts; it does not prove remote authentication or invoke an agent.
