# Path parity

## Co to znaczy

**Path parity** = ta sama ścieżka bezwzględna na hoście i wewnątrz kontenera Orcana.

Przykład: ścieżka hosta `/home/you/code/app` jest montowana pod `/home/you/code/app` w kontenerze (nie pod `/workspace/app`).

## Dlaczego to ważne

Gdy uruchamiasz Dockera **wewnątrz** Orcana (`make terminal-docker`), to **hostowy** daemon Dockera rozwiązuje bind mounty. Gdyby ścieżki się różniły, zagnieżdżony Compose montowałby złe katalogi.

## Jak Orcan to robi

`make env` zapisuje mounty do `.orcan/compose-projects.generated.yml`:

```yaml
# conceptual
volumes:
  - /absolute/path/to/app:/absolute/path/to/app
```

UX workspace'ów nadal używa krótkich symlinków pod `/home/developer/workspaces/<name>/`.

## Sprawdzenie

```bash
make path-check
```

Test integracyjny (wymaga socketa Dockera):

```bash
make test-path-parity
```

## Częste błędy

| Błąd | Skutek |
| --- | --- |
| Względne `projects[].path` | Odrzucone lub zepsute mounty |
| Założenie `/workspace` | Stary wzorzec — nieużywany |
| Ręczna edycja wygenerowanego Compose | Nadpisane przez `make env` |

## Zobacz też

- [Workspaces](workspaces.md)
- [Architektura](architecture.md)
- [Docker](../reference/docker.md)
- [Rozwiązywanie problemów](../guides/troubleshooting.md)
