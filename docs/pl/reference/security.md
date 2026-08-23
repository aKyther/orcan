# Bezpieczeństwo

## Limity izolacji

Orcan to wygodna izolacja dla **jednego zaufanego użytkownika na własnej
maszynie**, **nie** twarda granica multi-tenant.

- Bind mounty dają kontenerowi zapis do Twoich projektów
- `orcan up --with-docker` montuje `/var/run/docker.sock` → kontrola hostowego
  Docker Engine (efektywnie zasięg na poziomie hosta dla każdego, kto może
  odpalić Dockera)
- `orcan up --with-git` montuje hostowy `~/.ssh` (tylko odczyt) i może montować
  socket agenta SSH
- `orcan up --with-network NAME` dołącza do istniejącej sieci Docker →
  reachability sieciowa do tego, co na niej jest, ale **bez** socketa i
  **bez** kontroli hostowego Dockera

Reguły agentów i pliki permissions Cursor/Claude prowadzą zachowanie. To
**nie** jest sandbox.

## Drabinka możliwości (świadome kompromisy)

Wybieraj najsłabszą flagę, która wystarcza:

| Potrzeba | Flaga | Kompromis |
| --- | --- | --- |
| Tylko kontener lokalny (`orcan enter`) | *(brak)* — domyślne `orcan up` | Najmniejszy blast radius — bez publikacji portu ttyd |
| Terminal w przeglądarce (zdalnie / telefon) | `--with-ttyd` | Publikuje ttyd (`TTYD_BIND` domyślnie loopback); zdalnie preferuj Tailscale |
| Dojście do innego stacka Compose po nazwie/IP | `--with-network NAME` | Tylko sieć — **wyklucza się z `--with-docker`** |
| Nested `docker` / Compose wobec engine hosta | `--with-docker` | **Świadomie wysokie ryzyko** — opt-in; **wyklucza się z `--with-network`** |
| `git push` / `pull` po SSH z kontenera | `--with-git` | Klucze / agent w kontenerze — opt-in; łączy się z dowolnym trybem powyżej |

!!! warning
    Używaj `orcan up --with-docker` tylko gdy potrzebujesz Docker-from-Docker.
    Preferuj zwykłe `orcan up` albo `--with-network`, gdy nie potrzebujesz
    socketa. Flaga istnieje po to, żeby **Ty** świadomie przyjęliście to
    ryzyko; Orcan wypisuje ostrzeżenie przy starcie.

!!! warning
    Używaj `orcan up --with-git` tylko gdy potrzebujesz push/pull z kontenera.
    Udostępnia to kontenerowi klucze SSH (i agenta).

Nie ma bezpiecznego zamiennika zamontowanego socketa Dockera, który nadal
daje pełną kontrolę nad engine. Jeśli wystarczy reachability — użyj
`--with-network`.
`--with-docker` i `--with-network` nie łączą się w jednym `orcan up`.

## Kompromisy layoutu mountów

Stabilne bindy służą temu, żeby **dynamicznie zmieniać workspace’y i projekty
bez recreate kontenera**. To celowe:

| Bind | Rola | Kompromis |
| --- | --- | --- |
| `$ORCAN_PROJECTS_ROOT` (domyślnie `…/sandbox`) | Kotwica managed klonów i `.worktrees/` | Wszystko pod sandboxem widać w kontenerze — jeden stabilny mount, bez recreate przy dodaniu checkoutu |
| `$ORCAN_HOME/workspaces/` → `/home/developer/workspaces/` | Korzenie UX workspace’ów (symlinki, context pack, inbox) | **Wszystkie** skonfigurowane workspace’y dzielą jeden parent mount — agent w workspace A może widzieć ścieżki workspace B. To umożliwia dodawanie/usuwanie workspace’ów w runtime |
| `$ORCAN_DATA/context/` | Store Context Assertions (git) | **Nie** montowany do kontenera — agenci tylko zrzucają do inboxu workspace; `orcan sync` na hoście importuje |

!!! warning
    Usunięcie workspace'u z configu kasuje całe jego drzewo na dysku przy
    najbliższym reconcile (`orcan-runtime-reconcile` albo boot kontenera) —
    nie tylko zarządzane symlinki. Wszystko pod tym katalogiem, czego jeszcze
    nie zsynchronizowano — `.orcan/session-brief.md`, zadania agent-inbox,
    niezsynchronizowane zrzuty Context Assertions — ginie razem z nim, bez
    cofnięcia. To celowe (bez kwarantanny), nie błąd — zobacz `reconcile.py`.

Orcan zakłada **model zaufania single-user** (Ty + agenci na Twoim hoście).
JSON w inboxie nie jest kryptograficznie podpisany; uszkodzone zrzuty idą do
kwarantanny, a do store’u trafia tylko to, co człowiek zaakceptuje / odrzuci.
Zobacz [Context Assertions](../ideas/context-assertions.md).

## Skrzynka agentów / wykonywanie zadań

[Skrzynka agentów](../ideas/agent-inbox.md) (`<workspace_root>/.orcan/tasks/`)
przekazuje ustrukturyzowane manifesty zadań od agenta planującego do agenta
wykonującego. Ten sam model zaufania co Context Assertions — niepodpisane
pliki JSON, jeden host:

- Domyślna polityka (`approve`) wymaga ludzkiego `orcan-inbox approve`, zanim
  zadanie da się podjąć. `draft` nigdy nie jest podejmowalne. Obie są
  bezpieczne bez nadzoru.
- `policy: auto` pomija tę bramkę — zadanie jest podejmowalne od razu po
  zaproponowaniu.
- `execution.executor: shell` uruchamia `execution.command` jako prawdziwe
  polecenie shell w katalogu głównym workspace'u. **Kombinacja `auto` +
  `shell` oznacza, że plik zadania jest wykonywany bez żadnego kroku człowieka
  pomiędzy** — traktuj wszystko, co potrafi zapisać do
  `.orcan/tasks/inbox/` (skrypt, inny agent, współdzielony filesystem) jako
  coś, co może uruchamiać polecenia na Twoim hoście.
- `orcan-inbox watch` działa tylko wtedy, gdy sam go uruchomisz. Nic domyślnie
  nie odpytuje skrzynki.

Jeśli nie potrzebujesz wykonania bez nadzoru, zostań przy domyślnym `approve`
i przeglądaj każde zadanie przed akceptacją.

## Dane na hoście

Logowania i cache leżą pod `$ORCAN_DATA` (domyślnie `~/.config/orcan`). Traktuj
ten katalog jako wrażliwy.

`orcan uninstall --purge-data` usuwa go po potwierdzeniu.

## Terminal w przeglądarce

**Rekomendowany dostęp zdalny:** zostaw publikację na loopback i dochodź do
maszyny przez **Tailscale** (albo inny prywatny VPN), potem otwórz
`http://localhost:<port>` na tym hoście. To domyślna rekomendacja produktu.

!!! warning
    Domyślnie port ttyd jest publikowany **tylko na loopback**
    (`TTYD_BIND=127.0.0.1`). ttyd **nie ma autentykacji**, dopóki nie ustawisz
    `TTYD_CREDENTIAL=user:password` w `.env`. Nie wystawiaj portu do
    publicznego Internetu bez auth i TLS.

Opcjonalne HTTP basic auth (`TTYD_CREDENTIAL`) jest wspierane, gdy musisz
publikować poza loopback (`TTYD_BIND=0.0.0.0`). Najpierw Tailscale; hasło traktuj
jako warstwę dodatkową, nie główną historię dostępu zdalnego.

Config: `ttyd.bind` w `orcan.config.json` (domyślnie `127.0.0.1`) → `TTYD_BIND`
przez `orcan sync`. Credentials tylko w env, żeby sekrety nie trafiały do
commitowanego configu.

## Czego nie robić

- Nie startuj kontenerów Orcana z `--privileged`
- Nie montuj `/`, `/home`, `/etc`, `/usr`, `/var`, `/opt` ani `/root` (ani
  ścieżek pod tymi drzewami, poza normalnymi projektami `/home/<user>/…`) jako
  `PROJECT_DIR`
- Nie commituj `.env`, tokenów ani zawartości `ORCAN_DATA`
- Nie uruchamiaj `docker system prune` jako części normalnych workflowów Orcana

## Zobacz też

- [Docker](docker.md)
- [Model mentalny](../ideas/mental-model.md) — sandbox jako kotwica, mounty workspace
- [Workflowy](../guides/workflows.md)
- [Zmienne środowiskowe](environment.md)
