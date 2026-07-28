---
description: Dlaczego powstał Orcan — rozproszone repozytoria, utracony kontekst pracy i kiedy go nie używać.
---

# Dlaczego Orcan?

## Problem

Nie pracujesz w jednym repozytorium.

Pracujesz w wielu. Często pochodzą z różnych organizacji. Niektóre zależą od siebie. Niektóre wymagają konkretnej wersji wspólnej biblioteki. Każda maszyna zbiera inny mix narzędzi, loginów i skryptów „jak zaczynam dzień”.

Po kilku miesiącach trudna nie jest klonacja. Trudne jest **odtworzenie pełnego kontekstu pracy**: które checkouty należą do siebie, gdzie agenci powinni startować, co powinni ignorować i które ścieżki bezwzględne Docker-from-Docker nadal zrozumie.

Bez wspólnego opisu tego kontekstu każdy developer (i każdy agent) buduje go z pamięci.

## Dlaczego to boli

- Onboarding to zgadywanie, które pięć repo ma znaczenie dla „customer A”.
- Agenci indeksują złe drzewa albo pomijają wspólną bibliotekę obok aplikacji.
- Zagnieżdżony Docker psuje bindy, gdy ścieżka w kontenerze ≠ ścieżka na hoście.
- Toolchainy i loginy CLI rozsypują się po home hosta i jednorazowych kontenerach.

Same komendy tego nie naprawią. Potrzebujesz **nazwanego kontekstu**, który da się odtworzyć.

## Do czego służy Orcan

Orcan to **orkiestrator kontekstu pracy**.

Nie zastępuje Gita. Nie wybiera modeli AI. Opisuje **które projekty tworzą jeden workspace**, montuje je z **path parity**, seeduje mały **context pack** czytelny dla agentów i otwiera **terminal w przeglądarce** (tmux + zsh), w którym Cursor CLI (`agent`) i Claude Code (`claude`) działają w Dockerze.

Idea produktu jest prosta: **projekty są częściami; workspace jest kontekstem.**

## Życie bez Orcana

Trzymasz prywatną listę ścieżek. Otwierasz pięć terminali. Masz nadzieję, że `docker compose` w kontenerze nadal widzi `/home/you/...`. Wklejasz te same ignores do każdego checkoutu. Tłumaczysz układ każdemu nowemu agentowi od zera.

## Życie z Orcanem

Piszesz jedną konfigurację JSON: workspace'y i bezwzględne ścieżki projektów. `orcan sync` materializuje mounty i pliki runtime. Otwierasz jeden terminal w przeglądarce, wybierasz workspace — Ty i agenci dzielicie ten sam układ oraz te same instrukcje startowe.

## Kiedy używać

- Kilka powiązanych checkoutów (często multi-org) tworzy jedną codzienną pracę.
- Chcesz agentów kodujących w izolowanym Dockerze.
- Potrzebujesz Docker-from-Docker z poprawnymi ścieżkami bind (path parity).
- Chcesz powtarzalnej „sesji” per klient lub linia produktu.

## Kiedy nie używać

- Jedno małe repo i zwykłe IDE wystarczą.
- Nie chcesz Dockera na hoście.
- Potrzebujesz produktu, który **routuje lub przypina modele** — to zostaje przy każdym CLI.
- Chcesz hostowanego rejestru obrazów SaaS — Orcan to **clone + `orcan build`**.

## Stanowisko projektowe (non-goals)

Orcan celowo **nie**:

- wybiera ani abstrahuje modeli ponad `agent` / `claude`
- auto-routuje promptów między CLI
- przepisuje każdego zamontowanego checkoutu git przy każdym starcie

Te granice trzymają narzędzie małe: **orkiestruj kontekst, nie kognicję.**

## Dalej

1. [Idee podstawowe](ideas/core-ideas.md) — Project, Workspace, Context  
2. [Model mentalny](ideas/mental-model.md) — jak elementy się łączą  
3. [Szybki start](getting-started/quickstart.md) — gdy jesteś gotów uruchomić
