# Changelog

Product releases use SemVer in `cockpit/pyproject.toml` and git tags `vX.Y.Z`.
Tags identify changes; an explicit release declaration marks an existing tag and
its exact commit as ready. See [Release process](development/release.md).

The full Keep a Changelog file lives in the repository root:

**[CHANGELOG.md](https://github.com/aKyther/orcan/blob/main/CHANGELOG.md)**

## How to read versions

| Artefact | Meaning |
| --- | --- |
| Git tag `v0.1.0` | Immutable version of changes |
| Local image `orcan:0.1.0` | Built on your machine from that tag |
| GitHub Release | Notes + install reminder (`git checkout` + `orcan build`) |

CI does not publish container images.
