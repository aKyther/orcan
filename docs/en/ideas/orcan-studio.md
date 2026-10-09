---
tags:
  - concept
---

# Orcan Studio

For the next development phases, see the
[Studio server and container roadmap](orcan-studio-roadmap.md). It separates host/container
management from possible future container groups and visual task flows.

## Servers and named containers

### Container identities

Open **Identities** to create a template with a name, description and Markdown
instructions. Describe an effective developer, a goal, or a review perspective
such as security or testing. These instructions supplement the general Orcan
`AGENTS.md` / `CLAUDE.md` rules and the repository's own instructions.

**Save new version** retains previous versions. In **Servers → New container**,
select a saved identity version or **Default — Orcan base rules** before planning
creation. Studio sends a copy of that version through the existing host
connection; no MCP or extra service is required. Container identity is fixed:
editing a template does not change existing containers. Every current and future
workspace receives the frozen instructions through its generated context pack.
Settings display the assigned version as locked. Ordinary sync refuses a changed
or removed assignment, including changing an existing Default container to a role.

The library lives beside the installed Studio application:
`studio-data/identities/<UUID>/versions/<version>/identity.json` stores metadata,
and `instructions.md` stores the text. Use **Open data directory** to inspect,
back up or remove templates. Keep this directory during app updates. Removing a
template leaves existing container snapshots intact; new creation using a removed
version fails explicitly. Profiles and credentials keep their existing storage.
The installation directory must be writable. Studio reports storage errors and
does not silently switch to another location. For AppImage, the library lives
beside the AppImage file; on macOS it lives beside the `.app` bundle.

Custom identity creation requires updated host CLI code and a newly built Orcan
image with identity support. Older images are rejected for custom identities;
Default remains available. Updating Studio alone does not update a running
container. Choose the new image when creating a new container. Another identity
requires explicit replacement, preserving projects and shared data.

### Manual enclaves

Open **Enclaves**, name a group and choose a server profile. **Check container
list** discovers its configured containers. **Register / add container** adds
an existing runtime and saves target UUIDs when needed. It does not create or
start the container. Repeat with other servers to assemble the group. A container
can belong to several enclaves; removing a card only removes that membership.

The canvas uses Vue Flow, with draggable cards, zoom controls and a minimap.
Connect handles to draw a visual line; double-click the line to remove it. Lines,
opening a group and saving its layout execute no agent work. **Save enclave**
writes `studio-data/enclaves/<UUID>.json` beside the application. The JSON contains
the name, revision, member UUIDs, connection profile references, positions and
visual lines. Credentials remain in their existing vault. Conflicting saves fail
explicitly; **Reload list** can reload the saved layout after discarding local edits.

Use **Check** on a card to verify the host and container UUIDs. Select a workspace
and use **Attach** to open its existing tmux context. **Start** only starts an
existing stopped runtime and verifies the result. Missing/offline containers and
changed UUIDs require explicit recovery; the card cannot recreate or silently
replace a container. Card state is the last check; each action checks again.
The side panel shows UUIDs, profile, assigned identity and the checked project path.

Native Attach uses the selected terminal setting: local Linux/macOS, WSL on
Windows, or system SSH on the desktop platform. SSH Attach requires a saved
system-SSH profile and an SSH agent/configuration usable by that terminal.
Studio never passes a saved password or private key to another app. Workspace
selection and UUID verification happen before attaching, including a second
check in the launched shell. Sign into and use the agent manually. Closing the
terminal leaves the container and persistent tmux session in place.

### Target UUIDs and replacement

Probe remains read-only. **Register UUIDs** in Servers or **Register / add
container** in Enclaves explicitly initializes IDs for an existing instance.
New Studio-created containers are registered during creation. The host installation
stores `studio-host.json` in its configuration root; `host_id` and `container_id`
are metadata in the instance's `orcan.config.json`. They do not change the role.
Renaming a Studio profile/group label and ordinary stop/start preserve these IDs.
IDs represent the logical instance configuration: restoring that same configuration
after Down keeps its ID, while explicit replacement allocates a new one.

The host record includes a machine fingerprint. A changed fingerprint blocks
enclave operations. On Linux this uses the machine ID; other hosts use their
hostname. Fully copied VMs can retain the same fingerprint and cannot always be
detected automatically. On a clone, explicitly run `orcan studio target clone
--yes`, then register each cloned instance with `--new-target --yes`. Existing
enclaves continue to refer to the original host/container IDs.

To change a named container's identity, first use **Down**. After checking its
state, **Prepare replacement** previews and confirms archiving the whole instance
directory under `<host-root>/retired/<name>-<old-UUID>`. Shared projects, cache and
agent data stay in place; workspace metadata and the old configuration remain in
the archive. The operation refuses a still-existing runtime, unavailable Docker,
or project data stored inside the instance directory. Then use **New container**
with the same name or a new name, select an identity and create it explicitly.
Context bindings from the archive are not imported automatically. Old enclave
cards fail their UUID check; remove them and add the replacement explicitly.
The legacy default instance is not retired through this action; create a named
replacement instead.

### Creating and managing containers

A profile connects to a **server/host**: local Linux/macOS, a WSL2 distribution,
or a remote VM. Provisioning installs the CLI and transfers a Docker image to
that host. It does not create one container per profile. After provisioning,
**Servers → New container** creates named instances from the installed image.
The image is reused; it is not transferred again for each container.

After **Check destination**, choose an installed image marked as Orcan from the
image list. No free-form image or project-root path is needed. Project roots
come from Orcan's reports for the host's configured instances; the default
sandbox is included. A different root changes the source catalog, not the
shared cache or agent data. Studio shows the reported cache and instance
workspace paths. The backend rechecks image/root choices before plan and apply.
The selected image and root are recorded in the new container configuration;
normal sync continues to preserve existing host overrides.

Studio remembers the selected container per profile on this device. Reopening
Studio still requires a fresh connection check before editing. A missing saved
container is not silently replaced by another container. Settings identify the
exact container and server, so actions cannot be confused with host provisioning.

Choose a name such as `developer` or `tester`; Docker names become
`orcan-developer` and `orcan-tester`. Use lowercase letters, digits and hyphens,
starting with a letter, up to 48 characters. Names are unique on the host.
The server card offers compact clickable container cards, with the last checked
state (or an explicit not-checked/stale label). Selecting one checks it before
management. Host capacity is separate from the selected container's configured
limits; it is not a count of free CPU or RAM. Context, settings, drafts, cached
reports and lifecycle actions are scoped to that selected container.
Studio discovers configured instances from Orcan, not a second desktop registry.

Set CPU and RAM limits in the creation form. Orcan supplies its defaults; the
user can override them before reviewing the plan. Studio reports Docker engine
CPU/RAM capacity and free disk space on the project filesystem. These are
read-only snapshots: total engine capacity is not free or reserved capacity,
and limits on separate containers do not reserve that amount of RAM in advance.
Refresh to update the facts. Each published browser terminal needs a different
host port; Studio rejects a port already published by a running Docker container.
An unrelated host process can still take that port after the check.

Named instances use separate configuration, generated mounts, workspace metadata,
launch options and Compose project names. **Sandbox, cache, agent directories,
history and dotfiles are shared through `ORCAN_DATA` on that host.** Worktree
storage is namespaced beneath the shared sandbox. A mount-as-is edit changes
the shared source seen by every container; use separate worktrees for isolated
changes. Shared agent directories are not a security boundary and concurrent
login/token refresh depends on the agent tool's own behavior.

The legacy default `orcan-1` and ordinary CLI commands keep their existing layout.
No existing configuration or data is migrated. For named instances:

Host worktree commands and Studio probes use
`<projects_root>/.worktrees/instances/<name>/` and its own `registry.json`.
The default instance retains `<projects_root>/.worktrees/` and skips the
`instances` namespace during prune. Even forced removal refuses another
instance's managed worktree. Branch names still belong to the shared Git
repository, so separate containers must use different checked-out branches.
New/recreated containers receive their instance namespace in the environment;
existing running containers are not updated automatically. Existing worktrees
are not moved: inspect legacy bindings before adopting the namespaced layout.

```bash
orcan --instance developer studio probe --json
orcan --instance developer sync
orcan --instance developer up --resume
orcan --instance developer down
orcan studio instances --json
```

Default named configuration lives under `~/.config/orcan/instances/NAME` (or
`$ORCAN_INSTANCES_ROOT/instances/NAME`). Shared data remains the base Orcan data
directory; `ORCAN_DATA` and `ORCAN_PROJECTS_ROOT` can select explicit host paths.
Down removes only the selected Compose stack, without deleting configuration,
shared data, projects or worktrees. Start recreates a removed container using
saved flags; protected ttyd recreation still needs its credentials on the host.
Existing-container Start/Stop/Restart preserve its settings and ttyd auth.

The current terms are **profile → server/host → container → workspace**.
A profile supplies the connection, a host owns images and shared data, and each
container owns its configuration and workspaces. An **enclave** is a separate
saved group of containers across one or more servers. Existing internal server
command and storage identifiers stay compatible.
Named containers do not implement an agent workflow engine.

Orcan Studio is the native desktop companion for composing and inspecting Orcan
context. Orcan Sandbox remains the runtime that owns Docker, managed project
roots, mounts, workspaces, and live reconcile.

Studio has three transport modes:

- **Local** on Linux and macOS: runs the installed `orcan` command.
- **WSL2** on Windows: runs `orcan` inside the chosen distribution through
  `wsl.exe`.
- **SSH**: runs the same versioned Orcan Studio protocol through the user's
  OpenSSH configuration.

For a running container using system SSH, each workspace offers **Open terminal**.
Studio opens its tmux session through SSH in Windows Terminal, PowerShell,
Command Prompt, macOS Terminal, or the default Linux terminal
(`x-terminal-emulator`). The terminal choice is remembered on this device.
Configure SSH host aliases and ports in `~/.ssh/config`. Profiles using Studio's
credential vault cannot launch this external terminal; select a system-SSH
profile for this action. Closing or detaching the terminal leaves tmux running.

For a system-SSH container, Studio can open a selected workspace in the user's
native terminal application. It launches `ssh -tt HOST 'orcan attach WORKSPACE'`
so tmux keeps its normal keyboard shortcuts, clipboard, and scrollback. Studio
does not pass a saved password or private-key credential to another terminal
application; that action requires the user's system SSH agent/configuration.

Profiles are transport records, not proof that Orcan is already installed.
For a new SSH destination, Studio fetches the public host key before sign-in,
shows its algorithm and SHA-256 fingerprint, and saves it to the user's
OpenSSH-compatible `known_hosts` file only after explicit approval. A changed
key is blocked and never replaced automatically.
Studio handles this for all SSH tests and operations, including provisioning.
Its own dialog shows the fingerprint and saves approval without opening a
terminal. System SSH aliases and their configured known-hosts location are
resolved with OpenSSH. A changed identity can be replaced after a separate
explicit approval in that dialog; Studio first rechecks the fingerprint and
backs up the previous known-hosts file using `ssh-keygen`.
Studio can use the official online installer on a saved local, WSL2, or SSH
profile; it requires Internet access plus Bash, Git, and Python 3. For
isolated or on-premise hosts, Provisioning can copy a minimal CLI kit between
local Linux/macOS, WSL2, and SSH profiles in either direction, including SSH
server to SSH server. Local Windows must use a WSL2 profile. Studio stores the
export in a private temporary file, then sends it to the destination; leave
enough disk space for the entire kit or image and keep Studio open. The file
is removed when the operation finishes or fails. Transfer files live in the
current user's Studio application cache, in a dedicated `transfers` directory
(mode `700` on Unix, user-cache permissions on Windows). At startup Studio
cleans recognized files left by a crashed transfer. Filesystem leases protect
active transfers, including those in another Studio instance. Cleanup never
sweeps the system temp directory or follows symlinks; unrecognized files remain.
Legacy anonymous temp files and remote shell temp directories are not swept.
During provisioning Studio shows checking, source export, destination transfer,
installation, and verification phases. Export reports bytes without an estimated
percentage; upload uses the finished payload's size and shows remaining bytes,
average throughput, and an estimated transfer time after the first two seconds.
The estimate excludes destination installation/verification and can change with
network speed. Sending all bytes is not
installation success: Studio waits for the destination and verifies the result.
Interrupted uploads show **Resume** and **Discard** in the status area, even
after navigating to another view. Keep Studio open: recovery currently works
only in the same application session. Resume uses the original profiles and
exported payload, verifies the destination's partial-file SHA-256, then sends
only missing bytes. Transfer speed excludes bytes already present. The whole
payload is verified before installation; installation failures can retry using
the uploaded file without exporting it again. Source export cannot resume.
Discard removes only this transfer's cached files and requires connection to
the destination. Successful transfers remove their local and remote payloads.
Remote partials are private (directory 700, file 600) and guarded by file locks;
recognized idle leftovers older than 24 hours are removed during a later
receiver operation. Closing Studio removes local session payloads; it does not
guarantee immediate deletion on an unreachable destination. Allow enough disk
space on both Studio and the destination for the complete exported archive.
Elapsed time stays visible while a kit is being prepared or Docker is importing
it. A compact status remains visible across views. Keep Studio open until the
operation finishes; source/destination controls stay locked during transfer.
Checking requirements cannot replace an active transfer's progress view, and
switching views does not cancel it. Confirmations use centered Studio dialogs
with Cancel focused by default; Escape cancels and destructive actions have
explicit labels. Profile cards offer an inline connection-only test and Edit.
Hosts need no Internet or
direct connection to each other. The destination extracts the kit, installs
the host CLI, and verifies `orcan version`. CLI installation and Docker-image
transfer have separate panels, requirements checks, and progress. CLI kits do
not include a Docker image and do not require destination Docker. Before each
transfer, Studio checks source and destination
for the required commands, including Docker only when an image is selected.
The offline CLI readiness result reports the destination user, Bash, tar,
Python 3, and permission to write to the user's home. The separate image check
verifies Docker access and requires its architecture to match the
destination. Each provisioning profile selector shows the destination address
and the user and sign-in method supplied by the selected profile or credential.
The image-only transfer also checks destination Docker access and architecture
before enabling transfer. It reports an existing CLI version and image ID;
identical images need no transfer. Updating CLI does not require uninstalling
it first. Image checks offer separate, confirmed actions to remove the Orcan
container or selected image. Images used by containers cannot be removed;
neither action deletes CLI, configuration, projects, or workspace data.
After installation Studio reads the CLI version and
verifies the selected image after a separate image transfer. Image transfer compares the
destination runtime configuration, ordered filesystem layers and platform with
the source. Docker engines can report different IDs for the same content, so ID
differences alone do not fail verification. Incomplete inspection or different
content still fails; mismatches show both IDs. If source content changes during
export, Studio stops before uploading. A verified result offers
**Go to Servers**; failed operations show a short recovery hint and expandable
technical detail.
Kits intentionally exclude profiles, configuration, projects,
sandbox data, and credentials. It requires a remote shell and `tar`; Docker is
required only when an image is included. SSH-agent profiles use system OpenSSH.
Profiles that use a Studio-managed password or private key use Studio's native
SSH transport for the same check, CLI-kit transfer, and Docker-image transfer,
with the saved `known_hosts` verification policy.

The Studio transport explicitly prepends `~/.local/bin` on WSL2 and SSH
commands, so a newly provisioned CLI works even before a non-interactive
remote shell has read its rc files. The installers also persist that path in
`~/.profile` and the active Bash or Zsh rc file for later human terminals.

The first protocol operation is `orcan studio probe --json`. It is read-only.
It is the authoritative Sandbox snapshot: Studio refreshes paths, configuration
revision, managed roots, workspaces, projects, mounts, and runtime state on
each reconnect instead of treating a cached desktop default as the truth.
Studio requires its declared `orcan-studio` protocol version before it offers
any future context-editing action. If an installed CLI predates that protocol,
Studio marks the saved destination as needing an update and offers the same
idempotent official installer in place; it does not transfer or replace
configuration, projects, sandbox data, profiles, or credentials.

The probe is a versioned control contract, not a file browser. Alongside the
snapshot, Orcan returns `control.operations` (whether an action is available
and why) and `control.settings` (a safe display value, `editable` or `locked`,
and an optional Studio action). Studio renders that contract; it never searches
for remote configuration files or assumes that a Docker change is live.

Studio edits context only when the probe reports the live `orcan.config.json`
as its source. A synced workspace index remains useful for inspection, but is
read-only: Studio disables rename, detach, and worktree actions until it can
reconnect to the Orcan instance that owns the configuration.

Each container has a configuration gear. Its panel separates the actions Studio
can safely operate (context plans and container lifecycle) from reported,
locked facts: container resources, image-provided agent tools, protected
environment values, managed paths, and launch exposure. Locked environment
values are intentionally neither displayed nor editable in Studio.

Each Git project in Contexts carries the state of its Orcan-reported parent.
Studio shows clean/dirty and ahead/behind inline, checks that parent's tracked
branch against `origin`, then requires confirmation before a `git pull
--ff-only`. Updating a parent never rewrites its dependent worktrees; their
branches can be rebased later by the user or an agent.

Sandbox is the corresponding inventory view. It lists only projects and
folders reported by Orcan below the managed projects root, rather than browsing
the host filesystem. A clean, eligible parent on `main` or `master` gets an
Update button; it previews the remote state and then runs the same confirmed
`git pull --ff-only` operation.

Repository import accepts a Git URL and an Orcan-reported parent directory
under the managed projects root. Orcan derives the new checkout name from the
URL and validates the destination; Studio never accepts an arbitrary path.
Git authentication remains on the Orcan host (for example its SSH agent), and
Studio reports its availability without reading keys or secrets.

The same compact import form can create a managed child folder after a preview.
Its name is portable across Windows, macOS, and Linux: it starts with a letter
or digit and may then use letters, digits, dots, underscores, or hyphens.
Orcan validates the planned `mkdir` destination under the selected parent.

Worktree creation only offers eligible Git parents, reports whether the source
branch is clean and up to date, and can run a confirmed `git pull --ff-only`
before creation. A new worktree starts in one selected workspace; it can be
attached to further workspaces from the relationship map.
Studio also reads the source's local branch names and displays a compact sample.
An existing name is valid: the plan says that the new worktree will check out
that branch instead of creating it again.

The connected-container badge reports the target type, target user, exact Orcan
configuration path, and whether context changes are writable. Activity is
stored per Studio device and can be filtered by the container that started each
operation; a failed container check can be safely retried and an affected
container can be reopened from its activity row. The Connection doctor in
Settings repeats the target, user, configuration path, and workspace-index
path, with reconnect and profile actions.

For a real SSH or WSL verification, open that saved profile in Studio and run
**Test connection**. It verifies only the selected transport, server identity,
and sign-in user; it does not call Orcan or Docker and changes nothing on the
destination. Its result describes common reachability, sign-in, WSL2, and
changed-server-identity failures in plain language, with the original technical
detail available on demand. Provisioning then has a separate requirements check for Bash,
cURL, Git, Python 3, and reachability of the official installer; it also
reports whether it found an existing Orcan CLI.
New container accepts any saved profile, including a host without Orcan. **Check
destination** separates connection, Orcan CLI, Docker and the required image.
Missing components offer targeted CLI installation/update or image transfer;
the provisioning result returns to the selected destination's setup. Docker
Desktop integration or Docker Engine must already be ready inside the selected
WSL distribution; setup does not silently install Docker.
Access options and creation are enabled only after readiness checks succeed.
Preview the actual Orcan plan, then confirm creation; changing options invalidates
the plan. The backend checks again for the selected name's existing configuration or container
and a usable local image. It does not build an image on an offline destination.
After creation, Studio verifies the running container and opens Contexts.

Server cards show the selected container's state/name, image, configured CPU/RAM, source and
worktree paths, workspace count and access exposure. Settings remain behind the
gear, with locked creation-time values and change-impact explanations. A cached
or failed report is history, not authority to unlock operations; the current
session needs a successful probe before opening a runtime for changes.

For an existing container, Start, Stop and Restart use Docker's matching action.
Restart is a real restart, not a possibly unchanged Compose `up`. These actions
preserve container mounts, resources, environment and protected ttyd settings;
Stop does not remove the container. If the container was removed, Start uses
`orcan up --resume` only when saved options and the image are available. Removed
containers with protected ttyd require supplying credentials on the host to
recreate them. Studio checks resulting state before recording success.
Ordinary restart does not apply new creation-time settings: new mounts,
environment, resources or agent images may require explicit recreation.

The container map keeps projects directly under the managed sandbox root flat.
Only real child folders become groups, so `sandbox/STARE/*` and
`sandbox/NOWE/*` are easier to scan without adding a redundant `sandbox`
wrapper. On narrower windows the workspace and available-project columns flow
into one vertical view.
Selected workspace focus and map filters are remembered separately for each
container on the Studio device.

Studio saves reconnect profiles in its native application-data directory. A
profile contains a display name and transport metadata; system-SSH profiles may
optionally state their SSH user. Passwords and key passphrases are not written
to the profile file; they belong in the operating system credential vault.

Credentials are separate, reusable, immutable records: a named password or
private-key path together with its SSH user. Studio offers distinct creation
flows for password and key credentials; changing any of those values means
creating a replacement, moving profiles to it, and deleting the unused old
record. A profile chooses exactly one sign-in method: system SSH or one
credential. It cannot override the credential user, and a credential cannot be
deleted while a profile uses it.

Studio keeps reconnect metadata in a versioned JSON document in its per-user
application-data directory. Secrets are deliberately absent from that file and
remain in the platform credential vault; a hash cannot replace a password here
because native SSH must retrieve the password to authenticate. The installation
directory is intentionally not used: it is commonly read-only or shared on
Windows, macOS, and packaged Linux installations.
Studio walks through Credentials & keys → Profiles → Provisioning → Servers
and named containers. Context editing is enabled only after a successful probe
for the selected container. An existing configuration/container reserves that
name, not the whole profile: choose a different name to create another instance.

Workspace membership is edited on the container map: dragging a project onto a
workspace (or onto "New workspace") asks Orcan for a plan through
`orcan studio settings`, shows it for confirmation, applies it on that container
(system SSH or native SSH with a saved credential), and then offers
`orcan sync`. Removing a project from a workspace never deletes files.

The application is Rust + Tauri. The UI has no arbitrary shell permission: the
Rust connection layer owns fixed commands and validates target identifiers.
Password and private-key profiles use native SSH and check the host key against
the local `known_hosts` file. Studio displays an unknown key's fingerprint and
records it only after explicit user approval; a changed key is rejected and
never replaced automatically. Their destination is direct `host` or
`host:port`; SSH-agent profiles continue to use system OpenSSH configuration.

### Optional Git / SSH access provisioning

The Provisioning screen can copy one explicitly selected OpenSSH key pair between
source and destination profiles independently of CLI/image installation. Both
endpoints need Python 3 and OpenSSH; Orcan itself is not required. Windows users
can select their WSL profile as the source. Native Windows endpoints are not
supported by this POSIX helper.

Studio lists names and public fingerprints, then requires approval before copying
the private key. A separate key for the destination is safer: copying grants that
machine the source identity's permissions. Encrypted OpenSSH keys retain their
passphrase; hardware-backed and legacy PEM keys are not transferable here.

Only the selected pair is transferred through native process memory and stdin,
never through the webview, CLI/image archive, temporary archive or resume cache.
The destination uses the profile user's home, with `.ssh` mode 700 and new files
mode 600. Existing keys are never overwritten: choose another name or skip.
Source `config`, `known_hosts` and SSH multiplexing sockets are not copied.

The optional host-specific configuration toggle adds an Include while preserving
existing configuration bytes. With it off, existing SSH configuration is untouched
and a standalone test configuration is created. Test Git access checks
authentication without fetching or changing repositories. Unknown Git host keys
require fingerprint approval; changed/revoked entries are not replaced. Verify
fingerprints independently: key scanning alone does not authenticate a host.
Encrypted keys need unlocking on the destination. Containers started with
`--with-git` expose the host SSH directory read-only.
