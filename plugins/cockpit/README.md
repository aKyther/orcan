# Cockpit

The built-in terminal interface over tmux. Its application code and Python
dependencies live in `cockpit/`; this package describes the installed interface.

## Configuration and activation

Cockpit is an interface entry, not an optional startup service. The catalog marks
it as enabled and non-configurable; it has no plugin-specific fields or ports.
Use `orcan enter` or `orcan enter --launcher` to open it. Use `orcan enter --shell`
or `orcan enter --tmux` for direct access. Set initial windows and terminal layout
through Orcan's tmux settings.

## Operating rules

Cockpit manages workspace selection, terminal rendering and tmux interaction.
Its Tasks panel reads bounded JSON from `orcan-executor pulse` and `overview`.
The executor owns queue state, worktrees, reports, retention and notifications.
Opening the Tasks panel does not start a job or acknowledge a result.

## Authentication and data

No hosting credentials belong to this package. Cockpit does not select models or
start an agent merely because the interface or executor is available.

## Lifecycle and diagnostics

`runtime.sh` intentionally has no hooks: this package adds no background service,
Compose overlay or Supervisor program. `orcan plugins doctor --plugin cockpit`
checks interface availability; it does not prove executor readiness or remote
authentication. Check the executor separately with `orcan executor doctor`.
