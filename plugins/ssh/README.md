# SSH

Forward host ~/.ssh read-only and/or its existing SSH agent.

## Configuration and activation

Configuration: `orcan.config.json` → `plugins.ssh`. The package's
`plugin.json` defines its fields, defaults, aliases and conflicts. Use
`orcan settings` to choose defaults; CLI flags override only one start.

Flags: `--with-ssh`, `--ssh`, `--with-git`.

## Operating rules

Disabled by default. --with-git retains its historical SSH alias. Prepare mounts before stopping the container; verify the mount or agent after startup.

## Authentication and data

Host ~/.ssh and SSH_AUTH_SOCK. Never copy or read key contents.

## Lifecycle and diagnostics

`runtime.sh` owns this package's host hooks. The shared lifecycle resolves,
validates, prepares, starts, verifies and reports. Sourcing a package performs no
external actions. `orcan plugins doctor --plugin ssh` reports bounded runtime
facts; it does not prove remote authentication or invoke an agent.
