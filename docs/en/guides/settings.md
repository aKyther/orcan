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

## Workspace editor

Open **Workspaces and projects** to edit workspace drafts. Choose **Create workspace**,
enter a name, then choose **Add projects**. Open directories with Enter or Right, and return with Left or the visible
**.. Return to parent folder** row. Space marks or unmarks a directory as a
project; it does not open it. The **Selected projects** section lists choices
from every folder. Choose **Add selected projects** to return them to the draft.
Folder changes preserve selections and show a short action message. Use **Choose another folder**
to browse elsewhere without losing your selection.

Each project starts as **mount as-is**: work directly in its existing directory.
Select a project to edit its name or choose **worktree**, then enter a branch for
that project. Modes and branches are independent: one workspace can mix mounts
and several worktrees on different branches. Existing checkouts stay in place;
to create a different worktree, add its source repository as a new project.

The editor shows workspace name, projects, summary and actions from top to bottom,
with light section dividers and spacing. Dividers never receive keyboard focus.
Use Up/Down and Enter throughout; letter shortcuts and the help screen are not
needed. Escape returns to the workspace list and keeps the draft in memory.
**Close / discard draft** asks before discarding unsaved changes.

**Save changes** applies all workspace drafts together. It validates names, paths,
branches and configuration revision before creating worktrees and saving JSON.
An empty workspace can also be saved. Changes to other configuration sections are
preserved. Save does not run sync; run `orcan sync` separately afterwards.

Removing a workspace removes all its project entries. Existing mount directories
remain on disk. Managed worktree directory removal is a separate explicit choice,
performed only on save; local changes block removal. If worktree creation fails
partway through save, created directories remain and are reused on retry. Review
the error before discarding the draft: discarding cannot undo already executed
filesystem operations from an attempted save.
