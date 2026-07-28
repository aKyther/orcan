---
description: Path parity — te same ścieżki bezwzględne na hoście i w kontenerze Orcana oraz dlaczego potrzebuje tego zagnieżdżony Docker.
---

# Path parity

## Problem

Uruchamiasz Dockera **wewnątrz** kontenera Orcana (`orcan up`). Daemon, który tworzy zagnieżdżone kontenery, to nadal daemon **hosta**. Bind mounty są rozwiązywane na hoście.

Gdyby ścieżka w Orcanie była `/workspace/app`, a checkout na hoście `/home/you/code/app`, zagnieżdżony Compose zamontowałby zły katalog — albo nic.

## Dlaczego to boli

Zepsute zagnieżdżone buildy, puste volume'y i drogie w debugowaniu błędy „u mnie ścieżka działa, w kontenerze agenta nie”.

## Jak Orcan to rozwiązuje

**Path parity** oznacza tę samą ścieżkę bezwzględną na hoście i w kontenerze Orcana.

Przykład: host `/home/you/code/app` jest montowany jako `/home/you/code/app` w kontenerze (nie przepisywany na `/workspace/app`).

UX workspace'a nadal używa krótkich symlinków pod `/home/developer/workspaces/<name>/` do nawigacji. Mounty parity służą poprawności Docker-from-Docker. Zobacz [Model mentalny](../ideas/mental-model.md).

## Jak to działa

`orcan sync` zapisuje mounty do `.orcan/compose-projects.generated.yml`:

```yaml
# koncepcyjnie
volumes:
  - /absolute/path/to/app:/absolute/path/to/app
```

## Sprawdzenie (komendy na końcu)

```bash
orcan context show
```

Test integracyjny (wymaga socketa Dockera):

```bash
make test-path-parity
```

## Częste błędy

| Błąd | Skutek |
| --- | --- |
| Względne `projects[].path` | Odrzucenie lub zepsute mounty |
| Założenie `/workspace` | Stary wzorzec — nieużywany |
| Ręczna edycja wygenerowanego Compose | Nadpisane przez `orcan sync` |
