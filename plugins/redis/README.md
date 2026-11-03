# Redis / background executor

Run the local Redis broker, Celery executor and dashboard under Supervisor.

## Configuration and activation

Configuration: `orcan.config.json` → `plugins.redis`. The package's
`plugin.json` defines its fields, defaults, aliases and conflicts. Use
`orcan settings` to choose defaults; CLI flags override only one start.

Flags: `--with-redis`, `--with-executor`.

## Operating rules

Disabled by default. --with-redis and --with-executor select this package. Executor is a compatibility name. Workers, queue limits, timeouts and dashboard port belong to plugins.redis.

## Authentication and data

No models or agents start automatically. Session notifications require an explicit destination; completed results must be consumed and acknowledged.

## Lifecycle and diagnostics

`runtime.sh` owns this package's host hooks. The shared lifecycle resolves,
validates, prepares, starts, verifies and reports. Sourcing a package performs no
external actions. `orcan plugins doctor --plugin redis` reports bounded runtime
facts; it does not prove remote authentication or invoke an agent.
