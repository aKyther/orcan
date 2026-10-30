# Built-in Orcan plugins

Descriptors identify built-in capabilities; they are data, not executable hooks.
The host CLI owns lifecycle and configuration, tmux owns sessions, and the cockpit
is an optional interface over them. A descriptor names supported flags, runtime
requirements and a fixed verifier. `orcan plugins list` and `orcan plugins doctor`
show bounded results. Authentication is a ttyd mode, not a second terminal server.
External code installation and automatic agent invocation are not plugin discovery.

The `executor` plugin owns Celery tasks, compact reports and the dashboard. Redis
is its internal broker. Enable it with `--with-redis`; inspect it with
`orcan plugins doctor --plugin executor` and `orcan executor help`.

Explicit `--notify-codex-thread UUID` subscriptions allow the executor notification
controller to queue compact results in a local Codex session. Queued delivery and
explicit session consumption are separate states; this is not a generic agent launcher.
