# Release process

## Daily work vs release (short)

| What you do | Docs / product |
| --- | --- |
| PR → merge to `main` | Docs alias **`dev`** updates. No new SemVer. No GitHub Release. |
| You decide to ship → `make release` | Tag `vX.Y.Z`, docs **`X.Y.Z`** + alias **`latest`**, GitHub Release |

`dev` = “what is on main now”.  
`latest` = “what we officially released”.

## Model

- SemVer in `VERSION`
- Git tag `vX.Y.Z`
- GitHub Release notes (CI)
- Versioned docs via **mike** (`latest` / SemVer / `dev`)
- **No** container image publish from CI
- Users: `git checkout vX.Y.Z && make build`

## Steps

1. Update `CHANGELOG.md` (move items from Unreleased into a new `## [X.Y.Z]` section; fix footer compare links).
2. Bump version (also syncs display strings in `mkdocs.yml`, README, Home EN/PL):

```bash
make bump-patch   # or bump-minor / bump-major
```

3. Commit:

```bash
git add VERSION CHANGELOG.md mkdocs.yml README.md docs/en/index.md docs/pl/index.md
git commit -m "release: vX.Y.Z"
```

4. Tag and push:

```bash
make release
```

CI (`.github/workflows/release.yml`) validates, deploys versioned docs with **mike** (`X.Y.Z` + alias `latest`), and creates the GitHub Release.

## Local tags after build

`make build` also tags `orcan:VERSION` locally. That is for your machine only.
