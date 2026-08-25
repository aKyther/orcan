---
description: Terminal look — navy/cyan palette across ttyd, tmux, zsh, starship, fzf, and lazygit. Where to edit and how to extend.
tags:
  - guide
  - develop
---

# Terminal UI

Orcan’s browser and local terminal share one look: **dark navy / near-black / subtle cyan**. This page is the map for humans and agents changing that stack.

## Stack

```text
ttyd (xterm.js theme) → tmux 3.6a → zsh
  ├── Starship prompt
  ├── zsh-autosuggestions + syntax-highlighting + fzf
  ├── aliases (/etc/orcan/shell/aliases.sh)
  └── lazygit / delta (git UI)
```

Constraints (do not break these):

- **ttyd-safe** — Menlo / Monaco / Courier; **no Nerd Font** requirement
- Plain Unicode icons in tmux status (not Powerline glyphs)
- Image defaults under `docker/rootfs/`; personal overlays in `$ORCAN_DATA/dotfiles`

## Palette

| Role | Hex | Used for |
| --- | --- | --- |
| Background | `#0a0e17` | ttyd bg, active pane |
| Status / elevated | `#0d1520`, `#111827` | tmux status, inactive chrome |
| Selection | `#152033`, `#164e63` | fzf/lazygit selection, copy-mode |
| Foreground | `#c8d3e0` | default text |
| Muted | `#64748b`, `#334155` | inactive tabs, separators |
| Accent | `#5eead4` | active tab, borders, cursor |
| Accent bright | `#67e8f9` | path, secondary highlights |
| Warn / alert | `#fbbf24`, `#f87171` | activity, errors, low battery |

The **MkDocs site** reuses these tokens (`docs/assets/stylesheets/orcan.css`, favicon). Light docs mode uses a darker teal accent for readable links on white.

Presets in `cursor-ttyd`:

| `TTYD_THEME` / `ttyd.theme` | Meaning |
| --- | --- |
| `dark` or `navy` (default) | This palette |
| `mocha` / `catppuccin` | Legacy Catppuccin Mocha |
| raw `{...}` JSON | Custom xterm.js theme |

## Where to change what

| Layer | Path in repo | Apply how |
| --- | --- | --- |
| ttyd theme | `docker/rootfs/usr/local/bin/cursor-ttyd` | `orcan build` + recreate container |
| tmux binary | `Dockerfile` (`ARG TMUX_VERSION=3.6a`) | build — static binary from `tmux/tmux-builds` |
| tmux UI | `docker/rootfs/etc/tmux/` (`status.conf`, `options.conf`, `keybindings.conf`, `scripts/`) | build; or copy + `tmux source-file` for iteration |
| Cockpit layout / chrome | `cockpit/src/orcan_cockpit/app.py`, `activity.py`, `top_bar.py`, `rail.py`, `status_bar.py` | `make dev-restart` (isolated); or `orcan build` + recreate |
| Cockpit keys / help | `cockpit/…/shortcuts.py` (+ `keybindings.conf` for tmux tokens) | same; host test keeps tokens aligned |
| Cockpit PTY | `pty_terminal.py`, `pty_keys.py`, `pty_colors.py` | same — see [Cockpit + browser](#cockpit-browser) |
| zsh | `docker/rootfs/etc/skel/.zshrc`, `.zshrc.d/` | build (skel → home on new image); or copy into `~` for live test |
| fzf / suggest colours | `docker/rootfs/etc/skel/.zshrc.d/70-plugins.zsh` | new shell after copy/build |
| Starship | `docker/rootfs/opt/orcan/starship.toml` | **missing-only** → `~/.config/starship.toml` |
| lazygit | `docker/rootfs/opt/orcan/lazygit-config.yml` | **missing-only** → `~/.config/lazygit/config.yml` |
| git / delta | `docker/rootfs/opt/orcan/gitconfig` | missing-only → `~/.gitconfig` |
| User overlays | `$ORCAN_DATA/dotfiles` | bind-mounted; see [User dotfiles](dotfiles.md) |

**Missing-only** means an existing file in the developer home is **not** overwritten on container start. After changing the image seed, either delete the home copy once, or tell the user to merge manually.

## tmux notes (3.6a)

- One status row: centred window tabs only — workspace/metrics live in the cockpit top/bottom bars (raw `tmux attach` / `orcan enter --tmux` outside the cockpit will not show CPU/RAM/branch)
- Features gated with `%if #{>=:#{version},…}` so an older server can still reload config
- Prefer editing image files under `/etc/tmux` in the **repo**, not only a running container
- Prefix is **C-Space** (not `C-b`). Config: `docker/rootfs/etc/tmux/keybindings.conf`

### Prefix bindings (after `C-Space`)

| Keys | Action |
| --- | --- |
| `r` | Reload `/etc/tmux/tmux.conf` |
| `s` / `w` | Switch orcan workspace session |
| `W` | Choose window (IDE-style) |
| `u` | Pick/copy http(s) URL (joins soft-wrapped lines) |
| `P` | Copy path helper |
| `-` / `\|` | Split vertical / horizontal |
| `x` | Kill pane |

### Prefix-free (Meta / Alt — local shortcuts)

These use tmux `M-…` binds. They must arrive as **Meta**, not as composed characters.

| Keys | Action |
| --- | --- |
| `Alt+1` … `Alt+9` | Select window 1–9 |
| `Alt+0` | Select last window |
| `Alt+←/→/↑/↓` | Focus pane |
| `prefix z` | Zoom pane |
| `Alt+c` | New window |
| `Alt+a` / `Alt+q` | Mouse on / off |
| `Ctrl+←/→/↑/↓` | Split (direction) |
| `Ctrl+Alt+←/→` | Previous / next window |
| `Ctrl+Shift+←/→` | Swap window left / right |

### Cockpit + browser (do not break) { #cockpit-browser }

When `agent-launcher` embeds tmux (`cockpit/…/pty_terminal.py`):

#### Two terminals in one

Embedded tmux is **not** a native attach (`tmux attach` in Windows Terminal).
The cockpit **F1** / **?** shortcuts overlay (and tmux **prefix ?** popup) repeat
this at the bottom — see `EMBED_DISCLAIMER` in `shortcuts.py`. Three layers at once:

```text
Textual (UI, focus, selection, mouse)  ↔  pyte (VT100 emulation)  ↔  tmux attach (PTY)
```

Textual does **not** forward keyboard/mouse/paste automatically — each channel
needs its own translator in-repo. That is expected, not a one-off bug. With
`make dev-enter` / the cockpit, assume **every new input** (scroll, copy, tmux
status clicks, bracketed paste, …) may need dedicated logic — or use full tmux:
`orcan enter --tmux NAME` (no cockpit).

| Module | Direction | Without translation |
| --- | --- | --- |
| `pty_keys.py` | Textual → PTY | full `keybindings.conf` ``bind -n`` map — see table below |
| `pty_mouse.py` | Textual → PTY | wheel/clicks never reach tmux; SGR vs legacy X10 (`@`/`A` on screen) |
| `pty_colors.py` | pyte → Rich | `brown` / bright aliases break render |
| `pty_terminal.py` | PTY ↔ pyte ↔ UI | resize (`TIOCSCTTY`), refresh, selection vs tmux, `?1000/1006` modes, `Escape`+key coalesce |

**Local tmux binds (`bind -n`, no prefix)** — each needs correct CSI / Meta in one write:

| Shortcut | tmux | Target bytes |
| --- | --- | --- |
| `Ctrl+Space` | prefix | `\x00` |
| `Alt+←/→/↑/↓` | focus pane | `\x1b\x1b[D/C/A/B` (legacy Meta) |
| `prefix z` | zoom pane | `z` after `\x00` (C-Space) — no wrapper map |
| `Ctrl+←/→/↑/↓` | split | `\x1b[1;5D/C/A/B` |
| `Ctrl+Alt+←/→` | prev/next window | `\x1b[1;7D/C` |
| `Ctrl+Shift+←/→` | swap window | `\x1b[1;6D/C` |
| `Alt+c` / `Alt+a` / `Alt+q` | new win / mouse | `\x1bc` / `\x1ba` / `\x1bq` |
| `Alt+0..9` | select window | `\x1b0` … `\x1b9` |

Textual splits many of the above into `Escape` + a second key — the cockpit
recombines them (`pty_keys.esc_follow_up_bytes` + 50 ms window in `pty_terminal`).

**Mouse:** tmux sends `?1006l` then `?1006h` on attach — parser must take the
**last** state (not substring `in data`). Forward mouse only after tmux enables `?1000h`.

**Copy:** selection is Textual (not xterm). `Ctrl+C` with selection → clipboard;
without selection → SIGINT. Paste: `on_paste` → PTY.

**Scrollback:** pyte holds the **current** screen; tmux scrolls history (copy-mode)
and redraws the pane — the wheel must reach tmux as SGR.

#### Concrete requirements (regression)

- **`C-Space` and `Alt+…` must reach tmux** — the widget remaps Textual keys to raw pty bytes (`ctrl+space` → `\x00`; `alt+1` → one write `\x1b` + `1`). Splitting ESC and the base key into two writes breaks `escape-time` (tmux treats ESC alone). Textual also maps `ESC+digit` to macOS Option glyphs (`¡`/`™`/`£`); the cockpit reverses those back to Meta (`pty_keys.py`) so Windows Terminal / Linux Alt+1…9 works like a plain `tmux attach`.
- **Resize** needs a controlling tty on the child (`TIOCSCTTY`) so `TIOCSWINSZ` delivers **SIGWINCH** to tmux; otherwise the pane stays at attach size.
- Spawn size falls back to **80×24** when the widget is still `0×0` at mount (avoids a 1×1 dead terminal).
- Colors: pyte per-cell render (status/prompt match native attach).

Host tests (no Textual): `tests/host/test_cockpit_pty_{keys,mouse,colors}.py`.
Smoke: `tests/smoke/test-cockpit-tui.py`.

Browser ttyd (`cursor-ttyd`) sets **`macOptionIsMeta=true`** so macOS Option/Alt sends Meta (needed for `Alt+1`…), not `¡` / `™` composition. No effect on Windows/Linux.

### Cockpit chrome (app layer)

```text
top bar:    utility rail (☰ 🔔 ⎇ ?)  ·  CPU / RAM / clock (right)
main row:   workspaces + ASSERTIONS  |  terminal + hint strip
bottom:     status bar (workspace · branch · tmux · pending)
```

The utility rail used to be a far-right column — it now lives in **`top_bar.py`**
(left icons; metrics on the right). ASSERTIONS used to be a separate right panel —
they now sit at the bottom of the left column (`activity.py`). SoT for keys:
`cockpit/src/orcan_cockpit/shortcuts.py` (host tests assert tmux tokens stay in
`keybindings.conf`). **F1** / **?** footer: embedded tmux ≠ native attach
(`EMBED_DISCLAIMER`).

**Width tiers** (terminal columns, not browser CSS breakpoints —
`status.py` / `tier_for_width`):

| Tier | Columns | Effect |
| --- | --- | --- |
| `full` | ≥ 120 | Full bottom bar (branch + tmux session + pending) |
| `compact` | 90–119 | Bottom bar shortens (workspace + pending; no branch/session line) |
| `minimal` | < 90 | Hides **top bar** + **left column** (terminal full width); F-keys still work |

**F4** / **F2** still toggle workspaces / ASSERTIONS manually when visible.

| Keys | Action |
| --- | --- |
| **F2** / rail 🔔 | Toggle left-column ASSERTIONS section |
| **F4** / rail ☰ | Toggle workspaces column |
| **F3** / rail ⎇ | Git (`lazygit` popup) |
| **F1** / **?** / rail ? | Shortcuts overlay (includes embed ≠ native attach note) |
| **Ctrl+P** | Command palette (outside the terminal focus) |
| **r** | Run `orcan-context-review` (ASSERTIONS focused) |
| **p** | Pause/resume context automation (ASSERTIONS focused) |
| **o** | Turn context automation off/on (ASSERTIONS focused) |
| **prefix ?** | Standalone tmux shortcuts popup (works without cockpit) |

Daily enter flow: [Workflows — local terminal](workflows.md#local-terminal).

Verify after UX edits: `make dev-restart`, then `make dev-smoke` (and `make dev-visual` when chrome/layout screenshots matter); try `Alt+1` / resize the browser; or `./scripts/dev/terminal-ui-preview` for chrome-only.

## Preview without disturbing daily Orcan

From a git checkout (not the public CLI):

| Need | Command | Notes |
| --- | --- | --- |
| tmux status / keys / layout only | `./scripts/dev/terminal-ui-preview` | Isolated tmux socket; **C-Space r** reloads checkout files |
| Full browser UX (ttyd + cockpit + image) | `make dev-start` | Own image `orcan:dev-ux`, port/home under `.orcan-dev-ux/` |
| After UX edits | `make dev-restart` | Refresh cockpit from checkout; recreate; wait until healthy |
| Automated checks | `make dev-smoke` / `dev-a11y` / `dev-visual` | Textual+PTY; Playwright a11y + screenshots (preview must be up) |
| Pre-merge list | `make dev-checklist` | Prints automated targets + manual browser flow |
| Verify isolation | `make dev-doctor` | Docker identity, health, HTTP |

Details, flags, and isolation rules: [Testing — maintainer previews](../development/testing.md).

## Extending the look (checklist for agents)

1. Pick the layer table row; edit the **repo** path.
2. Keep the palette hex values aligned (or update this doc + all layers together).
3. Do **not** add TPM / Catppuccin-tmux / Oh My Zsh / Powerlevel10k unless product decision says so.
4. Iterate with `./scripts/dev/terminal-ui-preview` (tmux) or `make dev-restart` (full UX); verify with `make dev-smoke` / `make dev-visual` as needed.
5. Update **EN + PL** docs and `CHANGELOG.md` `[Unreleased]`.
6. `make validate` and `make docs-check`.
7. For Dockerfile / rootfs that ships in the image: `orcan build && orcan down && orcan up`.

Cursor rule (auto when touching these paths): `.cursor/rules/terminal-ui.mdc`.

## Related

- [User dotfiles](dotfiles.md) — personal overrides without rebuilding
- [Testing](../development/testing.md) — `make dev-*` / `scripts/dev/`
- [Docker reference](../reference/docker.md) — image contents including tmux 3.6a
- [Environment variables](../reference/environment.md) — `TTYD_THEME`, fonts
- [AI project context](../ai/project-context.md) — agent ritual
