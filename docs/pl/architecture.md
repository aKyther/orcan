---
description: Dlaczego architektura Orcana wygląda tak — orkiestracja na hoście, path parity, context pack i stos terminala.
---

# Architektura

Ta strona wyjaśnia **dlaczego** elementy istnieją. Targety Make i nazwy plików Compose: [Referencja](reference/makefile.md).

## Problem projektowy

Orcan musi:

1. Opisać **kontekst** multi-repo na hoście (konfiguracja JSON).
2. Uruchamiać agentów w izolowanym **kontenerze** z ciężkimi toolchainami.
3. Utrzymać **identyczne ścieżki bezwzględne**, gdy daemon Dockera hosta rozwiązuje bindy.
4. Dać ludziom i agentom jasne **wejście** (przeglądarka → sesja → shell).

Te ograniczenia wymuszają podział na **orkiestrację hosta** i **runtime kontenera**.

## Warstwy

```mermaid
flowchart TB
  subgraph host [Host]
    cfg["orcan.config.json"]
    make["Makefile + skrypty"]
    gen[".env + wygenerowane mounty .orcan"]
  end
  subgraph container [Kontener]
    entry["entrypoint"]
    term["ttyd → launcher → tmux → zsh"]
    pack["context pack workspace'a"]
    clis["agent / claude"]
  end
  cfg --> make
  make --> gen
  gen --> entry
  entry --> term
  entry --> pack
  term --> clis
  pack --> clis
```

**Podpis:** Host zamienia konfigurację na mounty i env. Kontener zamienia to w sesję i pliki czytelne dla agentów. Modele zostają w każdym CLI.

### Dlaczego host trzyma konfigurację

Konfiguracja musi działać bez obrazu (wizard, testy hosta w CI, `orcan sync`). Stdlib JSON trzyma stronę hosta cienką. YAML Compose zostaje tylko dla Dockera.

### Dlaczego obraz trzyma toolchain

Cursor CLI, Claude Code, toolchainy językowe i domyślne shella są duże i wspólne. Pieczenie ich w obrazie nie zaśmieca laptopów — a **źródła** projektów zostają na hoście przez mounty.

## Path parity i linki workspace

Dwa mechanizmy, jeden powód:

| Mechanizm | Dlaczego |
| --- | --- |
| Bind mount `host_abs:host_abs` | Daemon Dockera hosta potrzebuje prawdziwych ścieżek hosta |
| Symlinki pod `/home/developer/workspaces/<name>/` | Krótkie nazwy do nawigacji i instrukcji agentów |

Zobacz [Model mentalny](ideas/mental-model.md) oraz [Path parity](concepts/path-parity.md).

## Ścieżka wejścia

```mermaid
flowchart LR
  browser[Przeglądarka] --> ttyd[ttyd]
  ttyd --> launcher[launcher]
  launcher --> tmux[sesja tmux per workspace]
  tmux --> zsh[zsh]
  zsh --> agent[agent lub claude]
```

**Podpis:** Launcher to miejsce wyboru workspace'a. tmux trzyma jedną sesję na workspace, więc przełączanie kontekstu jest świadome.

Dlaczego nie sam SSH? Ścieżka przeglądarki to domyślna powierzchnia produktu: jeden URL, jeden launcher, przewidywalny układ tmux. Dlaczego nie bez tmux? Wiele paneli/okien to sposób pracy nad projektami w jednym kontekście; Orcan to standaryzuje zamiast wymyślać nowy multiplekser.

## Context pack vs seedy projektów

W **rootcie workspace'a** Orcan utrzymuje mały pack (manifest, wspólne `AGENTS.md` / `CLAUDE.md`, ignores). Odpowiada na: „czym jest ten kontekst?”

Zamontowane **checkouty git** nie są przepisywane przy każdym starcie. Seed plików w każdym `projects[].path` jest jawny (`orcan seed --all`). Chroni to repo klientów przed niespodziewanymi diffami, a nadal pozwala na wspólny kontekst nad nimi.

## Granica produktu

| Orcan odpowiada za | Orcan nie odpowiada za |
| --- | --- |
| Workspaces, mounty, path parity | Który model używa CLI |
| Context pack | Prompt engineering pod model |
| Ścieżka wejścia (ttyd → launcher → tmux → zsh) | Auto-routing między CLI |
| Izolacja Dockera i opcjonalny socket hosta | Współdzielony RAG poza plikami workspace'a |

## Non-goals (z założenia)

- UI ani flag do wyboru / przypinania modeli  
- Abstrakcji `AgentProvider` nad `agent` / `claude`  
- Auto-routingu promptów między CLI  
- Kolejki zadań (brief → CLI → magistrala wyników)

## Gdzie leży kod

| Obszar | Lokalizacja |
| --- | --- |
| Orkiestracja na hoście | `Makefile`, `scripts/repository/`, pliki Compose |
| System plików kontenera | `docker/rootfs/` |
| Build obrazu | `Dockerfile` |
| Globalne domyślne Cursor (seed missing-only) | `docker/rootfs/opt/cursor-defaults/` |
| Reguły Cursor tego repo | `.cursor/rules/` |

## Dalej

- [Idee podstawowe](ideas/core-ideas.md)  
- [Typowe workflowy](guides/workflows.md)  
- [Interfejs hosta i kontenera](interface.md)
