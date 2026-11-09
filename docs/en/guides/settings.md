# Settings terminal UI

Run `orcan settings` to edit the existing `orcan.config.json` through a menu.
The UI keeps a draft until you review and explicitly save it. Credentials remain
in their host login tools or process environment.

## Sections

| Section | What it changes |
| --- | --- |
| Workspaces and projects | Opens the existing context manager; its changes use that manager's save flow |
| Optional services | Default activation and package-owned fields, grouped as access, services and interface |
| Agents and tools | Agent CLIs in `build.agents`, their versions, and optional Go/Rust toolchains |
| Resources | Docker image, timezone and container CPU/memory/process limits |
| Terminal layout | tmux windows, history and window prefix |
| Review and save | Changed settings and the commands needed to apply them |
| Reload configuration | Discard the draft and read the current JSON |

To open the workspace manager, first save or discard any settings draft. On
return, settings reloads the configuration so workspace edits are preserved.
A concurrent edit from another terminal prevents saving over it; reload before
continuing.

Disabled services show their enable switch first. Enable a service to edit its fields.
Open **Setup help and examples** for the full package guide and JSON examples.
The agents page also keeps tool descriptions and build guidance in a separate help view.
Escape returns from help to the settings you were editing; opening help never changes the draft.

## Keys

- Up/Down or `j`/`k`: select a row.
- Space: toggle a plugin, agent or toolchain.
- Enter: open a section or edit a field. On an enabled agent, edit its version.
- Escape: go back.
- `r`: review the draft.
- `s`: open review; press `s` again there and confirm to save.
- `q`: exit; a changed draft asks whether to discard it.

Version/source entries already in JSON are preserved when selecting other agents.
Changing a version validates it with the same rules as `orcan build --plan`.
Space toggles a toolchain; Enter edits its version (or source image for Go/Rust).
Select one or several project Python versions and use Enter to choose the default. Required agent runtimes are described in the build help and supplied by the base
image. Plugin rows show dependency/conflict rules; enabling a plugin also selects
its required plugins.
Agents here are CLI tools installed in the image. Their models and provider
settings remain in the tools themselves.

Saving changes only the JSON file. It does not build an image, acquire tokens,
start agents or recreate the container. The UI prints the next steps:

```bash
orcan sync         # keep your --no-chown / --chown-exclude policy
orcan build        # when image contents changed
orcan up --plan
orcan up
```

Finish active executor jobs before recreating their container. Existing startup
flags still override one launch. See [Startup plugins](plugins.md).

The sequential wizard remains available as `orcan settings --cli`. It retains
its tmux and plugin prompts for terminals where the full-screen UI is unsuitable.

## Preview startup

```bash
orcan up --plan
orcan up --plan --json
orcan up --plan --without github
```

The preview shows the configured image/agents, selected plugins, plugin ports,
managed/project/plugin mounts, external network and authentication that startup
will require. It also reports missing or stale generated configuration.

The plan performs no Docker operations, credential lookup or file generation. It
works before the configuration directory exists. Requested image contents come
from JSON; the installed image and current runtime are not inspected. Startup
still checks actual credentials, sockets, networks and Docker availability.
Persistent client/cache mounts follow `data_root` and are noted separately from
the listed managed/project/plugin mounts.

`--resume --plan` previews the saved plugin selection. It can report a required
terminal password without asking for it or revealing an argument supplied to
the preview. The normal resume command still requires transient authentication.

Plugin configuration help is maintained in each package's `plugin.json`.
Every plugin must supply setup guidance and JSON examples. Enter opens the
plugin detail page, including plugins without editable fields; Space toggles it.
Long help text wraps to the terminal width and scrolls with the page. Field hints
include choices/ranges, authentication preparation and the effect of each option.
The same content is available without Docker through
`orcan plugins help --plugin ssh` (or `github`, `gitlab`, `redis`, etc.). Startup
plan JSON includes the enabled plugins' help/examples; the text plan links to
these commands. Opening help never fetches tokens, reads keys or executes the
suggested setup commands.

`up` is start-only: it fails on missing/stale generated configuration or an
unavailable local image and names the explicit sync/build command to run.
It never performs ownership repair, automatic sync/build or an image pull.
Saved ownership exclusions continue to apply to explicit `sync` operations.

## Workspace list

Workspace groups start collapsed. Press Enter or Right to show their projects.
Use Up/Down and Enter to select **Add project to this workspace**, **Create a new
workspace**, **Show / hide full project paths**, or **Save changes**. These visible
actions work without knowing letter shortcuts.
Project names are shown first; press `v` to show or hide full paths in the workspace
list or project picker. The parent folder stays visible while picking projects.
Press Tab to review selected projects, then `b` to switch the highlighted Git project
between **mount as-is** and **worktree**. The review explains whether you will work
in the existing directory or create a separate working directory. Both modes and mixed selections remain available.
