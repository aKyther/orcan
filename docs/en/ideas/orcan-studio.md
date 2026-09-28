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

Studio saves reconnect profiles in its native application-data directory. A
profile contains a display name, transport metadata, and SSH metadata such as a
username or private-key path. Passwords and key passphrases are not written to
the profile file; they belong in the operating system credential vault.

The application is Rust + Tauri. The UI has no arbitrary shell permission: the
Rust connection layer owns three fixed process invocations and validates the
target identifier before starting one. SSH authentication and host verification
stay with OpenSSH and the user's `ssh-agent` and `known_hosts`.
