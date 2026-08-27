---
description: Orkiestrator kontekstu pracy dla agentów kodujących — wiele repozytoriów, jeden kontekst.
tags:
  - concept
---

# Orcan

<div class="orcan-hero" markdown>

Orcan orkiestruje **kontekst pracy** dla agentów kodujących: które repozytoria należą do siebie, jak są montowane i jak wchodzisz do tego środowiska w Dockerze.

**Nie** wybiera modeli — Cursor CLI (`agent`) i Claude Code (`claude`) zachowują własne konta.

<span class="orcan-version">Wersja **3.0.1**</span>

</div>

## Zacznij tutaj

<div class="grid cards" markdown>

-   :material-download-outline: __Instalacja__

    ---

    Dodaj `orcan` do PATH, potem sync i build.

    [:octicons-arrow-right-24: Instalacja](getting-started/installation.md)

    [:octicons-arrow-right-24: Szybki start](getting-started/quickstart.md)

-   :material-lightbulb-outline: __Zrozum__

    ---

    Po co jest Orcan, Project / Workspace / Context i model mentalny.

    [:octicons-arrow-right-24: Dlaczego Orcan?](why-orcan.md)

    [:octicons-arrow-right-24: Idee podstawowe](ideas/core-ideas.md)

-   :material-map-search-outline: __Znajdź zmianę__

    ---

    Macierz *co chcesz zmienić* → *gdzie w repo* → *który doc*.

    [:octicons-arrow-right-24: Mapa zmian](change-map.md)

-   :material-book-search-outline: __Szukaj w referencji__

    ---

    Flagi CLI, zmienne env, Compose, bezpieczeństwo — po opowieści.

    [:octicons-arrow-right-24: Referencja CLI](reference/cli.md)

    [:octicons-arrow-right-24: FAQ](faq.md)

</div>

## Trzy słowa

| Termin | Znaczenie |
| --- | --- |
| **Project** | Jeden checkout — ścieżka bezwzględna na dysku |
| **Workspace** | Nazwany zbiór projektów + jedna sesja tmux |
| **Context** | Odtwarzalne środowisko: mounty, instrukcje, ignores, wejście |

Konfiguracja opisuje te relacje. `orcan sync` i Docker je stosują. Agenci i ludzie dzielą ten sam układ.

## Spróbuj

```bash
curl -fsSL https://raw.githubusercontent.com/aKyther/orcan/main/install.sh | bash
orcan doctor
orcan init /absolute/path/to/your-repo
orcan sync && orcan build && orcan up
# lokalnie: orcan enter
```

Pełne kroki: [Instalacja](getting-started/installation.md) · [Szybki start](getting-started/quickstart.md).

!!! note
    Po zmianach konfiguracji zawsze `orcan sync` przed odtworzeniem (`orcan down && orcan up`). Obraz przebudowuj tylko gdy zmienia się Dockerfile lub zestaw instalacji agentów.

## Zobacz też

- [Model mentalny](ideas/mental-model.md) — jak elementy się łączą  
- [Architektura](architecture.md)  
- [Changelog](changelog.md) · [GitHub](https://github.com/aKyther/orcan)
