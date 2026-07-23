# tmux inside ttyd

cind tmux is tuned for **browser ttyd**: IDE-like top tabs, per-pane footers, thin global status. Config lives in `/etc/tmux/`; `~/.tmux.conf` in the container only sources it.

**Flow:** ttyd → workspace launcher (pick **session**) → tmux.

## Sessions vs tabs

| Layer | Meaning |
| --- | --- |
| **tmux session** | One cind workspace (`cind.config.json`) |
| **tmux window** (top tabs) | Shells / tools inside that workspace (`tab-1` … or renamed) |
| **tmux pane** | Split inside a window; footer shows command + directory |

Switch **workspace (session):** launcher after detach, or `Ctrl+Space` `s` / `w`.  
Switch **window (tab):** `Alt+1`…`9`, mouse click on top bar, or `Ctrl+Space` `W`.

Rename a tab: `Ctrl+Space` `,`. New window: `Alt+c`. Projects are subdirectories — `cd backend`, etc.

## Layout (mockup)

```text
◉ gotibooks           1:tab-1  [2:claude]  3:tab-3        brief  14:32
──────────────────────┬───────────────────────────────────────────────
 $                    │  $
──────────────────────┴───────────────────────────────────────────────
 1 bash · backend      2 claude · backend >
```

- **Top bar:** session/workspace (left) · window tabs (centre) · brief + AI (if any) + time (right)
- **Pane footer:** index · current command · basename of cwd (`>` = active pane)
- No global CPU/RAM/battery/git stack in the status bar (keeps ttyd readable)

## Prefix

**`Ctrl+Space`** — then `-` (split horizontal) or `|` (split vertical), `x` kill pane.

Most navigation/splits work **without prefix** (see below).

## Bindings

### No prefix

| Key | Action |
| --- | --- |
| `Alt+←` `→` `↑` `↓` | Move between panes |
| `Ctrl+↓` | Split below |
| `Ctrl+↑` | Split above |
| `Ctrl+→` | Split right |
| `Ctrl+←` | Split left |
| `Ctrl+Alt+←` `→` | Previous / next window |
| `Alt+Enter` | Zoom pane |
| `Alt+c` | New window |
| `Ctrl+Shift+←` `→` | Swap window |
| `Alt+1`–`Alt+9`, `Alt+0` | Jump to window |
| `Alt+a` | Mouse on (already default) |
| `Alt+q` | Mouse off |

### With prefix `Ctrl+Space`

| Key | Action |
| --- | --- |
| `-` | Split horizontal |
| `\|` | Split vertical |
| `x` | Kill pane |
| `0` | Last window |
| `r` | Reload config (cind) |
| `s` / `w` | Switch **tmux session** (other cind workspaces) |
| `W` | Choose **window** in this session (tab picker) |
| `d` | Detach → back to workspace launcher |
| `P` | Copy pane path (cind) |
| `I` | Workspace info (cind) |

## Appearance

| Element | Style |
| --- | --- |
| Status position | **Top** |
| Status left | Prefix indicator + workspace / session name |
| Window tabs | Centre; inactive muted; **active** cyan block (`colour81`); activity/bell in orange/red |
| Status right (thin) | Optional **AI usage**, `brief` marker, clock |
| Pane border status | **Bottom** on every pane: `index command dirname` |
| Active pane border | Cyan + `>` in the footer |
| Browser font | `TTYD_FONT_SIZE` (default **22**) |

Activity: `monitor-activity` flags windows with background output (tab style only; no message spam).

### AI usage (optional, thin right)

While `claude` or `agent` is running, the right status may show meters from the CLI `statusLine` hook (cache under `~/.cache/cind/`, no network from tmux):

```text
claude ctx 42% · 5h 18% · 7d 4%
```

1. `init-ai-statusline` seeds hooks on container start (missing-only).
2. `cind-ai-statusline` writes `ai-usage-*.json`.
3. Thin `status-right` reads the cache (hidden when stale).

### Font size

```dotenv
TTYD_FONT_SIZE=28
```

Or `cind.config.json` → `ttyd.font_size` (first `make env` if unset in `.env`).

## Browser (ttyd) caveats

Many browsers **do not forward** `Alt+*` or `Ctrl+arrow` to the terminal.

**Workarounds:**

1. Mouse is **on by default** — click top tabs, panes, and drag borders.
2. Prefix splits: `Ctrl+Space` then `-` or `|`.
3. Window list: `Ctrl+Space` `W`.
4. On Android: hardware keyboard or mouse mode.

Host `~/.tmux.conf` is **not mounted**. Edit `docker/rootfs/etc/tmux/` and `make rebuild` for image defaults. Live test in a running container: `prefix r` after copying files, or append overrides under `~/.tmux.conf`.

### Personal override (less chrome)

```tmux
source-file /etc/tmux/tmux.conf
set -g pane-border-status off
```

## File layout

```
/etc/tmux/
  tmux.conf
  options.conf
  keybindings.conf
  status.conf
  scripts/          # status-left/right, session-switch, copy-path, ai-usage
```

## Custom overrides

```tmux
source-file /etc/tmux/tmux.conf
bind Q kill-session
```

Existing sessions keep old UI until `prefix r` (after image has new files) or session recreate.

See also: [Launcher](launcher.md), [Context orchestration](architecture/context.md), [Troubleshooting](troubleshooting.md#tmux-keys-do-not-work-in-the-browser).
