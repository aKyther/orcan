# Settings terminal UI

Run `orcan settings` to edit the existing `orcan.config.json` through a menu.
The UI keeps a draft until you review and explicitly save it. Credentials remain
in their host login tools or process environment.

## Sections

| Section | What it changes |
| --- | --- |
| Workspaces and projects | Opens the existing context manager; its changes use that manager's save flow |
| Startup plugins | Default activation and package-owned fields, grouped as access, services and interface |
| Agents and image | Agent CLIs in `build.agents`, their versions, and optional Go/Rust toolchains |
| Container | Docker image, timezone and container CPU/memory/process limits |
| Terminal layout | tmux windows, history and window prefix |
| Review and save | Changed settings and the commands needed to apply them |
| Reload configuration | Discard the draft and read the current JSON |

To open the workspace manager, first save or discard any settings draft. On
return, settings reloads the configuration so workspace edits are preserved.
A concurrent edit from another terminal prevents saving over it; reload before
continuing.

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
Agents here are CLI tools installed in the image. Their models and provider
settings remain in the tools themselves.

Saving changes only the JSON file. It does not build an image, acquire tokens,
start agents or recreate the container. The UI prints the next steps:

```bash
orcan sync
orcan build       # when image contents changed
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
