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
| zsh | `docker/rootfs/etc/skel/.zshrc`, `.zshrc.d/` | build (skel → home on new image); or copy into `~` for live test |
| fzf / suggest colours | `docker/rootfs/etc/skel/.zshrc.d/70-plugins.zsh` | new shell after copy/build |
| Starship | `docker/rootfs/opt/orcan/starship.toml` | **missing-only** → `~/.config/starship.toml` |
| lazygit | `docker/rootfs/opt/orcan/lazygit-config.yml` | **missing-only** → `~/.config/lazygit/config.yml` |
| git / delta | `docker/rootfs/opt/orcan/gitconfig` | missing-only → `~/.gitconfig` |
| User overlays | `$ORCAN_DATA/dotfiles` | bind-mounted; see [User dotfiles](dotfiles.md) |

**Missing-only** means an existing file in the developer home is **not** overwritten on container start. After changing the image seed, either delete the home copy once, or tell the user to merge manually.

## tmux notes (3.6a)

- Two status rows: centred window tabs (row 0), workspace + metrics (row 1)
- Features gated with `%if #{>=:#{version},…}` so an older server can still reload config
- Prefer editing image files under `/etc/tmux` in the **repo**, not only a running container
- Prefix is `C-Space`. Useful: `r` reload, `s`/`w` session switch, `u` URL pick, `P` copy path

## Extending the look (checklist for agents)

1. Pick the layer table row; edit the **repo** path.
2. Keep the palette hex values aligned (or update this doc + all layers together).
3. Do **not** add TPM / Catppuccin-tmux / Oh My Zsh / Powerlevel10k unless product decision says so.
4. Update **EN + PL** docs and `CHANGELOG.md` `[Unreleased]`.
5. `make validate` and `make docs-check`.
6. For Dockerfile / rootfs that ships in the image: `orcan build && orcan down && orcan up`.

Cursor rule (auto when touching these paths): `.cursor/rules/terminal-ui.mdc`.

## Related

- [User dotfiles](dotfiles.md) — personal overrides without rebuilding
- [Docker reference](../reference/docker.md) — image contents including tmux 3.6a
- [Environment variables](../reference/environment.md) — `TTYD_THEME`, fonts
- [AI project context](../ai/project-context.md) — agent ritual
