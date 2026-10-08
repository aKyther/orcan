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

For a running Enclave using system SSH, each workspace offers **Open terminal**.
Studio opens its tmux session through SSH in Windows Terminal, PowerShell,
Command Prompt, macOS Terminal, or the default Linux terminal
(`x-terminal-emulator`). The terminal choice is remembered on this device.
Configure SSH host aliases and ports in `~/.ssh/config`. Profiles using Studio's
credential vault cannot launch this external terminal; select a system-SSH
profile for this action. Closing or detaching the terminal leaves tmux running.

For a system-SSH Enclave, Studio can open a selected workspace in the user's
native terminal application. It launches `ssh -tt HOST 'orcan attach WORKSPACE'`
so tmux keeps its normal keyboard shortcuts, clipboard, and scrollback. Studio
does not pass a saved password or private-key credential to another terminal
application; that action requires the user's system SSH agent/configuration.

Profiles are transport records, not proof that Orcan is already installed.
For a new SSH destination, Studio fetches the public host key before sign-in,
shows its algorithm and SHA-256 fingerprint, and saves it to the user's
OpenSSH-compatible `known_hosts` file only after explicit approval. A changed
key is blocked and never replaced automatically.
Studio can use the official online installer on a saved local, WSL2, or SSH
profile; it requires Internet access plus Bash, Git, and Python 3. For
isolated or on-premise hosts, Provisioning can build a minimal CLI kit in
a WSL2 source profile and stream it to an SSH destination. The remote
host needs no Internet access: it extracts the kit, installs the host CLI, and
verifies `orcan version`. The optional Docker image is streamed in the same
operation. Before transfer, Studio checks the WSL source and destination shell
for the required commands, including Docker only when an image is selected.
The offline CLI readiness result reports the destination user, Bash, tar,
Python 3, and permission to write to the user's home. When including an image,
it also verifies Docker access and requires its architecture to match the
destination. Each provisioning profile selector shows the destination address
and the user and sign-in method supplied by the selected profile or credential.
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

The connected-Enclave badge reports the target type, target user, exact Orcan
configuration path, and whether context changes are writable. Activity is
stored per Studio device and can be filtered by the Enclave that started each
operation; a failed Enclave check can be safely retried and an affected
Enclave can be reopened from its activity row. The Connection doctor in
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
The Enclave check reports Docker readiness after Orcan is available. New Enclave
is enabled only after that check reports a usable Docker daemon; on WSL this
means Docker Desktop integration or a Docker Engine must already be available
inside the selected distribution.
After provisioning, open its Enclave and use **Check Orcan** to read the
configuration path before changing context.

The Enclave map keeps projects directly under the managed sandbox root flat.
Only real child folders become groups, so `sandbox/STARE/*` and
`sandbox/NOWE/*` are easier to scan without adding a redundant `sandbox`
wrapper. On narrower windows the workspace and available-project columns flow
into one vertical view.
Selected workspace focus and map filters are remembered separately for each
Enclave on the Studio device.

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
Studio's UI calls the current Sandbox runtime an **Enclave** (an isolated Orcan
environment) and walks through Credentials & keys → Profiles → Enclaves; no
instance view is shown until a probe succeeds. Today one checked profile owns
at most one Enclave, so Studio excludes profiles that already report an
`orcan.config.json` from the New Enclave chooser.

Workspace membership is edited on the Enclave map: dragging a project onto a
workspace (or onto "New workspace") asks Orcan for a plan through
`orcan studio settings`, shows it for confirmation, applies it on that Enclave
(system SSH or native SSH with a saved credential), and then offers
`orcan sync`. Removing a project from a workspace never deletes files.

The application is Rust + Tauri. The UI has no arbitrary shell permission: the
Rust connection layer owns fixed commands and validates target identifiers.
Password and private-key profiles use native SSH and check the host key against
the local `known_hosts` file. Studio displays an unknown key's fingerprint and
records it only after explicit user approval; a changed key is rejected and
never replaced automatically. Their destination is direct `host` or
`host:port`; SSH-agent profiles continue to use system OpenSSH configuration.
