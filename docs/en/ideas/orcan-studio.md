---
tags:
  - concept
---

# Orcan Studio

Orcan Studio is the native desktop companion for composing and inspecting Orcan
context. Orcan Sandbox remains the runtime that owns Docker, managed project
roots, mounts, workspaces, and live reconcile.

Studio has three transport modes:

- **Local** on Linux and macOS: runs the installed `orcan` command.
- **WSL2** on Windows: runs `orcan` inside the chosen distribution through
  `wsl.exe`.
- **SSH**: runs the same versioned Orcan Studio protocol through the user's
  OpenSSH configuration.

Profiles are transport records, not proof that Orcan is already installed.
Studio can use the official online installer on a saved local, WSL2, or SSH
profile; it requires Internet access plus Bash, Git, and Python 3. For
isolated or on-premise hosts, Provisioning can build a minimal CLI kit in
a WSL2 source profile and stream it to a system-SSH destination. The remote
host needs no Internet access: it extracts the kit, installs the host CLI, and
verifies `orcan version`. The optional Docker image is streamed in the same
operation. Before transfer, Studio checks the WSL source and destination shell
for the required commands, including Docker only when an image is selected.
Kits intentionally exclude profiles, configuration, projects,
sandbox data, and credentials. It requires a remote shell and `tar`; Docker is
required only when an image is included. SSH-agent profiles use system OpenSSH.
Profiles that use a Studio-managed password or private key use Studio's native
SSH transport for the same check and transfer, with the saved `known_hosts`
verification policy.

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

Each Enclave has a configuration gear. Its panel separates the actions Studio
can safely operate (context plans and container lifecycle) from reported,
locked facts: container resources, image-provided agent tools, protected
environment values, managed paths, and launch exposure. Locked environment
values are intentionally neither displayed nor editable in Studio.

Each Git project in Contexts carries the state of its Orcan-reported parent.
Studio shows clean/dirty and ahead/behind inline, checks that parent's tracked
branch against `origin`, then requires confirmation before a `git pull
--ff-only`. Updating a parent never rewrites its dependent worktrees; their
branches can be rebased later by the user or an agent.

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

The connected-Enclave badge reports the target type, target user, exact Orcan
configuration path, and whether context changes are writable. Activity is
stored per Studio device and can be filtered by the Enclave that started each
operation; a failed Enclave check can be safely retried and an affected
Enclave can be reopened from its activity row. The Connection doctor in
Settings repeats the target, user, configuration path, and workspace-index
path, with reconnect and profile actions.

For a real SSH or WSL verification, open that saved profile in Studio, run
**Check Orcan**, and confirm that Connection doctor reports the intended target user and
configuration path before changing context.

The Enclave map keeps projects directly under the managed sandbox root flat.
Only real child folders become groups, so `sandbox/STARE/*` and
`sandbox/NOWE/*` are easier to scan without adding a redundant `sandbox`
wrapper. On narrower windows the workspace and available-project columns flow
into one vertical view.
Selected workspace focus and map filters are remembered separately for each
Enclave on the Studio device.

Studio saves reconnect profiles in its native application-data directory. A
profile contains a display name, transport metadata, and an optional SSH user
override. Passwords and key passphrases are not written to
the profile file; they belong in the operating system credential vault.

Credentials are separate, reusable records: a named private-key path or
password, together with its usual remote username, that several profiles can
reference. A profile can override that user for an exceptional target. A
credential cannot be deleted while a profile uses it.
Studio's UI calls each connected Sandbox an **Enclave** (an isolated Orcan
environment) and walks through Credentials & keys → Profiles → Enclaves; no
instance view is shown until a probe succeeds.

Workspace membership is edited on the Enclave map: dragging a project onto a
workspace (or onto "New workspace") asks Orcan for a plan through
`orcan studio settings`, shows it for confirmation, applies it on that Enclave
(system SSH or native SSH with a saved credential), and then offers
`orcan sync`. Removing a project from a workspace never deletes files.

The application is Rust + Tauri. The UI has no arbitrary shell permission: the
Rust connection layer owns fixed commands and validates target identifiers.
Password and private-key profiles use native SSH and check the host key against
the local `known_hosts` file. An unknown or changed key is rejected; Studio
never trusts it automatically. Their destination is direct `host` or
`host:port`; SSH-agent profiles continue to use system OpenSSH configuration.
