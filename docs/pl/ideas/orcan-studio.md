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

Studio zapisuje profile ponownego połączenia w natywnym katalogu danych
aplikacji. Profil ma nazwę, metadane transportu oraz dane SSH, takie jak
użytkownik albo ścieżka klucza prywatnego. Hasła i passphrase kluczy nie trafiają
do pliku profilu; należą do systemowego magazynu poświadczeń.

Aplikacja używa Rust + Tauri. UI nie ma uprawnienia do dowolnego shella:
warstwa połączenia Rust ma stałe komendy i waliduje identyfikator celu.
Profile z hasłem i kluczem prywatnym używają natywnego SSH oraz sprawdzają klucz
hosta wobec lokalnego pliku `known_hosts`. Nieznany albo zmieniony klucz jest
odrzucany — Studio nigdy nie ufa mu automatycznie. Ich cel to bezpośredni
`host` albo `host:port`; profile z agentem SSH nadal używają konfiguracji
systemowego OpenSSH.
