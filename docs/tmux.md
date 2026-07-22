# tmux inside ttyd

cind runs **ttyd → cursor-launcher (workspaces) → cursor-tmux-workspace-attach → tmux**.

- **Launcher (main page):** pick a workspace by number — phone-friendly, one tap from Android.
- **Inside tmux:** normal tabs — workspace root, one tab per project, or multiple tabs when `windows[]` is set.

Configuration lives under `/etc/tmux/` (symlinked from `~/.config/tmux/`). Your `~/.tmux.conf` only sources the system config.

## Session flow

1. Open `http://localhost:7681` (`make terminal`).
2. Pick a **workspace** from the launcher menu (phone-friendly numbers).
3. `cursor-tmux-workspace-attach` attaches to that workspace session or creates it with tabs from config.
4. Use tmux normally: switch tabs (`prefix n` / `p` / `1`–`9`), split panes, detach, reattach.

Each workspace = **one tmux session**. Projects = **tabs** inside that session.

## Workspace tabs

Default layout per workspace session:

| Tab | Meaning |
| --- | --- |
| **🖥 workspace** | Workspace root (agent starts here) |
| **🐍 backend** | One tab per `projects[]` entry (icon from project `name`) |

## Project windows (`windows[]`)

Define extra tabs **inside a project** in `cind.config.json`:

```json
{
  "workspaces": [{
    "name": "sejs",
    "tmux": "sejs",
    "projects": [{
      "name": "backend",
      "path": "/path/to/backend",
      "windows": [
        {"name": "editor", "icon": "📝", "dir": "."},
        {"name": "server", "icon": "🐍", "dir": ".", "command": "make run"},
        {"name": "logs", "icon": "⚙", "dir": "."}
      ]
    }]
  }]
}
```

Tab titles look like **🐍 backend · 📝 editor**. Without `windows[]`, the project gets a single tab (**🐍 backend**).

| Field | Meaning |
| --- | --- |
| `name` | Window label (without icon) |
| `icon` | Optional unicode prefix shown in the tab bar |
| `dir` | Working directory relative to project root (or absolute) |
| `command` | Optional command sent after the window opens |

After editing config: `make env`, then `make down && make terminal-docker`, and start a **new** tmux session (kill old session or pick workspace fresh).

Legacy per-project sessions (`cursor-tmux-attach`) still exist for single-repo setups without workspaces.

## Status bar

| Segment | Content |
| --- | --- |
| Left | Prefix indicator (◉/○), project name, session name |
| Right | Git branch, hostname, cwd, CPU load, memory %, battery (if present), time |

Scripts run every 5 seconds and stay lightweight (no `top`, no OSC sequences).

## Prefix

**Prefix key:** `Ctrl+Space`

Press prefix once, then the shortcut key. While prefix is active, the status bar shows **◉** instead of **○**.

## Keybindings

All shortcuts use prefix **`Ctrl+Space`** unless noted.

### General

| Key | Action |
| --- | --- |
| `Ctrl+Space` `r` | Reload tmux config |
| `Ctrl+Space` `[` | Enter copy mode (vi keys) |
| `Ctrl+Space` `P` | Copy current pane path to tmux buffer |
| `Ctrl+Space` `]` | Paste tmux buffer (default tmux binding) |
| `Ctrl+Space` `I` | Show session / project info message |
| `Ctrl+Space` `s` | Switch session (fzf popup, or prompt fallback) |

### Panes

| Key | Action |
| --- | --- |
| `Ctrl+Space` `\|` | Split pane vertically (current directory) |
| `Ctrl+Space` `-` | Split pane horizontally (current directory) |
| `Ctrl+Space` `h` `j` `k` `l` | Move between panes (left/down/up/right) |
| `Ctrl+Space` `H` `J` `K` `L` | Resize pane (repeatable) |
| `Ctrl+Space` `z` | Zoom / unzoom pane |
| `Ctrl+Space` `O` | Swap pane with previous |
| `Ctrl+Space` `R` | Rotate panes in window |
| `Ctrl+Space` `y` | Toggle synchronized panes |
| `Ctrl+Space` `x` | Kill pane |

### Windows

| Key | Action |
| --- | --- |
| `Ctrl+Space` `c` | New window (current directory) |
| `Ctrl+Space` `C` | New window (current directory) |
| `Ctrl+Space` `n` | Next window |
| `Ctrl+Space` `p` | Previous window |
| `Ctrl+Space` `1`–`9` | Jump to window by index |
| `Ctrl+Space` `0` | Jump to last window |
| `Ctrl+Space` `X` | Kill window (confirm) |

### Copy mode (vi)

| Key | Action |
| --- | --- |
| `v` | Begin selection |
| `y` | Copy selection and exit |
| `Enter` | Copy selection and exit |
| `r` | Rectangle toggle |

Copy stays in the tmux buffer (ttyd has no desktop clipboard integration).

### Mouse (ttyd / phone)

| Action | Effect |
| --- | --- |
| Click pane | Focus pane |
| Drag border | Resize pane |
| Scroll | Scroll history |
| Click window name | Switch window |
| Double-click pane | Zoom pane (tmux default) |

### Alt bindings (desktop browsers only)

| Key | Action |
| --- | --- |
| `Alt+Enter` | Zoom pane |
| `Alt+↑` `↓` `←` `→` | Move between panes |

On phones, use the launcher menu and mouse instead of Alt/Ctrl shortcuts.

## File layout

```
/etc/tmux/
  tmux.conf           # entry point
  options.conf        # behaviour, mouse, vi mode
  keybindings.conf    # all custom binds
  status.conf         # status bar
  scripts/
    status-left.sh
    status-right.sh
    window-name.sh
    copy-path.sh
    session-switch.sh

/usr/local/bin/
  cursor-tmux-workspace-attach  # workspace session bootstrap + attach
  cursor-tmux-attach            # legacy single-project sessions
  cursor-launcher                 # ttyd workspace menu
```

## Migration notes

### From the old single-file `~/.tmux.conf`

1. Rebuild the image: `make rebuild`
2. Replace your home config (or merge manually):

   ```bash
   cp /etc/skel/.tmux.conf ~/.tmux.conf
   ln -sfn /etc/tmux ~/.config/tmux
   ```

3. Regenerate runtime config if you use JSON projects:

   ```bash
   make env CONFIG=./cind.config.json
   ```

4. Existing tmux sessions keep their layout; new sessions pick up windows from config.

### Custom binds

Add personal overrides to `~/.tmux.conf` **after** the source line:

```tmux
source-file /etc/tmux/tmux.conf
bind Q kill-session
```

### ttyd limitations

- No Kitty/WezTerm/iTerm features.
- No reliable desktop clipboard (use tmux buffer + `prefix ]`).
- Alt/Ctrl may be awkward on mobile — use the launcher and mouse.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Wrong session attached | Use launcher numbers; each project maps to `projects[].tmux` |
| Status bar empty / slow | Check `/etc/tmux/scripts/*.sh` are executable |
| Colors look wrong | Ensure `TERM=tmux-256color` (set automatically) |
| Config changes ignored | `prefix r` or restart tmux session |
| fzf session switch fails | Falls back to name prompt; upgrade tmux for popup support |

See also: [Project launcher](launcher.md), [JSON config](config.md).
