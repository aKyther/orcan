---
description: Skrzynka agentów — kolejka zadań na plikach, która przekazuje mały, ustrukturyzowany manifest od agenta dyskutującego do agenta wykonującego, zamiast całego transkryptu.
---

# Skrzynka agentów

**Skrzynka agentów** (agent inbox) to kolejka na plikach pod
`<workspace_root>/.orcan/tasks/`, która przekazuje mały, ustrukturyzowany
**manifest zadania** od agenta planującego/dyskutującego do agenta
wykonującego. Nigdy nie przekazuje własnego transkryptu agenta dyskutującego.

## Problem, który to rozwiązuje

Rozmowa planistyczna w jednej sesji agenta często kończy się „teraz idź to
zaimplementuj". Najprostszy sposób przekazania tego dalej to wklejenie całego
transkryptu do innej sesji — ale to marnuje kontekst na dyskusję, która nigdy
nie była decyzją, i nie daje agentowi wykonującemu żadnego sposobu, żeby
odróżnić „to ustaliliśmy" od „nadal się o to spieraliśmy".

## Jak to działa

```mermaid
flowchart LR
  propose[propose] -->|policy=draft| proposals[proposals/]
  propose -->|policy=approve, domyślnie| proposals
  proposals -->|akceptacja człowieka| inbox[inbox/]
  propose -->|policy=auto| inbox
  inbox -->|claim, atomowo| processing[processing/]
  processing --> done[done/]
  processing --> review[review/]
  processing --> failed[failed/]
```

- **`draft`** — zostaje wyłącznie w `proposals/`; nikt nigdy tego nie podejmuje.
- **`approve`** (domyślne) — siedzi w `proposals/`, aż człowiek uruchomi `approve`.
- **`auto`** — trafia od razu do `inbox/`, gotowe do podjęcia natychmiast.

`orcan-inbox` (CLI w kontenerze) pokrywa cały cykl życia:

```bash
orcan-inbox propose --title "Dodaj retry do fetch()" \
  --goal "Wywołania sieciowe powinny ponowić próbę raz po timeoucie" \
  --file src/fetch.ts --acceptance "Istniejące testy nadal przechodzą"
orcan-inbox approve task-abc123
orcan-inbox watch --executor claude   # podejmuje + uruchamia po jednym zadaniu
```

`claim` to atomowa zmiana nazwy (`inbox/<id>.json` → `processing/<id>.json`),
więc dwóch workerów ścigających się o to samo zadanie nigdy obu go nie
dostanie — przegrany po prostu dostaje `OSError` i idzie dalej. **Executor**
zamienia potem manifest w prompt (`build_prompt()` renderuje tylko znane pola:
goal, context, decisions, constraints, files, acceptance, risks — dowolne pole
`transcript` na zadaniu jest po cichu pomijane, nie trafia do promptu) i
uruchamia go — `claude -p`, `codex exec`, albo zwykłe polecenie shell, zależnie
od `execution.executor`.

## Kompromisy

## Dalej
