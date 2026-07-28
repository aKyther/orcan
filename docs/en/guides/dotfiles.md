---
description: Customize aliases, tmux, vim, and shell snippets without losing image defaults.
---

# User dotfiles

Image defaults (aliases under `/etc/orcan/shell`, tmux under `/etc/tmux`, skel vim/zsh) stay upgrade-safe. Your personal overrides live on the **host** and are bind-mounted into the container.

## Location

| Host | Container |
| --- | --- |
| `$ORCAN_DATA/dotfiles` (default `~/.config/orcan/dotfiles`) | `~/.config/orcan/dotfiles` |

`orcan sync` creates the directory and copies `*.example` files once (never overwrites your files).

## What you can add

| File | Effect |
| --- | --- |
| `aliases.sh` | Sourced after image aliases (zsh + bash) |
| `zshrc.d/*.zsh` | Extra zsh snippets |
| `bashrc.d/*.sh` | Extra bash snippets |
| `tmux.conf.local` | Sourced after `/etc/tmux/tmux.conf` |
| `vimrc.local` | Sourced after default `.vimrc` |
| `starship.toml` | Replaces `~/.config/starship.toml` (symlink) |
| `gitconfig.local` | `include.path` from `~/.gitconfig` |

Copy an example (drop the `.example` suffix), edit, open a **new** shell (`orcan enter` or a new tmux pane). For tmux: `tmux source-file ~/.tmux.conf` or detach/reattach. You do **not** need `orcan down` after editing these files.

## Examples

```bash
DOT="$HOME/.config/orcan/dotfiles"
cp "$DOT/aliases.sh.example" "$DOT/aliases.sh"
$EDITOR "$DOT/aliases.sh"

cp "$DOT/tmux.conf.local.example" "$DOT/tmux.conf.local"
cp "$DOT/vimrc.local.example" "$DOT/vimrc.local"
```

## What not to do

- Do not edit `/etc/orcan/shell/aliases.sh` or `/etc/tmux/*` inside the container — those reset on image rebuild.
- Do not put secrets in dotfiles if you sync that tree to a public repo; the directory is local under `$ORCAN_DATA`.

See also [Workflows — local terminal](../guides/workflows.md#local-terminal).
