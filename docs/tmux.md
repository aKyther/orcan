# tmux inside ttyd

cind tmux matches **host `~/.tmux.conf`** (prefix, colours, Alt/Ctrl bindings). Config lives in `/etc/tmux/`; `~/.tmux.conf` in the container only sources it.

**Flow:** ttyd → workspace launcher (pick session) → tmux with tabs `workspace-1` … `workspace-3`.

Rename tabs anytime: `Ctrl+Space` `,` (prompt) or `Alt+c` for a new window. Projects live as subdirectories — `cd backend` etc.

## Prefix

**`Ctrl+Space`** — then `-` (split horizontal) or `|` (split vertical), `x` kill pane.

Most navigation/splits work **without prefix** (see below).

## Bindings (same as local)

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
| `Alt+a` | Mouse on |
| `Alt+q` | Mouse off |

### With prefix `Ctrl+Space`

| Key | Action |
| --- | --- |
| `-` | Split horizontal |
| `\|` | Split vertical |
| `x` | Kill pane |
| `0` | Last window |
| `r` | Reload config (cind) |
| `P` | Copy pane path (cind) |
| `s` | Session switch (cind) |
| `I` | Workspace info (cind) |

## Appearance

| Element | Style |
| --- | --- |
| Status bar | Dark (`colour234`) with cyan workspace, mint session, gold prefix active |
| Window tabs | Inactive grey; **active tab** cyan background (`colour81`) |
| Right status | Git branch, cwd, CPU load, memory %, battery, time |
| Browser font | `TTYD_FONT_SIZE` (default **22** in `.env` / `cind.config.json`) |
| Pane borders | Active pane highlighted cyan |

Set font size in `.env`:

```dotenv
TTYD_FONT_SIZE=28
```

Or in `cind.config.json` → `ttyd.font_size` (applied on first `make env` only if unset in `.env`).

## Browser (ttyd) caveats

Many browsers **do not forward** `Alt+*` or `Ctrl+arrow` to the terminal — bindings match local tmux, but the browser may block them.

**Workarounds:**

1. `Alt+a` — enable mouse, then click panes and drag borders.
2. Prefix splits: `Ctrl+Space` then `-` or `|`.
3. On Android: hardware keyboard for the shortcuts above, or mouse mode.

Host `~/.tmux.conf` is **not mounted** into the container. To change defaults for everyone using the image, edit `docker/rootfs/etc/tmux/` and `make rebuild`.

## File layout

```
/etc/tmux/
  tmux.conf
  options.conf
  keybindings.conf
  status.conf
  scripts/          # cind helpers (copy-path, session-switch)
```

## Custom overrides

Inside the container, append **after** `source-file` in `~/.tmux.conf`:

```tmux
source-file /etc/tmux/tmux.conf
bind Q kill-session
```

Existing sessions keep old binds until recreated or `prefix r` after reload.

See also: [Launcher](launcher.md), [Troubleshooting](troubleshooting.md#tmux-keys-do-not-work-in-the-browser).
