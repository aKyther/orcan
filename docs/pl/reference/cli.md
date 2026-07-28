# Referencja CLI

Publiczny interfejs Orcan to komenda **`orcan`** (Bash). Cele Make zostają tylko dla **maintainerów** (docs, testy, release).

## Instalacja

```bash
curl -fsSL https://raw.githubusercontent.com/aKyther/orcan/main/install.sh | bash
```

| Ścieżka | Rola |
| --- | --- |
| `~/.local/share/orcan` | Klon gita (`ORCAN_ROOT`) |
| `~/.local/bin/orcan` | Launcher |
| `~/.config/orcan/home` | Config + `.env` + `.orcan/*` (`ORCAN_HOME`) — **zawsze** domyślne |
| `~/.config/orcan` | Dane narzędzi / loginy (`ORCAN_DATA`) |

Nadpisz tylko gdy trzeba: `ORCAN_HOME=/path` albo `ORCAN_USE_CWD=1` (użyj `./orcan.config.json` w bieżącym katalogu).

## Zależności hosta

Komenda `orcan` to **Bash**, ale konfiguracja na hoście idzie przez **Python 3** (sama stdlib — bez pip/venv):

| Potrzeba | Używane przez |
| --- | --- |
| Bash, Git | CLI, instalacja, `orcan update` |
| **Python 3** | `orcan sync`, `init`, `context` (wizard / show / add) |
| Docker Compose v2 | `orcan build`, `up`, `down`, … |

Sprawdź: `orcan doctor`. Szczegóły: [Instalacja](../getting-started/installation.md).

## Komendy

| Komenda | Rola |
| --- | --- |
| `orcan init [PATH]` | Pierwszy start: scaffold, sync, show |
| `orcan sync` | Zastosuj `orcan.config.json` → `.env` + `.orcan/*` |
| `orcan context show` | Lista workspace'ów + path parity |
| `orcan context wizard` | Interaktywny edytor konfiguracji |
| `orcan context add PATH` | Dodaj projekt (`--workspace`, `--force`) |
| `orcan up [--with-docker]` | Start terminala (socket tylko z `--with-docker`); podpowiada, gdy jest nowszy release |
| `orcan down` | Stop kontenerów |
| `orcan build [--claude|--cursor] [--force] [--no-cache]` | Obaj agenci → `orcan:latest` + `orcan:<VERSION>` (pull lub build). `--claude` / `--cursor` → `orcan:<VERSION>-claude\|cursor` (bez pull; nie nadpisuje `latest`). Nigdy nie publikuje |
| `orcan pull` | Pull obu agentów `orcan:<VERSION>` → `orcan:latest` |
| `orcan publish` | Push obu agentów `orcan:latest` (**ręcznie**; nie `-claude`/`-cursor`) |
| `orcan url` | URL terminala |
| `orcan logs` | Logi |
| `orcan update [--release\|--main]` | Najnowszy tag release `vX.Y.Z` (domyślnie); `--main` = bleeding edge |
| `orcan doctor` | Raport zdrowia hosta / configu |
| `orcan uninstall [--purge-data]` | Usuń CLI (opcjonalnie `ORCAN_DATA`) |
| `orcan version` / `orcan help` | Wersja / pomoc |

### Opcjonalne

| Komenda | Rola |
| --- | --- |
| `orcan seed [--all] [--dry-run]` | Szablony/ignores w checkoutach git — **rzadko potrzebne**; pack workspace wystarcza |

## Rytuał

```bash
orcan init
orcan build
orcan up
```

Po edycji konfiguracji:

```bash
# edytuj ~/.config/orcan/home/orcan.config.json
orcan sync
orcan down && orcan up
```

`orcan up` **nie** uruchamia `sync`.

## Make dla maintainerów

Z checkoutu gita: `make validate`, `make test-host`, `make docs*`, `make release*`, `make registry-*`. Zobacz [Development](../development/overview.md).
