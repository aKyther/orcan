# Referencja konfiguracji

Plik hosta: `orcan.config.json` (tylko stdlib JSON).

Zastosuj przez `make env`. Egzekwowanie schematu jest w `scripts/repository/apply-config.py`.
Szkic maszynowy: [`orcan.config.schema.json`](https://github.com/aKyther/orcan/blob/main/orcan.config.schema.json).

## Klucze najwyższego poziomu

| Klucz | Wymagany | Opis |
| --- | --- | --- |
| `workspaces` | tak (niepusty) | Lista obiektów workspace |
| `tmux` | nie | Domyślny układ okien |
| `ttyd` | nie | Ustawienia terminala w przeglądarce |
| `resources` | nie | Limity kontenera (domyślnie **2** CPU / **4g** RAM — podnieś w configu w razie potrzeby) |

Legacy akceptowane i normalizowane: pojedynczy obiekt `workspace` albo top-level `projects[]` (jeden workspace).

## Obiekt workspace

| Klucz | Wymagany | Opis |
| --- | --- | --- |
| `name` | tak | Sesja tmux + `/home/developer/workspaces/<name>` |
| `enabled` | nie | Domyślnie true |
| `projects` | tak | Lista `{ name, path }` |

### Obiekt projektu

| Klucz | Wymagany | Opis |
| --- | --- | --- |
| `name` | tak | Nazwa symlinku pod workspace'em |
| `path` | tak | Bezwzględna ścieżka hosta (mount path-parity) |

## Odrzucane klucze (błędy)

Nie używaj: `projects_dir`, `default_project`, `default_workspace`, projektowe `alias` / `mount` / `role` / `windows`, workspace'owe `root` / `meta_path` / `mount_mode`, per-workspace `tmux`.

## Pochodne (nieustawiane przez użytkownika)

- Root workspace'a: `/home/developer/workspaces/<name>`
- Meta hosta: `.orcan/workspaces/<name>/`
- Nazwa sesji tmux = `name` workspace'a
- Primary workspace = pierwszy włączony wpis

## Narzędzia

| Polecenie | Rola |
| --- | --- |
| `make config-wizard` | Edytor interaktywny |
| `make config-scaffold` | Dodawanie bez interakcji |
| `make config-show` | Lista workspace'ów |
| `scripts/repository/config_io.py` | Load/dump/discover |

Przewodnik użytkownika: [Pierwsze kroki — Konfiguracja](../getting-started/configuration.md).

## Zobacz też

- [Przewodnik po konfiguracji](../getting-started/configuration.md)
- [Zmienne środowiskowe](environment.md)
- [Workspaces](../concepts/workspaces.md)
- [Referencja Makefile](makefile.md)
