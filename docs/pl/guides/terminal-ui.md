---
description: Wygląd terminala — paleta navy/cyan (ttyd, tmux, zsh, starship, fzf, lazygit). Gdzie edytować i jak rozszerzać.
---

# Terminal UI

Terminal w przeglądarce i lokalny mają jeden wygląd: **dark navy / near-black / subtle cyan**. Ta strona to mapa dla ludzi i agentów zmieniających ten stack.

## Stack

```text
ttyd (motyw xterm.js) → tmux 3.6a → zsh
  ├── prompt Starship
  ├── zsh-autosuggestions + syntax-highlighting + fzf
  ├── aliasy (/etc/orcan/shell/aliases.sh)
  └── lazygit / delta (UI gita)
```

Ograniczenia (nie łamać):

- **ttyd-safe** — Menlo / Monaco / Courier; **bez wymogu Nerd Font**
- Zwykłe Unicode w statusie tmux (bez glifów Powerline)
- Defaulty obrazu w `docker/rootfs/`; nadpisania w `$ORCAN_DATA/dotfiles`

## Paleta

| Rola | Hex | Użycie |
| --- | --- | --- |
| Tło | `#0a0e17` | ttyd, aktywny panel |
| Status / elevated | `#0d1520`, `#111827` | status tmux, chrome |
| Zaznaczenie | `#152033`, `#164e63` | fzf/lazygit, copy-mode |
| Tekst | `#c8d3e0` | domyślny foreground |
| Wyciszony | `#64748b`, `#334155` | nieaktywne taby, separatory |
| Akcent | `#5eead4` | aktywny tab, ramki, kursor |
| Akcent jasny | `#67e8f9` | ścieżka, drugorzędne highlighty |
| Ostrzeżenie / błąd | `#fbbf24`, `#f87171` | activity, błędy, niska bateria |

Presety w `cursor-ttyd`:

| `TTYD_THEME` / `ttyd.theme` | Znaczenie |
| --- | --- |
| `dark` lub `navy` (domyślne) | Ta paleta |
| `mocha` / `catppuccin` | Stary Catppuccin Mocha |
| surowy JSON `{...}` | Własny motyw xterm.js |

## Gdzie zmieniać co

| Warstwa | Ścieżka w repo | Jak wdrożyć |
| --- | --- | --- |
| motyw ttyd | `docker/rootfs/usr/local/bin/cursor-ttyd` | `orcan build` + recreate kontenera |
| binarka tmux | `Dockerfile` (`ARG TMUX_VERSION=3.6a`) | build — static z `tmux/tmux-builds` |
| UI tmux | `docker/rootfs/etc/tmux/` | build; albo kopia + `tmux source-file` przy iteracji |
| zsh | `docker/rootfs/etc/skel/.zshrc`, `.zshrc.d/` | build; albo kopia do `~` na test na żywo |
| kolory fzf / suggest | `docker/rootfs/etc/skel/.zshrc.d/70-plugins.zsh` | nowy shell po kopii/buildzie |
| Starship | `docker/rootfs/opt/orcan/starship.toml` | **missing-only** → `~/.config/starship.toml` |
| lazygit | `docker/rootfs/opt/orcan/lazygit-config.yml` | **missing-only** → `~/.config/lazygit/config.yml` |
| git / delta | `docker/rootfs/opt/orcan/gitconfig` | missing-only → `~/.gitconfig` |
| Overlay użytkownika | `$ORCAN_DATA/dotfiles` | montowane; zobacz [Dotfiles](dotfiles.md) |

**Missing-only** = istniejący plik w home developera **nie** jest nadpisywany przy starcie. Po zmianie seeda w obrazie: usuń kopię w home raz albo zrób merge ręcznie.

## tmux (3.6a)

- Dwa rzędy statusu: wyśrodkowane taby (0), workspace + metryki (1)
- Feature’y za `%if #{>=:#{version},…}` — starszy serwer nadal może przeładować config
- Edytuj pliki obrazu w **repo**, nie tylko w działającym kontenerze
- Prefix: `C-Space`. Przydatne: `r` reload, `s`/`w` sesje, `u` URL, `P` kopiuj ścieżkę

## Rozszerzanie wyglądu (checklist dla agentów)

1. Wybierz wiersz z tabeli; edytuj ścieżkę w **repo**.
2. Trzymaj spójne hexy palety (albo zaktualizuj ten doc + wszystkie warstwy naraz).
3. **Nie** dodawaj TPM / Catppuccin-tmux / Oh My Zsh / Powerlevel10k bez decyzji produktowej.
4. Zaktualizuj docs **EN + PL** i `CHANGELOG.md` `[Unreleased]`.
5. `make validate` i `make docs-check`.
6. Dla Dockerfile / rootfs w obrazie: `orcan build && orcan down && orcan up`.

Reguła Cursora (gdy ruszasz te ścieżki): `.cursor/rules/terminal-ui.mdc`.

## Powiązane

- [Dotfiles użytkownika](dotfiles.md) — własne nadpisania bez rebuilda
- [Docker — referencja](../reference/docker.md) — zawartość obrazu, tmux 3.6a
- [Zmienne środowiskowe](../reference/environment.md) — `TTYD_THEME`, fonty
- [Kontekst AI](../ai/project-context.md) — rytuał agenta
