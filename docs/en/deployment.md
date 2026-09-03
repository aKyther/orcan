# Deployment

How Orcan itself is installed and how the **versioned** docs site is published.

## Product runtime (your machine / VPS)

Orcan is **not** deployed as a pulled image from GHCR.

### Steps

1. Clone a release tag or `main`
2. Configure `orcan.config.json`
3. `orcan sync`
4. `orcan build --agent codex` (or choose another explicit client set)
5. `orcan up` (local — `orcan enter`) or `orcan up --with-ttyd` (browser) or `orcan up --with-docker | --with-network NAME` (pick one)

```bash
git clone https://github.com/aKyther/orcan.git
cd orcan
git checkout v0.1.0
orcan init /absolute/path/to/your/repo
orcan sync
orcan build --agent codex
orcan up
# remote browser: orcan up --with-ttyd && orcan url
```

### Multi-host

On each host: `orcan build --agent codex` (or `--all-agents`; build is local and never publishes). CI does not publish images.

## Documentation site (versioned, mike)

Docs use [mike](https://github.com/jimporter/mike) + Material’s version selector, with English + Polish inside each version.

| Alias / version | Meaning | Typical URL |
| --- | --- | --- |
| `latest` | Rolling tip of `main` — default landing page | https://akyther.github.io/orcan/latest/ |
| `0.1.0` | Pinned snapshot for that SemVer, from a `make release` | https://akyther.github.io/orcan/0.1.0/ |
| `26.3` | Alias to that same release's snapshot (its CalVer label) | https://akyther.github.io/orcan/26.3/ |
| `/` | Redirects to default alias (`latest`) | https://akyther.github.io/orcan/ |

`latest` here means "what's on `main` right now", not "last release" —
see [Release process](development/release.md) for the full `make tag` /
`make release` split. Polish pages live under the same version prefix,
e.g. `/latest/pl/`, `/0.1.0/pl/`.

### What publishes what

| Git event | Docs action |
| --- | --- |
| Push tag `vX.Y.Z` (from `make release`) | `mike deploy X.Y.Z` + alias `YY.Q` (Release workflow) — `latest` untouched |
| Push to `main` | `mike deploy` alias `latest` + set-default (CI) |
| Pull request | Build/check only — **no** publish |

CI `docs-dev` and Release share concurrency group `docs-gh-pages` so they do not push the branch at the same time. `docs-mike.sh` also re-fetches `gh-pages` before each deploy and retries on push rejection.

### Local mike helpers

```bash
DOCS_MIKE_PUSH=0 make docs-mike-release   # VERSION → local gh-pages only
DOCS_MIKE_PUSH=0 make docs-mike-latest
./scripts/repository/docs-mike.sh list
```

Use `DOCS_MIKE_PUSH=1` (default in CI) to push `gh-pages`.

### Pages settings

GitHub → Settings → Pages → Deploy from branch → **`gh-pages`** / `(root)`.

Do **not** use orphan wipe deploys; mike keeps all versions on that branch.

### Version × language

Use the header **version dropdown** together with **Language**:

- **Docs version dropdown** — lists `latest`, SemVer folders, and their `YY.Q` aliases from
  [versions.json](https://akyther.github.io/orcan/versions.json). Works on
  GitHub Pages **and** on local `mkdocs serve` (fetches the published JSON).
  Keeps the current page path when switching (e.g. Installation → same page on `2.0.0`).
- **`vX.Y.Z` chip** — product SemVer from `extra.orcan_version`; links to Changelog.

Nested pages keep relative language links; `mike-i18n.js` fixes absolute homepage language links under `/latest/` and `/X.Y.Z/`.

If a page is missing in an older version, you may land on a 404 or that version’s home — there is no smart cross-version remap.

## TODO

- [ ] Official Helm / cloud marketplace packaging — not planned
- [ ] GHCR official images — out of scope (see architecture)

## See also

- [Quick start](getting-started/quickstart.md)
- [Release process](development/release.md)
- [Docker reference](reference/docker.md)
- [Releases on GitHub](https://github.com/aKyther/orcan/releases)
