# Rozwiązywanie problemów

## Co to robi

Wypisuje częste awarie i jak je diagnozować na **hoście**.

## Zanim zaczniesz

Z instalacji Orcana (albo checkoutu gita):

```bash
orcan doctor
orcan context show
docker compose -f docker-compose.yml -f mounts/compose-projects.generated.yml config
```

`docker compose config` wypisuje rozwiązany plik Compose (wymaga wygenerowanych plików `mounts/` z `orcan sync`).

## Terminal w przeglądarce się nie otwiera

Wymaga `orcan up --with-ttyd` (sam `orcan up` = tylko lokalnie — użyj `orcan enter`).

1. Potwierdź, że kontener działa: `orcan logs`
2. Potwierdź, że ttyd jest włączone: `orcan doctor` (sekcja Runtime) albo `orcan url`
3. Potwierdź URL: `orcan url` (przy `TTYD_BIND=0.0.0.0` to `http://localhost:7681`)
4. Jeśli port jest zajęty, zmień `ttyd.host_port` w `orcan.config.json`, potem `orcan sync` i `orcan down && orcan up --with-ttyd`

## Częste „reconnecting” na telefonie / LTE

Handoffy sieci komórkowej zrywają WebSocket ttyd — to oczekiwane. Procesy w tmux przeżywają.

- Po reconnect `agent-launcher` auto-reattachuje ostatni workspace (Enter w trakcie odliczania → menu).
- Wyłączenie auto-reattach: `ORCAN_AUTO_REATTACH=0` w kontenerze.
- Preferuj Tailscale / VPN zamiast publicznego portu; na LTE i tak bywają krótkie reconnecty.
- Opcjonalnie: `ttyd.ping_interval` / `TTYD_PING_INTERVAL` (domyślnie `20`).

## Rozjeżdżający się layout, gdy otwiera się klawiatura ekranowa (telefon / tablet)

Znane ograniczenie samego ttyd, nie konfiguracji orcana: wbudowany frontend
xterm.js w ttyd nie synchronizuje kontenera terminala z `visualViewport`
przeglądarki, gdy otwiera/zamyka się mobilna klawiatura ekranowa — może
objawiać się jako zmiana rozmiaru/zoom, białe pole na dole albo scroll
niezgodny z widocznym ekranem. Śledzone upstream:
[tsl0922/ttyd#1531](https://github.com/tsl0922/ttyd/pull/1531) (otwarty, nie
scalony; żadne wydanie ttyd tego jeszcze nie ma — przypięte `1.7.7` w
`Dockerfile` to wciąż najnowsze wydanie, więc nie ma na co zbumpować).

Obejścia do czasu scalenia upstream:

- Fizyczna/Bluetooth klawiatura — nie wywołuje klawiatury ekranowej.
- Orientacja pozioma zwykle jest stabilniejsza niż pionowa.
- Jeśli layout zostaje rozjechany po zamknięciu klawiatury, dotknij/kliknij
  raz terminal albo przeładuj stronę.

## Launcher jest pusty / złe projekty

1. Sprawdź, że `orcan.config.json` ma `workspaces` z bezwzględnymi `projects[].path`
2. Uruchom `orcan sync` (cele terminal nie odświeżają konfiguracji). Sync robi reconcile meta workspace'u na hoście nawet gdy kontener stoi; live reconcile w kontenerze, gdy jest w górze.
3. `orcan down && orcan up`, gdy `orcan doctor` zgłasza ścieżkę niewidoczną w kontenerze.

Jeśli projekt leżał bezpośrednio pod folderem workspace'u (katalog zamiast symlinku), `orcan sync` przenosi go do `*.orcan-reconcile-bak` i odtwarza symlink (live reconcile w kontenerze). Szukaj w outputcie sync `relocated stale checkout dirs`.

**Nie** przekazuj `PROJECT_DIR=…` przy `orcan up`. Przełączaj projekty przez edycję konfiguracji + `orcan sync`.

## `orcan sync` / `require-generated` się wywala

| Komunikat | Rozwiązanie |
| --- | --- |
| Brak `.env` | `orcan sync` lub `orcan init` |
| Wygenerowane pliki nieaktualne | Konfiguracja nowsza niż `mounts/*` — uruchom `orcan sync` |
| Nieprawidłowy `PROJECT_DIR` | Ścieżka bezwzględna; unikaj `/`, `/home`, `/etc` |

## Brak agenta lub Claude

- Zbuduj potrzebny zestaw, np. `orcan build --agent codex`, potem odtwórz kontener
- Dla Claude użyj `orcan build --agent claude`; zainstalowanych klientów pokazuje `orcan status`
- Auth leży pod `$ORCAN_DATA` (`~/.config/orcan`)

## Błędy socketa Dockera wewnątrz kontenera

Użyj `orcan up --with-docker`. Zwykły `orcan up` nie montuje socketa.

Jeśli w kontenerze `docker` wymaga `sudo`, GID socketa na hoście musi zgadzać się z `DOCKER_GID` w `.env`:

```bash
stat -c '%g' /var/run/docker.sock
grep DOCKER_GID "${ORCAN_HOME:-$HOME/.config/orcan}/.env"
orcan sync && orcan down && orcan up --with-docker
```

`orcan sync` ponownie wykrywa GID socketa z hosta (nie zostawiaj starego `999` z `.env.example`).

## Path parity / zagnieżdżony Compose nie działa

Zobacz [Path parity](../concepts/path-parity.md). Potwierdź mounty przez `orcan context show`.

## Klawisze tmux nie działają w przeglądarce

## Osadzony tmux nie zmienia rozmiaru z przeglądarką

PTY cockpitu musi mieć controlling tty, żeby resize dostarczył SIGWINCH do tmux. Naprawione w bieżącym cockpicie (`TIOCSCTTY` + `on_resize`). Jeśli pane zostaje przy rozmiarze z attach po resize przeglądarki: zaktualizuj obraz (`orcan build` / `make dev-restart`) i zrób hard-refresh karty. Szczegóły: [Terminal UI — cockpit](terminal-ui.md#cockpit-browser).

## Długi URL się zawija i trudno kliknąć

Autodetekcja linków w przeglądarce/terminalu zwykle łapie **jeden wiersz ekranu**. Soft-wrap `https://…` tnie URL na kawałki, więc klik nie otwiera całości.

Workaround (domyślnie w obrazie): **prefix `u`** (`C-Space`, potem `u`) — skleja zawinięte linie w panelu i kopiuje URL (menu, gdy jest kilka). Wklej prefixem `]` albo skrótem przeglądarki.

Aplikacje emitujące hiperłącza OSC 8 mogą zostać klikalne mimo zawinięcia, gdy zewnętrzny terminal to obsługuje; zwykły wydrukowany tekst nadal wymaga prefix `u`.

## „Wyłącz tmux” / tylko zwykły shell

tmux startuje launcher (`cursor-ttyd` → `agent-launcher`), a nie blok w `50-orcan-shell.zsh`. Dziś nie ma obsługiwanego przełącznika „wyłącz tmux”. Nadal możesz otwierać dodatkowe shelle w oknach tmux.

## Hostowy `~/.gitconfig` stał się katalogiem

Starszy układ mógł utworzyć katalog należący do roota. Napraw właściciela albo zastąp zwykłym plikiem, potem zaktualizuj Orcana i odtwórz kontener.

Orcan **nie** montuje hostowego `~/.gitconfig`. Zamiast tego `orcan sync` kopiuje `user.name` / `user.email` do `.env` (`GIT_AUTHOR_*` / `GIT_COMMITTER_*`), żeby commity w kontenerze miały tego samego autora co na hoście.

Do `git push` / `git pull` po SSH:

```bash
orcan up --with-git
# razem z DinD:
orcan up --with-docker --with-git
```

Montuje hostowy `~/.ssh` tylko do odczytu (oraz agenta SSH, gdy `SSH_AUTH_SOCK` jest ustawiony). Zwykłe `orcan up` tego nie robi.

## Po upgrade do 2.0 został `space/` jako `root:root`

W 2.0 managed projects root zmienił nazwę `space/` → `sandbox/`. Jeśli po
rename `.env` nadal ma `ORCAN_PROJECTS_ROOT=…/space`, następne `orcan up`
montuje **nieistniejącą** ścieżkę na hoście i daemon Dockera tworzy ją jako
`root:root`. `orcan doctor` to zgłasza (check legacy `space/`).

```bash
orcan down
# pusty leftover (typowy przypadek):
sudo rmdir "${ORCAN_DATA:-$HOME/.config/orcan}/space"
# albo, jeśli nadal są Twoje checkouty:
bash "${ORCAN_ROOT}/scripts/migrations/rename-space-to-sandbox.sh"
orcan sync && orcan down && orcan up
```

## Checklista diagnostyczna

```bash
orcan doctor
orcan context show
docker compose -f docker-compose.yml -f mounts/compose-projects.generated.yml config
orcan logs
```

## Zobacz też

- [Typowe workflowy](workflows.md)
- [Path parity](../concepts/path-parity.md)
- [Bezpieczeństwo](../reference/security.md)
- [FAQ](../faq.md)
