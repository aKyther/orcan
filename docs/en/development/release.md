# Version tags and releases

A version tag identifies changes. A release declares that an existing version is ready.
Ordinary commits keep notes under `[Unreleased]`.

```bash
make tag PART=patch       # fixes; minor for features, major for breaking changes
make release TAG=v4.0.1  # explicit readiness declaration, after validation
```

`make tag` requires a clean tree and changelog content. It synchronizes package
versions, cuts a SemVer changelog section, commits, and pushes `vX.Y.Z` and the
branch. It does not publish a GitHub Release. Tags are immutable: fixes receive
new versions, never a moved or deleted tag.

`make release` requires the selected local and remote tag to identify the same
commit, with matching committed VERSION. It dispatches the release workflow with
the exact SHA. The workflow checks that snapshot, validates tests and docs,
rechecks the remote tag, and publishes versioned documentation and a GitHub
Release. Dispatch means publication is pending, not already complete. The host
requires an authenticated GitHub CLI for this operation.

No new CalVer or `checkpoint/` tags are created. Historical tags and changelog
sections remain intact. Upgrade selection continues to use ordinary SemVer tags;
a tag can be an upgrade target before a GitHub Release is declared.
