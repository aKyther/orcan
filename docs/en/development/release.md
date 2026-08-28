# Release process

## Three tiers (short)

| What you do | Docs / product |
| --- | --- |
| PR → merge to `main` | Docs alias **`latest`** updates (rolling tip of main). No new tag. No GitHub Release. |
| `make tag` — your own checkpoint | Bumps SemVer, moves `CHANGELOG.md` `[Unreleased]` into `[X.Y.Z]`, commits + tags, **fully pushed** — but the tag lives under `checkpoint/vX.Y.Z`, not bare `vX.Y.Z`, so it can't trigger a release or become an update target. |
| `make release` — the real, deliberate stop | Ensures a real, pushed bare `vX.Y.Z` tag exists, adds its own CalVer tag (`26.3`) at the same commit, a CHANGELOG divider above everything checkpointed since the last release, GitHub Release, docs snapshot `X.Y.Z` (+ alias `26.3`). |

`latest` = "what's on main right now" (rolling — replaces the old `dev` alias name).
Numbered docs snapshots (`X.Y.Z`, `26.3`) only exist from a real `make release`.

Regular dev commits — including ones pushed out just to test something on
another machine — never touch version or tags. Only `make tag` / `make
release` do, and only when you decide to run them.

## Model

- SemVer in `cockpit/pyproject.toml` (`version = "X.Y.Z"`; root `VERSION` is a synced mirror). A bare `vX.Y.Z` git tag is what `orcan update`/`orcan downgrade`, CI, and GitHub Releases key off — only `make release` ever creates one.
- Checkpoint tags (`checkpoint/vX.Y.Z`, from `make tag`) are a separate namespace. `orcan update`/`downgrade` only match `^v[0-9]+\.[0-9]+\.[0-9]+$` and `release.yml` only triggers on `v*.*.*` — neither matches a `checkpoint/...` tag, so checkpoints are fully pushed and visible on GitHub without ever being release/update candidates.
- CalVer (`YY.Q`, e.g. `26.3`) gets its own bare tag at release time — "everything from here to here is release 26.3" — plus a `## YY.Q — DATE` divider in `CHANGELOG.md`, an extra `mike` docs alias, and the GitHub Release title. It's a second, human-named pointer at the same commit as the release's `vX.Y.Z` tag, not a replacement for it.
- Versioned docs via **mike**: `latest` (rolling), `X.Y.Z` (each release), `YY.Q` (alias to that same release).
- **No** container image publish from CI.
- Users: `git checkout vX.Y.Z && orcan build`.

## Checkpoint — `make tag`

Run this whenever you decide a batch of commits (could be 1, could be 50)
is done and you want a stable point to jump back to. Requires a clean
tree (commit your feature work first).

```bash
make tag                # bump patch (default)
make tag PART=minor     # or minor / major
```

This bumps `cockpit/pyproject.toml` + synced copies, moves whatever is
under `## [Unreleased]` in `CHANGELOG.md` into a new `## [X.Y.Z] - DATE`
section, commits (`chore: checkpoint vX.Y.Z`), tags it as
`checkpoint/vX.Y.Z`, and pushes both — commit and tag, nothing stays
local. It's still invisible to `orcan update`/`downgrade` and
`release.yml` (see Model above), so pushing it can't trigger a release
or docs publish; CI's `checks` job does still test the commit (it
triggers on every push to `main` regardless of tags).

## Release — `make release`

The rare, deliberate public stop (aim for roughly quarterly, but it's a
judgment call, not a cron job).

```bash
make release             # CalVer label = current quarter (YY.Q)
make release Q=26.3      # explicit label
```

Steps this runs:

1. If `[Unreleased]` still has content, auto-checkpoints it first (so
   nothing is lost).
2. Drops a `## YY.Q — DATE` divider in `CHANGELOG.md`, directly above
   every `[X.Y.Z]` section accumulated since the previous divider.
3. Commits (`release: YY.Q (vX.Y.Z)`).
4. Ensures a real `vX.Y.Z` tag exists (creating one if `make tag` hasn't
   already) — pushing it is what triggers `.github/workflows/release.yml`.
5. Tags the same commit `26.3` (bare CalVer, refused if that label was
   already used) and pushes it too.

CI then validates, deploys docs `X.Y.Z` (+ alias `YY.Q`, read back from
the `CHANGELOG.md` divider — never touches `latest`), and creates the
GitHub Release, titled `Orcan YY.Q (vX.Y.Z)`.

## Local tags after build

`orcan build` also tags `orcan:VERSION` locally. That is for your machine only.
