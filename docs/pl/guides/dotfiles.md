---
description: Własne aliasy, tmux, vim i snippety shell bez utraty defaultów obrazu.
---

# Dotfiles użytkownika

Domyślne ustawienia obrazu (aliasy w `/etc/orcan/shell`, tmux w `/etc/tmux`, skel vim/zsh) zostają bezpieczne przy upgrade. Twoje nadpisania żyją na **hoście** i są montowane do kontenera.

## Lokalizacja

| Host | Kontener |
| --- | --- |
| `$ORCAN_DATA/dotfiles` (domyślnie `~/.config/orcan/dotfiles`) | `~/.config/orcan/dotfiles` |

`orcan sync` tworzy katalog i raz kopiuje pliki `*.example` (nigdy nie nadpisuje Twoich plików).

## Co możesz dodać

| Plik | Efekt |
| --- | --- |
| `aliases.sh` | Po aliasach obrazu (zsh + bash) |
| `zshrc.d/*.zsh` | Dodatkowe snippety zsh |
| `bashrc.d/*.sh` | Dodatkowe snippety bash |
| `tmux.conf.local` | Po `/etc/tmux/tmux.conf` |
| `vimrc.local` | Po domyślnym `.vimrc` |
| `starship.toml` | Zastępuje `~/.config/starship.toml` (symlink) |
| `gitconfig.local` | `include.path` z `~/.gitconfig` |

Domyślny **wygląd terminala** (ttyd, tmux, starship, fzf, lazygit) jest w `docker/rootfs/` — zobacz [Terminal UI](terminal-ui.md). Dotfiles tylko nakładają; nie zastępują mapy obrazu.

Skopiuj przykład (usuń sufiks `.example`), edytuj, otwórz **nowy** shell (`orcan enter` albo nowe okno tmux). Dla tmux: `tmux source-file ~/.tmux.conf` albo detach/reattach. **Nie** musisz robić `orcan down` po edycji tych plików.

## Przykłady

```bash
DOT="$HOME/.config/orcan/dotfiles"
cp "$DOT/aliases.sh.example" "$DOT/aliases.sh"
$EDITOR "$DOT/aliases.sh"

cp "$DOT/tmux.conf.local.example" "$DOT/tmux.conf.local"
cp "$DOT/vimrc.local.example" "$DOT/vimrc.local"
```

## Czego nie robić

- Nie edytuj `/etc/orcan/shell/aliases.sh` ani `/etc/tmux/*` w kontenerze — wrócą przy rebuildzie obrazu.
- Nie trzymaj sekretów w dotfiles, jeśli synchronizujesz ten katalog do publicznego repo; katalog jest lokalny pod `$ORCAN_DATA`.

Zobacz też [Workflowy — lokalny terminal](../guides/workflows.md#local-terminal).
