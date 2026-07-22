# Virtual workspace architecture

A **workspace** is the primary unit in cind: one directory under `/home/developer/workspaces/<name>`, one tmux session, one or more mounted repos.

## Model

```text
Host (cind repo, automatic)              Container (always)
──────────────────────────────────    ─────────────────────────────────────
.cind/workspaces/              →    /home/developer/workspaces/
  gotibooks/                              gotibooks/
    .cursor/rules/                          .cursor/rules/
    backend/  → symlink                     backend/   → /home/you/.../backend (parity)
    frontend/                               frontend/  → /home/you/.../frontend (parity)
  other/                                  other/
```

One Compose bind mounts the whole `.cind/workspaces/` tree (not one bind per workspace). Each workspace is a subdirectory — project symlinks stay only under that subdirectory.

| Concept | Path / meaning |
| --- | --- |
| Workspace (session) | tmux session name = `workspaces[].name` |
| Workspace root | Always `/home/developer/workspaces/<name>` in the container |
| Host persistence | Auto: `<cind-repo>/.cind/workspaces/<name>/` (not in JSON) |
| `projects[]` | Path parity mount + symlink as subdirectory under workspace root |
| tmux tabs | `tab-1`, `tab-2`, `tab-3` (shells in the same workspace; configurable) |

You do **not** set container paths in JSON — cind handles parity mounts and symlinks.

## Path parity + symlinks

Every `projects[].path` is bind-mounted at the **same absolute path** on host and in the container. That keeps `docker compose` bind mounts working when you use the host Docker socket.

Under the workspace root, `init-workspace` creates symlinks:

```text
/home/developer/workspaces/gotibooks/backend → /home/you/gotibooks/backend
```

Agents start in the workspace root and `cd` into project subdirectories.

## One tmux session per workspace

- ttyd launcher lists **workspaces**.
- Choosing a workspace attaches **one** tmux session.
- Default layout: **three tabs** — `tab-1`, `tab-2`, `tab-3` (all in this workspace root). These are **not** other workspaces. Rename or add windows with normal tmux commands.
- Second workspace = second **tmux session** (launcher → pick again after detach, or `prefix s` / `prefix w`).
- Project repos appear as subdirectories under the workspace root (symlinks).
- Agent and shell start in the **workspace root**; projects are subdirectories.

## Configuration

```json
{
  "workspaces": [
    {
      "name": "gotibooks",
      "projects": [
        {"name": "backend", "path": "/home/you/gotibooks/backend"},
        {"name": "frontend", "path": "/home/you/gotibooks/frontend"}
      ]
    }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `name` | Workspace id — directory under `/home/developer/workspaces/` and tmux session name |
| `projects[].name` | Symlink name under workspace root |
| `projects[].path` | Host absolute path (parity mount) |

No `alias`, no `default_project`, no `default_workspace`, no `mount_mode`, no per-workspace `tmux`.

## Workspace-level Cursor rules

On the host, edit `<cind-repo>/.cind/workspaces/<name>/.cursor/rules/` (created by `make env`). Inside the container the same files appear under `/home/developer/workspaces/<name>/.cursor/rules/`.

## Agents

On container start, `init-workspace` writes at the workspace root:

| File | Role |
| --- | --- |
| `.manifest.json` | Machine-readable projects / paths |
| `AGENTS.md` | Agent instructions (regenerated each start) |
| `CLAUDE.md` | Same content for Claude Code |
| `.cursorignore` | Cursor agent exclusions (missing-only) |
| `.cursorindexingignore` | Cursor index exclusions (missing-only) |
| `.claudeignore` | Claude discovery exclusions (missing-only) |
| `.claude/settings.json` | Claude `permissions.deny` for secrets (missing-only) |
| `.cursor/rules/workspace-context.mdc` | Cursor rule seed (missing-only) |
| `README.workspace.md` | Short human map |

Agents should read **`AGENTS.md` → `.manifest.json` → project `AGENTS.md`**.

Ignore files at the workspace root help when the agent starts there. They do **not** rewrite files inside each project checkout (cind does not auto-modify mounted repos). For per-repo `.env` protection, run `cursor-init-project` inside that project (or `make init-project` from the host for the primary `PROJECT_DIR`).

Global layers: Cursor `~/.cursor/cli-config.json` deny rules; Claude `~/.claude/settings.json` deny rules (seeded additively by `init-ai-statusline`).

Do not treat workspace root as a git root.

Custom lasting rules: edit `.cursor/rules/` under `<cind-repo>/.cind/workspaces/<name>/` (not the generated `AGENTS.md`). Customize ignore files in the same tree — they are missing-only and will not be overwritten on restart.

See also: [Path parity](../path-parity.md), [Cursor](../cursor.md#what-belongs-in-the-mounted-project).
