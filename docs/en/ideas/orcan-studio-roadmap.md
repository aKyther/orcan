# Orcan Studio server and container roadmap

This is a maintainer handoff and product direction, not a list of available
features. It preserves decisions from the design session ending on 2026-10-08.
Read [Orcan Studio](orcan-studio.md) for the current implementation.

The follow-up decision is to develop named containers now, with shared sandbox
and cache. The implemented first management layer is **server/host → named
containers**: profiles connect to WSL2 or a VM, provisioning prepares CLI/image,
then creation chooses name, CPU, RAM, access and browser-terminal host port.
Servers report engine CPU/RAM capacity and project-filesystem free space.
Configuration, workspace metadata and launch state are instance-scoped;
worktrees are namespaced beneath the shared source catalog. Existing default
instances are not migrated. The Enclave term is retired from the current product
vocabulary; possible future grouping has no committed category name.
Real Windows/WSL/SSH and concurrent-container operation still need field testing.

## Product direction

Orcan helps people build the context that agents need. Running agents and
wrapping tmux are useful, but they are not the main product value.

Studio should make context selection, composition, inspection, and changes
simple and visual. A user should see which projects are available, which
workspace uses them, and what a proposed change will do. The terminal cockpit
stays available for daily work with an agent; Studio does not replace it.

Later, a group could coordinate several Orcan containers on one machine. A 2D graph,
inspired by the clarity of n8n, could describe work passing between their agent
roles. This is a future direction, not permission to build a general automation
engine now. First complete and test the single-container foundation.

## Terms and boundaries

| Term | Meaning |
| --- | --- |
| Credential | Immutable SSH user plus password or key identity; secrets stay in the system vault. |
| Profile | A connection to a local machine, WSL2 distribution, or SSH host. It must work without Orcan installed. |
| Server / host | Local machine, WSL2 distribution or remote VM reached by a profile; owns installed CLI, Docker images and shared data. |
| Named instance | One Orcan container on a host, with its own Compose project, configuration, launch state and workspaces. |
| Container | Execution and access boundary; later a named role such as developer or tester. |
| Sandbox / project root | A host-side catalog of source projects and folders, mounted into the container. Not necessarily inside Orcan's config directory. |
| Workspace | A named working context, with project bindings and a corresponding tmux session. |
| Binding | One project's attachment to a workspace, as a worktree or mount-as-is, with its own local alias. |

Do not permanently encode profile and container as the same identity in new storage.
Keep host identity separate from container identity. Named containers now isolate
paths, lifecycle and ownership; grouping and task orchestration remain future work.

## Current baseline: implemented, not yet fully field-tested

The transfer baseline before this roadmap is `138ce161` on `main`.

- Rust + Tauri desktop app, TypeScript + Vite UI, Windows/macOS/Linux packaging.
- Local, WSL2, and SSH profiles; separate immutable credentials with explicit
  users; SSH identity approval inside Studio.
- Online CLI installation and offline CLI kits. The offline kit excludes
  user configuration, sandbox/workspace data, and credentials.
- Separate image and CLI transfers between supported profiles. For an offline
  server, use WSL image export, SSH transfer, and remote `docker load`, not build.
  The online `install.sh` still needs GitHub; sending that script alone is not
  an offline installation.
- Transfer phases, bytes, speed, estimated upload time, and cross-view status.
  Image checks compare runtime configuration, ordered layers, and platform;
  engine-specific IDs alone are not a portable equality check.
- Interrupted uploads offer Resume and Discard. SHA-256 checks the partial and
  full payload. Resume requires the same Studio session; source export cannot
  resume. Remote idle partials older than 24 hours are cleaned on a later
  receiver operation, not by a continuous timer.
- Orcan supplies its paths, context, capabilities, and declared controls through
  `orcan studio probe --json`. Studio should not guess host/container config paths.
- Context map, project/workspace bindings, worktree management, parent updates,
  plans/drafts, settings inspection, and single-container creation exist.
  Inspect their behavior before adding another implementation.

Tests passed at the transfer baseline: 412 host tests, 19 native app tests,
3 UI behavior tests, UI build, formatting, and docs checks. This is not proof of
a real Windows → WSL → SSH end-to-end run; that still needs field verification.

The single-container foundation is being extended alongside this roadmap.
Check the current commit and tests before treating a planned block as complete.

## Single-container foundation: implementation and verification

The four blocks below now have an initial implementation: guided readiness
and provisioning return, guarded creation, compact runtime cards, real
existing-container lifecycle, and entry into context management. They are
acceptance criteria for the next session, not a request to duplicate the work.
Field-test Windows → WSL → SSH, failure recovery, and the named creation UI.
Refine in verified blocks; no release, tag, or
version bump is requested.

### 1. Guided preparation and creation

Make New container available from Servers, even when the selected profile does
not yet have Orcan. A saved connection is not the same as a provisioned runtime.

Show separate facts: connection, CLI/Studio protocol, Docker access, required
image, existing configuration/container, and readiness to create. A failure
must explain which layer failed, not call a reachable host "unreachable"
because its CLI is missing.

Offer existing provisioning actions only for missing or outdated components.
Preselect the destination profile. Offer online CLI install explicitly, or an
offline source profile and CLI kit. Offer image transfer separately. Never
silently fetch/build on a network-restricted destination or install Docker
without approval. WSL may use Docker Desktop integration or its own daemon.

After provisioning, recheck and return to creation. Review paths reported by
Orcan, Git/SSH access, Docker socket access, ttyd and optional user/password.
Keep defaults local-only and least-privilege. Then show a real plan, confirm,
create configuration, sync, start, and verify the actual result.

Acceptance:

- A profile without Orcan can enter preparation instead of disappearing.
- Existing configuration or an existing container blocks duplicate creation;
  check again on the backend immediately before apply.
- Selection or option changes invalidate the plan. Late async responses do not
  authorize a different profile. Background polling does not erase a ready plan.
- Errors preserve recovery actions; progress does not block navigation.
- Success opens the verified container and offers context management.

### 2. Compact container control panel

Show container state/name, required image, Orcan version, last successful check,
project/worktree/workspace roots, CPU/RAM, agent tools, and access exposure.
Use Orcan-reported values; unknown and stale are valid states, not defaults.

Keep the main view compact: summary, actions, paths, and optional details.
Put configuration behind the container gear. Locked image/start-time settings
should remain visible with a short reason. Do not display environment secrets.

Acceptance: the user can see what exists, where it lives, what is exposed, and
what is actionable without scrolling through several forms. Failed refreshes
mark old data stale and must not leave destructive controls enabled.

### 3. Correct lifecycle and change impact

Provide Start / Stop / Restart for the selected container, with progress,
state-based guards, and fresh status afterward. Preserve access flags, mounts,
resource settings, and protected ttyd behavior. Stop/restart warns that active
agent sessions may end; it does not remove project data.

Existing containers now use Docker's actual start/stop/restart actions.
The core fallback `runtime_args(Start)` and `runtime_args(Restart)` still both
represent `orcan up --resume`, but Studio's native lifecycle layer selects that
fallback only for Start after a container was removed. Field-test both paths;
do not treat ordinary restart as recreation or configuration apply.

Classify changes as context reconciliation, container restart, container
recreation, or image replacement. Context changes under existing mounted roots
can often reconcile live; new Docker mounts and creation-time resources may
need recreation. Show Orcan's plan and impact, not a blanket "restart required".
Keep unsupported resource edits locked rather than inventing an edit endpoint.

Acceptance: controls affect only the intended runtime, replay/preserve its
settings, and never claim success until the resulting state is checked.

### 4. Context as the main working area

After connection/probe, offer projects, workspaces, and the existing relation
map. Do not expose write actions before Orcan declares capabilities and paths.
Keep the map central rather than adding another context inventory.

Preserve these design decisions:

- Workspace column and available-project/folder column, clear anchors/lines,
  active relations highlighted, compact cards, mount/worktree icons and tooltips.
- Projects directly under a root stay flat. Real child folders form natural
  groups. Optional filters help with dozens of projects; avoid deep wrappers.
- Drag/drop asks a compact question: mount-as-is or worktree, branch, and alias.
  Prefer choices from reported inventory over raw path textareas.
- One master repository can supply many worktrees; each can attach to several
  workspaces. A workspace can contain multiple branches of the same repository
  through unique aliases/mount paths. Preserve old single-binding behavior.
- Mount-as-is can appear in multiple workspaces, including non-Git folders;
  shared writable access must be explicit, not presented as isolated copies.
- Keep drafts per workspace when switching views; Apply confirms the plan and
  Discard drops edits without touching files. Do not silently apply on navigation.
- Detach removes a binding. Delete removes a specific managed worktree only
  after inspection/confirmation. Track detached worktrees for later cleanup.
- Update the source parent with a button and cleanliness/upstream checks.
  Do not automatically rebase worktrees. Existing branches are a choice with an
  explanation, not automatically an error. Non-Git folders have no Git actions.

Acceptance: adding, comparing, editing, detaching and cleaning contexts are
clickable and understandable; sources, worktrees, aliases and mount paths are
not confused, and no manual host/config path discovery is required.

## Later: isolate multiple containers before orchestrating them

Keep the first/default instance backward compatible. Add explicit runtime IDs
and names, rather than relying on the connection profile as the runtime ID.
Containers may use the same source catalog or separate roots such as a tester
catalog outside Orcan home. A role is a user-facing name, not a hardcoded type.

Each runtime must own its configuration, generated state, launch settings,
container name, port allocation, workspace metadata, and worktree ownership.
Workspace names may repeat in different runtimes, but host paths and lifecycle
commands must remain unambiguous. Reusing sources must not mean reusing writable
workspace/worktree directories by accident.

Plan host-side worktree registration and bindings explicitly: reference shared
worktrees rather than giving two runtimes independent deletion authority.
Prefer small versioned JSON contracts over a new database or distributed
coordination service. Do not introduce a ZooKeeper-like directory bureaucracy.

Agent login/config directories may be shared only as an explicit access policy.
Evaluate read/write requirements and concurrent token refresh per agent tool;
do not blindly share every home directory writable. Keep role instructions and
credentials separate. Orcan still does not choose or route AI models.

Gate: prove two isolated containers on one host, independent lifecycle, safe
shared source access, namespaced workspaces, and default-instance compatibility
before building a pipeline editor.

## Later: a 2D graph for agent work

Use two graph layers, not one ambiguous canvas:

```text
Context map:  source project → worktree/mount binding → workspace
Work flow:    developer task → artifact/revision → tester task → review
```

The context graph defines what is available to an agent. The work graph defines
what runs next and what is handed over. A line showing a shared project must
not also mean "execute this task".

Candidate nodes are container roles and explicit tasks using a selected
workspace. Candidate edges carry a Git revision, artifact, or structured result,
with declared inputs/outputs and clear status. Changes to a flow are drafts;
running it is a separate confirmed action. A small first flow could be a
developer producing a revision, then a tester consuming it read-only, followed
by human review. Do not hand off a concurrently edited directory implicitly.

Keep manual terminal entry into a container/workspace available. The graph
supports that work; it should not force everyone into automation. Later task
runs need IDs, logs, failures, retry/cancel rules, human approval, and explicit
permissions. Prefer a local, inspectable runner over adopting a large workflow
platform. Cross-host flows, arbitrary plugins, and automatic agent chains are
not part of the next session.

## Contract, safety and maintenance rules

- Orcan owns configuration and resolves instance paths. Studio consumes a
  versioned, capability-declared contract, with plan/apply and revisions. JSON
  is a transport/storage format, not permission to hunt for files on the host.
- SSH is the current transport. A persistent server/HTTP API is optional later,
  not required now. Profile readiness stays independent of Orcan availability.
- Host canonical paths matter for Docker bind mounts; navigation symlinks are
  not substitutes. Context mounted under shared roots should remain live where
  possible, without unnecessary restarts.
- Never auto-approve changed SSH keys, disable identity checks, log passwords,
  expose a Docker socket by default, or write host SSH mounts to fix caching.
- Docker access is not full hostile-code isolation; filesystem, mounts and
  network policy determine what each agent can reach.
- Updates/installers must preserve configuration, sandbox sources, workspaces,
  credentials, and profile data. Do not transfer a user's Orcan home as a kit.
- Keep Rust + Tauri and existing adapters. No stack rewrite, speculative service
  layer, generic plugin engine, or unrelated cleanup.

## Small code map for the next agent

- `studio/app/src/main.ts`: current creator, server/container list, profile checks,
  lifecycle controls, context UI and demo adapter. Avoid more monolithic growth.
- `studio/app/src/types.ts`, `probe.ts`: report types/normalization, including
  Docker image/name facts and Orcan-provided creation defaults.
- `studio/app/src-tauri/src/main.rs`: native commands, profile/vault integration,
  probe, `enclave_action`, and `runtime_action`.
- `studio/app/src-tauri/src/provisioning.rs`, `transfer_receiver.py`,
  `transfer_cache.rs`, `transfer_progress.rs`: existing offline transfer/recovery.
- `studio/crates/orcan-studio-core/src/lib.rs`: report model and argument helpers.
- `cli/commands/studio.sh`, `scripts/repository/studio-enclave.py`,
  `studio-probe.py`: Orcan-side contract, creation, reported capabilities/paths.
- `cli/orcan.sh`, `scripts/repository/studio-instances.py`: named instance
  scoping and host-side configured-instance discovery.
- `cli/commands/up.sh`, `down.sh`, `cli/lib/runtime.sh`: actual lifecycle behavior.
- `studio/app/tests/feedback.test.mjs`, `tests/host/test_studio_transfer_receiver.py`
  and existing Studio probe/enclave tests: extend, do not duplicate.

Start by verifying named-instance isolation, shared data and the four foundation blocks. Keep
this roadmap current as decisions change. Use the workspace session brief for
short live handoffs, not additional PLAN/TODO/SUMMARY files.
