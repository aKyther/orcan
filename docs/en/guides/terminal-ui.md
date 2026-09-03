---
description: Terminal look — restrained graphite and plum chrome around the terminal toolchain. Where to edit and how to extend.
tags:
  - guide
  - develop
---

# Terminal UI

Orcan’s cockpit uses quiet **graphite / near-black / muted plum** surfaces. A
single violet accent marks interaction; colour is otherwise reserved for
state. Tmux chrome follows the same hierarchy while programs inside panes
retain their terminal-native palette. This page is the map for humans and
agents changing that stack.

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

Cockpit's embedded PTY renders a blinking reverse-video block cursor while it
has keyboard focus. It follows the cursor from zsh, Codex, Claude Code and
other terminal applications, but respects applications that intentionally hide
their cursor.

## Palette

| Role | Hex | Used for |
| --- | --- | --- |
| Background | `#12101a` | cockpit and empty states |
| Elevated | `#1b1724`, `#211c2b` | bars, picker, dialogs |
| Selection | `#2a2237`, `#342a44` | active and hover surfaces |
| Foreground | `#e2ddea` | primary text |
| Muted | `#948ba3`, `#b0a6ba` | metadata and secondary text |
| Accent | `#ad91d0`, `#c7b1e2` | focus and interactive identity |
| Warn / alert | `#fbbf24`, `#f87171` | activity, errors, low battery |

The **MkDocs site** reuses these tokens (`docs/assets/stylesheets/orcan.css`, favicon). Light docs mode uses a darker teal accent for readable links on white.

Presets in `cursor-ttyd`:

| `TTYD_THEME` / `ttyd.theme` | Meaning |
| --- | --- |
| `dark` or `navy` (default) | Graphite/plum palette (legacy preset name) |
| `mocha` / `catppuccin` | Legacy Catppuccin Mocha |
| raw `{...}` JSON | Custom xterm.js theme |

## Where to change what

| Layer | Path in repo | Apply how |
| --- | --- | --- |
| ttyd theme | `docker/rootfs/usr/local/bin/cursor-ttyd` | `orcan build` + recreate container |
| tmux binary | `Dockerfile` (`ARG TMUX_VERSION=3.6a`) | build — static binary from `tmux/tmux-builds` |
| tmux UI | `docker/rootfs/etc/tmux/` (`status.conf`, `options.conf`, `keybindings.conf`, `scripts/`) | build; or copy + `tmux source-file` for iteration |
| Cockpit layout / chrome | `cockpit/src/orcan_cockpit/app.py`, `top_bar.py`, `rail.py`, `status_bar.py` | `make dev-restart` (isolated); or `orcan build` + recreate |
| Cockpit keys / help | `cockpit/…/shortcuts.py` (+ `keybindings.conf` for tmux tokens) | same; host test keeps tokens aligned |
| Cockpit PTY | `pty_terminal.py`, `pty_keys.py`, `pty_colors.py`, `pty_tmux_nav.py` | same — see [Cockpit + browser](#cockpit-browser) / [nav mix](#cockpit-nav-mix) |
| zsh | `docker/rootfs/etc/skel/.zshrc`, `.zshrc.d/` | build (skel → home on new image); or copy into `~` for live test |
| fzf / suggest colours | `docker/rootfs/etc/skel/.zshrc.d/70-plugins.zsh` | new shell after copy/build |
| Starship | `docker/rootfs/opt/orcan/starship.toml` | managed default → `~/.config/starship.toml` |
| lazygit | `docker/rootfs/opt/orcan/lazygit-config.yml` | managed default → `~/.config/lazygit/config.yml` |
| git / delta | `docker/rootfs/opt/orcan/gitconfig` | missing-only → `~/.gitconfig` |
| User overlays | `$ORCAN_DATA/dotfiles` | bind-mounted; see [User dotfiles](dotfiles.md) |

Starship and lazygit use **managed defaults**: Orcan records the exact seed it
wrote and refreshes it on a later image only while the file remains unchanged.
Known defaults from older images are migrated once by checksum. A user edit or
dotfile overlay stops management and is never overwritten. Git config remains
strictly missing-only.

## tmux notes (3.6a)

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

These use tmux `M-…` / `C-…` binds in `keybindings.conf` for **raw**
`orcan enter --tmux`. They must arrive as **Meta**/Ctrl CSI, not as composed
characters. **Inside the cockpit** the arrow chords differ — see
[Cockpit nav mix](#cockpit-nav-mix).

| Keys | Action (`--tmux` / conf) |
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
The cockpit shortcuts overlay (**F1** always; **?** when focus is outside the
embedded terminal) and tmux **prefix ?** popup repeat this at the bottom —
see `EMBED_DISCLAIMER` in `shortcuts.py`. With terminal focus, typing **?** goes
into the shell — use **F1** there. Three layers at once:

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
| `pty_tmux_nav.py` | Textual → `tmux` CLI | Ctrl/Alt+arrows / Ctrl+Shift+arrows — see [Cockpit nav mix](#cockpit-nav-mix) |
| `pty_keys.py` | Textual → PTY | other `keybindings.conf` ``bind -n`` chords — see table below |
| `pty_mouse.py` | Textual → PTY | wheel/clicks never reach tmux; SGR vs legacy X10 (`@`/`A` on screen) |
| `pty_colors.py` | pyte → Rich | `brown` / bright aliases break render |
| `pty_terminal.py` | PTY ↔ pyte ↔ UI | resize (`TIOCSCTTY`), refresh, selection vs tmux, `?1000/1006` modes, `Escape`+key coalesce |

#### Cockpit nav mix (Alt-as-Ctrl limit) { #cockpit-nav-mix }

**Limitation:** under ttyd/xterm.js and some desktop terminals (Windows Terminal /
WSL), **Alt+←/→/↑/↓** often arrives at Textual as **`ctrl+arrow`** — there is no
separate Meta event. Cockpit cannot implement both “Ctrl = split” and
“Alt = focus pane” when those chords look identical.

**Cockpit behaviour** (`pty_tmux_nav.py` — calls `tmux select-pane` /
`split-window` directly, no CSI to the child PTY):

| Shortcut | Cockpit action |
| --- | --- |
| `Ctrl` or `Alt` + `←/→/↑/↓` | Focus pane |
| `Ctrl+Shift` + `←/→/↑/↓` | Split pane |
| `prefix -` / `prefix \|` | Split (unchanged; forwarded to tmux) |

**Raw attach** (`orcan enter --tmux`): `keybindings.conf` is unchanged —
`Ctrl+arrows` = split, `Alt+arrows` = focus **when Meta is delivered**.

F1 / **?** and **prefix ?** footers show this as `BROWSER_KEY_LIMIT` in
`shortcuts.py`. `Alt+1`…`Alt+9` is a separate path (often OK with
`macOptionIsMeta` on macOS).

**Local tmux binds (`bind -n`, no prefix)** — still used for chords that the
cockpit **forwards** as bytes (not the nav-mix set above). Each needs correct
CSI / Meta in one write:

| Shortcut | tmux | Target bytes |
| --- | --- | --- |
| `Ctrl+Space` | prefix | `\x00` |
| `prefix z` | zoom pane | `z` after `\x00` (C-Space) — no wrapper map |
| `Ctrl+Alt+←/→` | prev/next window | `\x1b[1;7D/C` |
| `Alt+c` / `Alt+a` / `Alt+q` | new win / mouse | `\x1bc` / `\x1ba` / `\x1bq` |
| `Alt+0..9` | select window | `\x1b0` … `\x1b9` |

Textual splits many of the above into `Escape` + a second key — the cockpit
recombines them (`pty_keys.esc_follow_up_bytes` + coalesce window in
`pty_terminal`).

**Mouse:** tmux sends `?1006l` then `?1006h` on attach — parser must take the
**last** state (not substring `in data`). Forward mouse only after tmux enables `?1000h`.

**Copy:** selection is Textual (not xterm). `Ctrl+C` with selection → clipboard;
without selection → SIGINT. Paste is queued to the non-blocking PTY, so a
confirmed large paste is delivered in full rather than being cut at the PTY
buffer boundary.

Pastes of **32 KiB or more** are staged instead of being injected into the
active agent. Orcan writes a private `0600` file under `/tmp/orcan-paste-*.md`
and types a short instruction with its path. The agent can read the complete
request without losing its terminal context. Staged files expire after 24 hours.

**Scrollback:** pyte holds the **current** screen; tmux scrolls history (copy-mode)
and redraws the pane — the wheel must reach tmux as SGR.

#### Concrete requirements (regression)

- **`C-Space` and `Alt+…` must reach tmux** — the widget remaps Textual keys to raw pty bytes (`ctrl+space` → `\x00`; `alt+1` → one write `\x1b` + `1`). Splitting ESC and the base key into two writes breaks `escape-time` (tmux treats ESC alone). Textual also maps `ESC+digit` to macOS Option glyphs (`¡`/`™`/`£`); the cockpit reverses those back to Meta (`pty_keys.py`) so Windows Terminal / Linux Alt+1…9 works like a plain `tmux attach`.
- **Resize** needs a controlling tty on the child (`TIOCSCTTY`) so `TIOCSWINSZ` delivers **SIGWINCH** to tmux; otherwise the pane stays at attach size.
- Spawn size falls back to **80×24** when the widget is still `0×0` at mount (avoids a 1×1 dead terminal).
- Colors: pyte per-cell render (status/prompt match native attach).

Host tests (no Textual): `tests/host/test_cockpit_pty_{keys,mouse,colors,tmux_nav}.py`.
Smoke: `tests/smoke/test-cockpit-tui.py`.

Browser ttyd (`cursor-ttyd`) sets **`macOptionIsMeta=true`** so macOS Option/Alt sends Meta (needed for `Alt+1`…), not `¡` / `™` composition. No effect on Windows/Linux.

On touch screens, a one-finger vertical drag over the embedded terminal is
translated to tmux scrollback. The bridge listens only to browser touch events;
mouse, trackpad, keyboard, native `orcan enter`, and Windows Terminal / WSL
input keep their existing paths. A short tap stays a tap because scrolling
starts only after a vertical movement threshold.

Phone and tablet typography is responsive: 16 px up to 600 px wide, 14 px up
to 1024 px, and the configured `TTYD_FONT_SIZE` (14 px by default) on desktop.
An explicit `?fontSize=N` URL parameter overrides the automatic profile. While
xterm's input is focused, the bridge also follows `visualViewport`; when the
software keyboard reduces the visible height, ttyd refits its rows so the
current prompt remains above the keyboard.

### Cockpit chrome (app layer)

**Width tiers** (terminal columns, not browser CSS breakpoints —
`status.py` / `tier_for_width`):

| Tier | Columns | Effect |
| --- | --- | --- |
| `compact` | 90–119 | Bottom bar shortens; the workspace picker overlays the terminal |
| `minimal` | < 90 | Hides rail and metrics; the workspace pill remains available above the full-width terminal |

| Keys | Action |
| --- | --- |
| **F4** / workspace pill | Open the workspace picker without resizing the terminal |
| **F1** (always) · **?** (outside terminal) / rail ? | Shortcuts overlay (not About). With terminal focused, **?** is typed into the shell — use **F1** |
| **Click `🌀 orcan`** | About (name, version, docs) — `about_modal.py` |
| **Click current workspace** | Open/close the workspace browser without losing the active workspace identity |
| **F5** | Peek the current workspace session brief |
| **Ctrl+P** | Command palette (outside the terminal focus) |
| **i** | Expand/collapse workspace details (list focused) |
| **prefix ?** | Standalone tmux shortcuts popup (works without cockpit) |
| **`lg`** (in shell) | lazygit — not a cockpit F-key |

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
