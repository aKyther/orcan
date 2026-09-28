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
warstwa połączenia Rust posiada trzy stałe wywołania procesów i waliduje
identyfikator celu przed uruchomieniem. Uwierzytelnianie SSH i weryfikacja hosta
pozostają po stronie OpenSSH oraz `ssh-agent` i `known_hosts` użytkownika.
