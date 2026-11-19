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

## Package ownership

`supervisor.sh` and `supervisor.py` select the programs in `supervisor.d/` using
the executor's validated settings. The shared launcher supplies log paths and
installs the selected programs; it has no Redis-specific service list.
`plugin.json` owns defaults, ranges and process variable names for both host and
executor settings. The executor wheel carries the same descriptor for standalone
use. `compose.yml` requires host-resolved settings and forwards every runtime
field, including log, artifact, completed-detail and worktree byte limits. Use
`orcan up`; invoking the overlay without resolved settings reports a missing value.
