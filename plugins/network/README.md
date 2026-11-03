# Docker network

Join one existing external Docker network.

## Configuration and activation

Configuration: `orcan.config.json` → `plugins.network`. The package's
`plugin.json` defines its fields, defaults, aliases and conflicts. Use
`orcan settings` to choose defaults; CLI flags override only one start.

Flags: `--with-network`, `--network`.

## Operating rules

Disabled by default; conflicts with the Docker socket plugin. An enabled plugin requires a network name and an existing network. Verify attachment after startup.

## Authentication and data

No credentials. Network creation is an explicit user operation.

## Lifecycle and diagnostics

`runtime.sh` owns this package's host hooks. The shared lifecycle resolves,
validates, prepares, starts, verifies and reports. Sourcing a package performs no
external actions. `orcan plugins doctor --plugin network` reports bounded runtime
facts; it does not prove remote authentication or invoke an agent.
