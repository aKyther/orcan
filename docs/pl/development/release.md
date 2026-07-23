# Proces wydania

## Codzienna praca vs release (krótko)

| Co robisz | Docs / produkt |
| --- | --- |
| PR → merge do `main` | Aktualizuje się alias docs **`dev`**. Bez nowego SemVer. Bez GitHub Release. |
| Decydujesz wydać → `make release` | Tag `vX.Y.Z`, docs **`X.Y.Z`** + alias **`latest`**, GitHub Release |

`dev` = „co jest teraz na main”.  
`latest` = „co oficjalnie wydaliśmy”.

## Model

- SemVer w `VERSION`
- Tag git `vX.Y.Z`
- Notatki GitHub Release (CI)
- Wersjonowane docs przez **mike** (`latest` / SemVer / `dev`)
- **Brak** publikacji obrazu kontenera z CI
- Użytkownicy: `git checkout vX.Y.Z && make build`

## Kroki

1. Zaktualizuj `CHANGELOG.md` (przenieś pozycje z Unreleased).
2. Podbij wersję:

```bash
make bump-patch   # or bump-minor / bump-major
```

3. Commit:

```bash
git add VERSION CHANGELOG.md
git commit -m "release: vX.Y.Z"
```

4. Tag i push:

```bash
make release
```

CI (`.github/workflows/release.yml`) waliduje, publikuje wersjonowane docs przez **mike** (`X.Y.Z` + alias `latest`) i tworzy GitHub Release.

## Lokalne tagi po buildzie

`make build` taguje też lokalnie `orcan:VERSION`. To tylko na Twojej maszynie.

## Zobacz też

- [Changelog](../changelog.md)
- [Wdrożenie](../deployment.md)
- [Przegląd rozwoju](overview.md)
- [Wydania na GitHubie](https://github.com/aKyther/orcan/releases)
