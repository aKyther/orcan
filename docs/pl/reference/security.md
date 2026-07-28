# Bezpieczeństwo

## Limity izolacji

Orcan to wygodna izolacja, **nie** twarda granica bezpieczeństwa.

- Bind mounty dają kontenerowi zapis do Twoich projektów
- `orcan up --with-docker` montuje `/var/run/docker.sock` → silny dostęp do hosta
- `orcan up --with-git` montuje hostowy `~/.ssh` (tylko odczyt) i może montować socket agenta SSH

!!! warning
    Używaj `orcan up --with-docker` tylko gdy potrzebujesz Docker-from-Docker. Preferuj zwykłe `orcan up` bez socketa.

!!! warning
    Używaj `orcan up --with-git` tylko gdy potrzebujesz push/pull z kontenera. Udostępnia to kontenerowi klucze SSH (i agenta).

## Dane na hoście

Logowania i cache leżą pod `$ORCAN_DATA` (domyślnie `~/.config/orcan`). Traktuj ten katalog jako wrażliwy.

`orcan uninstall --purge-data` usuwa go po potwierdzeniu.

## Terminal w przeglądarce

!!! warning
    ttyd w domyślnej konfiguracji **nie ma autentykacji**. Bindować do localhost albo schować za Tailscale / VPN. Nie wystawiaj portu do publicznego Internetu bez auth i TLS.

## Czego nie robić

- Nie startuj kontenerów Orcana z `--privileged`
- Nie montuj `/`, `/home` ani `/etc` jako `PROJECT_DIR`
- Nie commituj `.env`, tokenów ani zawartości `ORCAN_DATA`
- Nie uruchamiaj `docker system prune` jako części normalnych workflowów Orcana

## Zobacz też

- [Docker](docker.md)
- [Rozwiązywanie problemów](../guides/troubleshooting.md)
- [Typowe workflowy](../guides/workflows.md)
- [Zmienne środowiskowe](environment.md)
