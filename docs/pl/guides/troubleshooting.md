# Rozwiązywanie problemów

## Co to robi

Wypisuje częste awarie i jak je diagnozować na **hoście**.

## Zanim zaczniesz

Z instalacji Orcana (albo checkoutu gita):

```bash
orcan doctor
orcan context show
docker compose -f docker-compose.yml -f .orcan/compose-projects.generated.yml config
```

`docker compose config` wypisuje rozwiązany plik Compose (wymaga wygenerowanych plików `.orcan` z `orcan sync`).

## Terminal w przeglądarce się nie otwiera

1. Potwierdź, że kontener działa: `orcan logs`
2. Potwierdź URL: `orcan url` (domyślnie `http://localhost:7681`)
3. Jeśli port jest zajęty, zmień `ttyd.host_port` w `orcan.config.json`, potem `orcan sync` i odtwórz kontener

## Launcher jest pusty / złe projekty

1. Sprawdź, że `orcan.config.json` ma `workspaces` z bezwzględnymi `projects[].path`
2. Uruchom `orcan sync` (cele terminal nie odświeżają konfiguracji)
3. `orcan down && orcan up`

**Nie** przekazuj `PROJECT_DIR=…` przy `orcan up`. Przełączaj projekty przez edycję konfiguracji + `orcan sync`.

## `orcan sync` / `require-generated` się wywala

| Komunikat | Rozwiązanie |
| --- | --- |
| Brak `.env` | `orcan sync` lub `orcan init` |
| Wygenerowane pliki nieaktualne | Konfiguracja nowsza niż `.orcan/*` — uruchom `orcan sync` |
| Nieprawidłowy `PROJECT_DIR` | Ścieżka bezwzględna; unikaj `/`, `/home`, `/etc` |

## Brak agenta lub Claude

- Pełny obraz: `orcan build`, potem odtwórz kontener
- Tylko Claude: `orcan build --claude`, potem `IMAGE_LOCAL=orcan:<VERSION>-claude orcan up` — `agent` nie jest zainstalowany (oczekiwane)
- Auth leży pod `$ORCAN_DATA` (`~/.config/orcan`)

## Błędy socketa Dockera wewnątrz kontenera

Użyj `orcan up --with-docker`. Zwykły `orcan up` nie montuje socketa.

## Path parity / zagnieżdżony Compose nie działa

Zobacz [Path parity](../concepts/path-parity.md). Potwierdź mounty przez `orcan context show`.

## Klawisze tmux nie działają w przeglądarce

Ustaw fokus na panelu terminala. Użyj prefixu tmux (domyślne ustawienia obrazu pod `/etc/tmux`). Prawy przycisk myszy otwiera menu przeglądarki (menu myszy tmux są celowo odwiązane).

## Długi URL się zawija i trudno kliknąć

Autodetekcja linków w przeglądarce/terminalu zwykle łapie **jeden wiersz ekranu**. Soft-wrap `https://…` tnie URL na kawałki, więc klik nie otwiera całości.

Workaround (domyślnie w obrazie): **prefix `u`** (`C-Space`, potem `u`) — skleja zawinięte linie w panelu i kopiuje URL (menu, gdy jest kilka). Wklej prefixem `]` albo skrótem przeglądarki.

Aplikacje emitujące hiperłącza OSC 8 mogą zostać klikalne mimo zawinięcia, gdy zewnętrzny terminal to obsługuje; zwykły wydrukowany tekst nadal wymaga prefix `u`.

## „Wyłącz tmux” / tylko zwykły shell

tmux startuje launcher (`cursor-ttyd` → `cursor-launcher`), a nie blok w `50-orcan-shell.zsh`. Dziś nie ma obsługiwanego przełącznika „wyłącz tmux”. Nadal możesz otwierać dodatkowe shelle w oknach tmux.

## Hostowy `~/.gitconfig` stał się katalogiem

Starszy układ mógł utworzyć katalog należący do roota. Napraw właściciela albo zastąp zwykłym plikiem, potem zaktualizuj Orcana i odtwórz kontener.

## Checklista diagnostyczna

```bash
orcan doctor
orcan context show
docker compose -f docker-compose.yml -f .orcan/compose-projects.generated.yml config
orcan logs
```

Więcej o limitach: [Bezpieczeństwo](../reference/security.md).

## Zobacz też

- [Typowe workflowy](workflows.md)
- [Path parity](../concepts/path-parity.md)
- [Bezpieczeństwo](../reference/security.md)
- [FAQ](../faq.md)
