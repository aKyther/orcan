---
tags:
  - concept
---

# Orcan Studio

Orcan Studio jest natywną aplikacją desktopową do budowania i sprawdzania
kontekstu Orcan. Orcan Sandbox pozostaje runtime'em, który zarządza Dockerem,
managed project root, mountami, workspace'ami i live reconcile.

Studio ma trzy transporty:

- **Local** na Linuxie i macOS: uruchamia zainstalowaną komendę `orcan`.
- **WSL2** na Windows: uruchamia `orcan` w wybranej dystrybucji przez
  `wsl.exe`.
- **SSH**: uruchamia ten sam wersjonowany protokół Orcan Studio przez
  konfigurację OpenSSH użytkownika.

Pierwszą operacją protokołu jest `orcan studio probe --json`. Jest tylko do
odczytu. Jest autorytatywnym snapshotem Sandboxa: przy każdym reconnect Studio
odświeża ścieżki, rewizję konfiguracji, managed root, workspace'y, projekty,
mounty i stan runtime'u zamiast uznawać zapamiętany domyślny katalog desktopowy
za prawdę. Studio wymaga obsługiwanej wersji deklarowanego protokołu
`orcan-studio`, zanim udostępni przyszłe akcje edycji kontekstu.

Probe jest wersjonowanym kontraktem sterowania, a nie przeglądarką plików.
Oprócz snapshotu Orcan zwraca `control.operations` (czy akcja jest dostępna i
dlaczego) oraz `control.settings` (bezpieczną wartość do wyświetlenia, stan
`editable` albo `locked` i opcjonalną akcję Studio). Studio renderuje ten
kontrakt; nie szuka zdalnych plików konfiguracji ani nie zakłada, że zmiana
Dockera jest już aktywna.

Studio edytuje kontekst tylko wtedy, gdy probe wskazuje aktywny
`orcan.config.json` jako źródło. Zsynchronizowany indeks workspace'ów nadal
jest przydatny do podglądu, ale pozostaje tylko do odczytu: Studio blokuje
zmianę nazwy, odłączanie i tworzenie worktree, dopóki nie połączy się z
instancją Orcan, która posiada konfigurację.

Każda Enclave ma zębatkę konfiguracji. Panel rozdziela akcje, które Studio może
bezpiecznie wykonać (plany kontekstu i cykl życia kontenera), od raportowanych,
zablokowanych faktów: zasobów kontenera, narzędzi agentów z obrazu,
chronionych wartości środowiska, ścieżek zarządzanych i ekspozycji startowej.
Zablokowane wartości środowiska celowo nie są ani wyświetlane, ani edytowane w
Studio.

Każdy projekt Git w Contexts ma przy sobie stan parenta zgłoszonego przez
Orcan. Studio pokazuje clean/dirty i ahead/behind bezpośrednio przy projekcie,
sprawdza śledzony branch parenta względem `origin`, a następnie wymaga
potwierdzenia przed `git pull --ff-only`. Aktualizacja parenta nigdy nie
przepisuje zależnych worktree; ich branche można później zrebase'ować ręcznie
lub przez agenta.

Import repozytorium przyjmuje URL Git i parent directory zgłoszony przez Orcan
pod zarządzanym projects rootem. Orcan wyprowadza nazwę nowego checkoutu z URL
i waliduje cel; Studio nigdy nie przyjmuje dowolnej ścieżki. Uwierzytelnienie
Git pozostaje na hoście Orcan (na przykład jego agencie SSH), a Studio pokazuje
jego dostępność bez odczytywania kluczy ani sekretów.

Studio zapisuje profile ponownego połączenia w natywnym katalogu danych
aplikacji. Profil ma nazwę, metadane transportu oraz dane SSH, takie jak
użytkownik albo ścieżka klucza prywatnego. Hasła i passphrase kluczy nie trafiają
do pliku profilu; należą do systemowego magazynu poświadczeń.

Poświadczenia są osobnymi rekordami wielokrotnego użytku: nazwana ścieżka klucza
prywatnego albo hasło, do których może odwoływać się wiele profili, a każdy
profil trzyma własny adres i użytkownika. Nie można usunąć poświadczenia, którego
używa jakiś profil. UI Studio nazywa połączony Sandbox **Enclave** (izolowane
środowisko Orcana) i prowadzi przez Credentials & keys → Profiles → Enclaves;
żaden widok instancji nie pojawia się przed udanym probe.

Przynależność do workspace'ów edytuje się na mapie Enclave'a: przeciągnięcie
projektu na workspace (albo na „New workspace”) prosi Orcana o plan przez
`orcan studio settings`, pokazuje go do potwierdzenia, stosuje na tym
Enclavie (systemowe SSH albo natywne SSH z zapisanym poświadczeniem), a potem
proponuje `orcan sync`. Usunięcie projektu z workspace'u nigdy nie kasuje plików.

Aplikacja używa Rust + Tauri. UI nie ma uprawnienia do dowolnego shella:
warstwa połączenia Rust ma stałe komendy i waliduje identyfikator celu.
Profile z hasłem i kluczem prywatnym używają natywnego SSH oraz sprawdzają klucz
hosta wobec lokalnego pliku `known_hosts`. Nieznany albo zmieniony klucz jest
odrzucany — Studio nigdy nie ufa mu automatycznie. Ich cel to bezpośredni
`host` albo `host:port`; profile z agentem SSH nadal używają konfiguracji
systemowego OpenSSH.
