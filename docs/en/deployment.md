# Deployment

How Orcan itself is installed and how the **versioned** docs site is published.

## Product runtime (your machine / VPS)

Orcan is **not** deployed as a pulled image from GHCR.

### Steps

1. Clone a release tag or `main`
2. Configure `orcan.config.json`
3. `make env`
4. `make build` (or `make build-claude`)
5. `make terminal` or `make terminal-docker`

```bash
git clone https://github.com/aKyther/orcan.git
cd orcan
git checkout v0.1.0
make setup PROJECT_DIR=/absolute/path/to/your/repo
make build
make terminal-docker
```

### Multi-host

On each host: same git tag + `make build`, **or** (optional) push a privately built image with `make publish` / `make pull`. CI does not publish images.

## Documentation site (versioned, mike)

Docs use [mike](https://github.com/jimporter/mike) + Material’s version selector, with English + Polish inside each version.

| Alias / version | Meaning | Typical URL |
| --- | --- | --- |
| `latest` | Last **release** (git tag) | https://akyther.github.io/orcan/latest/ |
| `0.1.0` | Snapshot for that SemVer | https://akyther.github.io/orcan/0.1.0/ |
| `dev` | Tip of `main` (unreleased) | https://akyther.github.io/orcan/dev/ |
| `/` | Redirects to default alias (`latest`) | https://akyther.github.io/orcan/ |

Polish pages live under the same version prefix, e.g. `/latest/pl/`, `/0.1.0/pl/`.

### What publishes what

| Git event | Docs action |
| --- | --- |
| Push tag `vX.Y.Z` | `mike deploy X.Y.Z` + alias `latest` + set-default (Release workflow) |
| Push to `main` | `mike deploy` alias `dev` (CI) |
| Pull request | Build/check only — **no** publish |

CI `docs-dev` and Release share concurrency group `docs-gh-pages` so they do not push the branch at the same time. `docs-mike.sh` also re-fetches `gh-pages` before each deploy and retries on push rejection.

### Local mike helpers

```bash
DOCS_MIKE_PUSH=0 make docs-mike-release   # VERSION → local gh-pages only
DOCS_MIKE_PUSH=0 make docs-mike-dev
./scripts/repository/docs-mike.sh list
```

Use `DOCS_MIKE_PUSH=1` (default in CI) to push `gh-pages`.

### Pages settings

GitHub → Settings → Pages → Deploy from branch → **`gh-pages`** / `(root)`.

Do **not** use orphan wipe deploys; mike keeps all versions on that branch.

### Version × language

Use the header **Version** and **Language** controls together. Nested pages keep relative language links; a small script (`mike-i18n.js`) fixes absolute homepage language links under `/latest/` and `/X.Y.Z/`.

If a page is missing in an older version, you may land on a 404 or that version’s home — there is no smart cross-version remap.

## TODO

- [ ] Official Helm / cloud marketplace packaging — not planned
- [ ] GHCR official images — out of scope (see architecture)

## See also

- [Quick start](getting-started/quickstart.md)
- [Release process](development/release.md)
- [Docker reference](reference/docker.md)
- [Releases on GitHub](https://github.com/aKyther/orcan/releases)
