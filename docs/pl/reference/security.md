# Bezpieczeństwo

## Limity izolacji

Orcan to wygodna izolacja, **nie** twarda granica bezpieczeństwa.

- Bind mounty dają kontenerowi zapis do Twoich projektów
- `make terminal-docker` montuje `/var/run/docker.sock` → silny dostęp do hosta

!!! warning
    Używaj `terminal-docker` tylko gdy potrzebujesz Docker-from-Docker. Preferuj `make terminal`, gdy nie potrzebujesz.

## Dane na hoście

Logowania i cache leżą pod `$ORCAN_DATA` (domyślnie `~/.config/orcan`). Traktuj ten katalog jako wrażliwy.

`make clean-data` usuwa go po potwierdzeniu.

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
