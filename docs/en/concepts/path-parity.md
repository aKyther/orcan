---
description: Path parity — same absolute paths on host and in the Orcan container, and why nested Docker needs it.
---

# Path parity

## Problem

You run Docker **inside** the Orcan container (`orcan up`). The daemon that creates nested containers is still the **host** daemon. Bind mounts are resolved on the host.

If the path inside Orcan were `/workspace/app` while the host checkout lived at `/home/you/code/app`, nested Compose would mount the wrong directory — or nothing.

## Why it hurts

Broken nested builds, empty volumes, and “it works on my laptop path but not in the agent container” bugs that are expensive to debug.

## How Orcan addresses it

**Path parity** means the same absolute path on the host and inside the Orcan container.

Example: host `/home/you/code/app` is mounted at `/home/you/code/app` in the container (not rewritten to `/workspace/app`).

Workspace UX still uses short symlinks under `/home/developer/workspaces/<name>/` for navigation. Parity mounts are for correctness with Docker-from-Docker. See [Mental Model](../ideas/mental-model.md).

## How it works

`orcan sync` writes mounts into `mounts/compose-projects.generated.yml`:

```yaml
# conceptual
volumes:
  - /absolute/path/to/app:/absolute/path/to/app
```

If a project path is itself a git worktree, `orcan sync` also mounts its main repo's **`.git` directory** at parity — a worktree's own `.git` is just a pointer into that shared git dir, and without it visible too, every git command inside the worktree fails with `fatal: not a git repository`. This is resolved by reading the worktree's `.git` pointer directly, so it works for any worktree (`orcan context worktree create` or a bare `git worktree add`), not only ones Orcan tracked itself. Only `.git` is mounted — never the main checkout's working-tree files — so a feature-branch worktree still can't see or edit the main branch's actual files; that boundary is the whole point of `orcan context worktree create` in the first place.

## Check (commands last)

```bash
orcan context show
```

Integration test (needs Docker socket):

```bash
make test-path-parity
```

## Common mistakes

| Mistake | Result |
| --- | --- |
| Relative `projects[].path` | Rejected or broken mounts |
| Assuming `/workspace` | Old pattern — not used |
| Editing generated Compose by hand | Overwritten by `orcan sync` |
