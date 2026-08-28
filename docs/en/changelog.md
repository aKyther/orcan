# Changelog

Product releases use SemVer in `cockpit/pyproject.toml` and git tags `vX.Y.Z`.
Each real release (`make release`) also gets a CalVer label (`YY.Q`, e.g.
`26.3`) — a `## YY.Q — DATE` divider in the file below, grouping the
`[X.Y.Z]` sections shipped since the previous one. See
[Release process](development/release.md) for the full model.

The full Keep a Changelog file lives in the repository root:

**[CHANGELOG.md](https://github.com/aKyther/orcan/blob/main/CHANGELOG.md)**

## How to read versions

| Artefact | Meaning |
| --- | --- |
| Git tag `v0.1.0` | Source release |
| `## 26.3` divider in CHANGELOG.md | CalVer label for that release (cosmetic — the tag is the source of truth) |
| Local image `orcan:0.1.0` | Built on your machine from that tag |
| GitHub Release | Notes + install reminder (`git checkout` + `orcan build`) |

CI does not publish container images.
