# Startup plugins

Choose integrations once in `orcan settings`. Orcan groups them by purpose and
stores their activation and settings in the `plugins` section of
`orcan.config.json`. Then use:

```bash
orcan sync
orcan up
```

`up` uses the saved selection. After changing a running configuration, finish
active background work before recreating the container.

See [Settings TUI](settings.md) for keys, agent/image selection and the startup preview.

## Plugin list in settings

| Group | Packages | What you configure |
| --- | --- | --- |
| Access | `git`, `ssh`, `github`, `gitlab`, `docker`, `network` | Git identity defaults, SSH forwarding, hosting access, Docker socket or network |
| Services | `redis` | Background executor workers, queues, timeouts and dashboard port |
| Interface | `ttyd` | Browser terminal activation, ports, appearance and authentication mode |

The Git identity plugin starts enabled to preserve existing behavior. Other
startup plugins are disabled by default. Cockpit is listed as an installed
interface; it does not add a startup capability.

Settings lets you enable or disable each plugin and optionally edit its fields.
The final save is explicit. Workspaces have a separate manager entry; save or discard
your draft before opening it. Tokens and passwords
are not settings fields.

## One configuration file

```json
{
  "workspaces": [],
  "plugins": {
    "git": { "enabled": true },
    "ssh": { "enabled": false },
    "github": { "enabled": true, "hostname": "github.com" },
    "redis": { "enabled": true, "workers": 5, "max_running": 5 },
    "ttyd": { "enabled": false, "host_port": 17681 }
  }
}
```

`redis` includes the local broker, Celery executor and dashboard. `executor` is
accepted as a compatibility name. The `network` plugin requires an existing
network `name` and conflicts with the `docker` socket plugin.

For browser basic authentication, choose `plugins.ttyd.authentication: "basic"`
and supply `TTYD_CREDENTIAL` through the calling process, or use the existing
terminal auth flag. Orcan refuses startup before stopping the current container
if required credentials are unavailable.

## One-start overrides

Existing flags still work and select their owning package:

| Flag | Package |
| --- | --- |
| `--with-redis`, `--with-executor` | `redis` |
| `--with-docker`, `--docker-socket` | `docker` |
| `--with-ssh`, `--ssh`, `--with-git` | `ssh` |
| `--github`, `--with-github` | `github` |
| `--gitlab`, `--with-gitlab` | `gitlab` |
| `--network NAME`, `--with-network NAME` | `network` |
| `--web-terminal`, `--with-ttyd` | `ttyd` |
| `--web-terminal-auth USER:PASS`, `--with-ttyd-auth USER:PASS` | `ttyd`, transient auth mode |
| `--with-git-identity` | `git` |

Generic overrides use the same catalog:

```bash
orcan up --without github
orcan up --with redis
```

These do not rewrite JSON. Package defaults apply first, then saved configuration,
then explicit flags. Unknown plugins, unknown fields and incompatible selections
fail before container lifecycle changes.

`--with git` selects Git identity. The old hyphenated `--with-git` keeps its SSH
meaning for compatibility.

`orcan up --resume` uses the validated selection and settings from the last
successful start. It reacquires hosting authentication and never restores saved
passwords; an explicit terminal auth argument must be supplied again.

## Package rules and diagnostics

Every integration lives in `plugins/<id>/`, grouping:

- `plugin.json`: fields, defaults, aliases, flags, dependencies and conflicts;
- `runtime.sh`: preparation, verification and reporting hooks;
- `compose.yml`, when needed: static container additions;
- `README.md`: operating rules and authentication sources.

The shared lifecycle validates selection, prepares enabled plugins, starts the
container, verifies their runtime additions, then saves a secret-free launch
record. Disabled plugins do not acquire tokens or add mounts and ports. Only
bundled packages are loaded; user JSON cannot supply executable hook paths.

```bash
orcan plugins list
orcan plugins validate
orcan plugins doctor
orcan plugins doctor --plugin redis
```

Availability, activation and readiness are separate. Diagnostics do not attempt
remote authentication, invoke models or retry failed procedures.

## Existing configuration

Legacy top-level `executor`, `executor_port` and `ttyd` settings remain readable.
They configure values without enabling a plugin. Explicit `plugins` fields win.
A reviewed plugin save in `orcan settings` moves those values into the package
sections and removes the old sections. A normal `up` does not edit configuration.

Package descriptors also declare `image_requires` (components supplied by the
standard image) and `host_requires` (sockets, networks or authentication checked
at startup). `up --plan` explains them without acquiring credentials. Package
validation rejects unknown image requirements and cycles in plugin dependencies.
Required plugins run before their dependents. Settings enables transitive plugin
requirements together, refuses disabling a plugin still required by another,
and asks you to disable a conflicting selection explicitly. It never silently
removes access or services to resolve a conflict. CLI overrides validate the final
selection and report missing dependencies rather than persisting extra settings.

Each descriptor must include non-empty `help` and `examples` lists. `help` is
setup text; each `examples` entry is a JSON object encoded as text, normally a
configuration fragment. Field-level `help` is optional and explains that field.
Catalog validation rejects missing guidance or malformed examples. Settings,
`orcan plugins help --plugin NAME`, and startup plan JSON read this metadata
rather than maintaining separate setup instructions.
