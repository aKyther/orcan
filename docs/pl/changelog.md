# Changelog

Wydania produktu używają SemVer w `cockpit/pyproject.toml` oraz tagów git `vX.Y.Z`.
Każdy właściwy release (`make release`) dostaje też etykietę CalVer
(`YY.Q`, np. `26.3`) — separator `## YY.Q — DATA` w pliku poniżej,
grupujący sekcje `[X.Y.Z]` wydane od poprzedniego. Pełny model: [Proces
wydania](development/release.md).

Pełny plik Keep a Changelog leży w katalogu głównym repozytorium:

**[CHANGELOG.md](https://github.com/aKyther/orcan/blob/main/CHANGELOG.md)**

## Jak czytać wersje

| Artefakt | Znaczenie |
| --- | --- |
| Tag git `v0.1.0` | Wydanie źródeł |
| Separator `## 26.3` w CHANGELOG.md | Etykieta CalVer dla tego release'u (kosmetyczna — źródłem prawdy jest tag) |
| Lokalny obraz `orcan:0.1.0` | Zbudowany na Twojej maszynie z tego tagu |
| GitHub Release | Notatki + przypomnienie instalacji (`git checkout` + `orcan build`) |

CI nie publikuje obrazów kontenerów.

## Zobacz też

- [Proces wydania](development/release.md)
- [Wdrożenie](deployment.md)
- [Wydania na GitHubie](https://github.com/aKyther/orcan/releases)
