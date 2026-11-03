# Browser terminal

Expose the browser terminal and configure its appearance and host port.

## Configuration and activation

Configuration: `orcan.config.json` → `plugins.ttyd`. The package's
`plugin.json` defines its fields, defaults, aliases and conflicts. Use
`orcan settings` to choose defaults; CLI flags override only one start.

Flags: `--with-ttyd`, `--web-terminal`.

## Operating rules

Disabled by default. Existing web-terminal flags remain supported. `authentication: "basic"` requires a transient credential. Authentication is a terminal mode; credentials are transient and must be supplied again on resume.

## Authentication and data

TTYD_CREDENTIAL in the calling process or an explicit auth flag; never saved in a manifest.

## Lifecycle and diagnostics

`runtime.sh` owns this package's host hooks. The shared lifecycle resolves,
validates, prepares, starts, verifies and reports. Sourcing a package performs no
external actions. `orcan plugins doctor --plugin ttyd` reports bounded runtime
facts; it does not prove remote authentication or invoke an agent.
