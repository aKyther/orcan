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

The first protocol operation is `orcan studio probe --json`. It is read-only.
It is the authoritative Sandbox snapshot: Studio refreshes paths, configuration
revision, managed roots, workspaces, projects, mounts, and runtime state on
each reconnect instead of treating a cached desktop default as the truth.
Studio requires its declared `orcan-studio` protocol version before it offers
any future context-editing action.

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

Studio saves reconnect profiles in its native application-data directory. A
profile contains a display name, transport metadata, and SSH metadata such as a
username or private-key path. Passwords and key passphrases are not written to
the profile file; they belong in the operating system credential vault.

Credentials are separate, reusable records: a named private-key path or
password that several profiles can reference, while each profile keeps its own
address and username. A credential cannot be deleted while a profile uses it.
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
