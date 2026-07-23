# Rozwiązywanie problemów

## Co to robi

Wypisuje częste awarie i jak je diagnozować na **hoście**.

## Zanim zaczniesz

Z repozytorium Orcana:

```bash
make validate
make path-check
make config
```

`make config` wypisuje rozwiązany plik Compose (wymaga wygenerowanych plików `.orcan`).

## Terminal w przeglądarce się nie otwiera

1. Potwierdź, że kontener działa: `make logs`
2. Potwierdź URL: `make terminal-url` (domyślnie `http://localhost:7681`)
3. Jeśli port jest zajęty, zmień `ttyd.host_port` w `orcan.config.json`, potem `make env` i odtwórz kontener

## Launcher jest pusty / złe projekty

1. Sprawdź, że `orcan.config.json` ma `workspaces` z bezwzględnymi `projects[].path`
2. Uruchom `make env` (cele terminal nie odświeżają konfiguracji)
3. `make down && make terminal-docker`

**Nie** przekazuj `PROJECT_DIR=…` przy `make terminal`. Przełączaj projekty przez edycję konfiguracji + `make env`.

## `make env` / `require-generated` się wywala

| Komunikat | Rozwiązanie |
| --- | --- |
| Brak `.env` | `make env` lub `make setup` |
| Wygenerowane pliki nieaktualne | Konfiguracja nowsza niż `.orcan/*` — uruchom `make env` |
| Nieprawidłowy `PROJECT_DIR` | Ścieżka bezwzględna; unikaj `/`, `/home`, `/etc` |

## Brak agenta lub Claude

- Pełny obraz: `make build`, potem odtwórz kontener
- Tylko Claude: `IMAGE_LOCAL=orcan:claude` — `agent` nie jest zainstalowany (oczekiwane)
- Auth leży pod `$ORCAN_DATA` (`~/.config/orcan`)

## Błędy socketa Dockera wewnątrz kontenera

Użyj `make terminal-docker`. Zwykły `make terminal` nie montuje socketa.

## Path parity / zagnieżdżony Compose nie działa

Zobacz [Path parity](../concepts/path-parity.md). Potwierdź mounty przez `make path-check`.

## Klawisze tmux nie działają w przeglądarce

Ustaw fokus na panelu terminala. Użyj prefixu tmux (domyślne ustawienia obrazu pod `/etc/tmux`). Prawy przycisk myszy otwiera menu przeglądarki (menu myszy tmux są celowo odwiązane).

## „Wyłącz tmux” / tylko zwykły shell

tmux startuje launcher (`cursor-ttyd` → `cursor-launcher`), a nie blok w `50-orcan-shell.zsh`. Dziś nie ma obsługiwanego przełącznika „wyłącz tmux”. Nadal możesz otwierać dodatkowe shelle w oknach tmux.

## Hostowy `~/.gitconfig` stał się katalogiem

Starszy układ mógł utworzyć katalog należący do roota. Napraw właściciela albo zastąp zwykłym plikiem, potem zaktualizuj Orcana i odtwórz kontener.

## Checklista diagnostyczna

```bash
make validate
make path-check
docker compose -f docker-compose.yml -f .orcan/compose-projects.generated.yml config
make logs
```

Więcej o limitach: [Bezpieczeństwo](../reference/security.md).

## Zobacz też

- [Typowe workflowy](workflows.md)
- [Path parity](../concepts/path-parity.md)
- [Bezpieczeństwo](../reference/security.md)
- [FAQ](../faq.md)
