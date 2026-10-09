# Orcan Studio server and container roadmap

This is a maintainer handoff and product direction, not a list of available
features. It preserves decisions from the design sessions of 2026-10-08 and
2026-10-09. The maintainer has authorized implementation of the manual milestone;
automation remains future planning.
Read [Orcan Studio](orcan-studio.md) for the current implementation.

The follow-up decision is to develop named containers now, with shared sandbox
and cache. The implemented first management layer is **server/host → named
containers**: profiles connect to WSL2 or a VM, provisioning prepares CLI/image,
then creation chooses name, CPU, RAM, access and browser-terminal host port.
Servers report engine CPU/RAM capacity and project-filesystem free space.
Configuration, workspace metadata and launch state are instance-scoped;
the probe reports worktrees namespaced beneath the shared source catalog.
The first isolation block now aligns the host Git helper and probe registry
with those paths; Compose passes the namespace to newly created containers. Existing default instances are not migrated. Enclave is reserved for
the planned group of containers across one or more servers; it is not a current
container category. Identity templates and enclaves are planning work only.
Real Windows/WSL/SSH and concurrent-container operation still need field testing.

The creator now lists installed images labelled Orcan and project roots reported
by configured instances on the host. It records choices in the new configuration
and rechecks them before plan/apply. Cache paths are explicitly reported; the
last selected container is a device preference per profile, never authorization
to edit without a fresh check. No extra container or workflow grouping is added.

## Agreed first milestone

Build a manually usable enclave, using the existing server/container foundation.
The intended user journey is:

```text
Create identity in Studio (optional)
  → connect to server and provision CLI/image
  → create/start container with identity or Default
  → create enclave from existing containers on one or more VMs
  → arrange/save the 2D canvas
  → Attach to a container/workspace
  → manually sign into and use an agent
```

The first milestone includes the identity library, creation-time adaptation,
workspace instruction propagation, stable target identification, accessible
local storage, saved enclave membership/layout and manual terminal access.
A container can belong to several enclaves. Identity is immutable for its life;
Default adds no role template to the normal Orcan base rules.

Canvas lines and saved layouts are inert. Opening a group does not provision,
create or start its containers. Start and Attach are explicit actions on the
selected target. Closing a terminal does not delete its container or end its
persistent tmux session implicitly. Agent sign-in is manual.

Optional later work includes PR/MR integration, task dispatch, execution edges,
results, retention and retries. These designs are preserved below for continuity,
but they are not acceptance requirements for the manual milestone. No background
scheduler, mandatory MCP, automatic login or pipeline engine is needed now.

### Remaining decisions for the first milestone

- Define the exact instruction composition and verify actual agent loading.
- Choose supported Attach mechanisms on Windows, WSL, SSH and local hosts,
  including target labels and reconnect to existing sessions.
- Define UUID initialization/clone detection and replacement-container config,
  preserving projects while clearing the old immutable identity assignment.
- Define writable installation-adjacent studio-data roots on each platform and
  preservation on updates; keep current profiles/vault outside this change.
- Define the minimal canvas layout/cards and behavior for stale, missing or
  offline members. Avoid adding task controls in the initial view.

Resolve these implementation design questions within the authorized manual
milestone. The six checks before automation remain in their separate
section. Detailed contracts should follow the smallest verified manual workflow.

## Product direction

Orcan helps people build the context that agents need. Running agents and
wrapping tmux are useful, but they are not the main product value.

Studio should make context selection, composition, inspection, and changes
simple and visual. A user should see which projects are available, which
workspace uses them, and what a proposed change will do. The terminal cockpit
stays available for daily work with an agent; Studio does not replace it.

Later, an enclave could coordinate selected Orcan containers across several VMs.
Each container has an identity inherited by all its workspaces. A 2D graph,
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
| Identity | A named, versioned template of working instructions, procedures and tool requirements, selected for a whole container. Separate from credentials and connection profiles. |
| Server default identity | The identity proposed for new containers on that server or VM; falls back to Default. |
| Enclave | A logical group of selected containers from one or more servers or VMs. Its member unit is a container, not a VM or workspace. |
| Sandbox / project root | A host-side catalog of source projects and folders, mounted into the container. Not necessarily inside Orcan's config directory. |
| Workspace | A named working context, with project bindings and a corresponding tmux session. |
| Binding | One project's attachment to a workspace, as a worktree or mount-as-is, with its own local alias. |

Do not permanently encode profile and container as the same identity in new storage.
Keep host identity separate from container identity. Named containers now isolate
configuration and lifecycle; worktree ownership still needs verification.
Identity templates, grouping and task orchestration remain future work.

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

## Planned identities and enclaves

Implementation has started with the isolation foundation. Identities and the
manual enclave remain the next planned blocks.
The agreed model is: a VM proposes a default identity, a container owns its
selected identity, and all workspaces in that container inherit it. An enclave
groups containers, including containers selected from different VMs.

### Identity creation in Studio and adaptation to a container

Studio is where users create, edit and version identities in a template
library. A user can start from Default or an existing identity and define its
name, purpose, working instructions, procedures, output formats and tool
requirements. Saving an identity in Studio does not change any container.

The identity library is a first-class Studio section alongside Profiles and
Credentials, with saved template cards and a small create/edit form. Initial
fields are name, short description and a Markdown textarea for identity
instructions: what the container's agents are, how they work and how they report.
Concrete PR/MR tasks remain separate from this persistent role description.
Identity can describe an effective developer, goal-oriented working habits or
a specialist review perspective; it is not limited to job titles. Keep the
existing general Orcan AGENTS.md/CLAUDE.md rules as the base and add identity
instructions without replacing them. Use Markdown for the instruction body and
JSON only for UUID/name/description/version metadata; no numeric priority engine
in the first version. Describe working priorities in plain instruction text.
Proposed storage is `identities/<identity_id>/identity.json` for metadata/version
and `instructions.md` for the readable text. Editing produces a version for
future containers and never changes an already assigned container.

Adaptation happens only during container creation. Choose a server, installed
image and identity version; inspect the plan, then create the container.
Provisioning of CLI/image remains separate. A server such as "Testers" proposes
Tester for new containers; without a server default, use Default. Creation can
select a different identity.

Studio transfers the selected template through the existing local, WSL or SSH
adapter to Orcan-owned instance configuration on the destination host. Orcan
adapts it to reported paths, supported agent instruction mechanisms and available
tools before startup. Keep the reusable template separate from generated
instructions. Report missing tools before creation; do not silently install them
or grant permissions. An identity does not require its own Docker image unless
its tool requirements require different image contents.

The container's identity and template version are immutable. Every existing and
new workspace inherits that identity; there are no per-workspace overrides.
Editing a Studio template or changing the VM default affects future containers
only. Existing containers without an explicit identity remain Default. A different
identity requires a new container; context transfer is a separate explicit action.
There is no identity update, switch or rollback action on an existing container.
To replace a container's identity, explicitly remove that container and create
a replacement with the new choice; this is a separate lifecycle action, not an
in-place identity edit. Show the identity read-only in existing-container settings.
Removal must preserve project data and must not silently carry the old immutable
assignment into the replacement; define replacement-config handling in its plan.

The host copy lets the container retain its identity when Studio is closed.
Creation verifies the recorded identity and the instructions actually loaded by
the agent, rather than only generated files. Keep three visible layers: Orcan
base rules, container identity, and repository/workspace instructions. Do not
overwrite repository AGENTS.md or CLAUDE.md. Define composition order and supported
agent mechanisms before implementation. Templates contain working instructions,
procedures, output formats and tool requirements, not credentials or permissions.

Extend Orcan's existing workspace context-pack propagation rather than creating
a second instruction-distribution layer. Include the container's frozen identity
in the Orcan-managed workspace instruction files (such as AGENTS.md/CLAUDE.md),
for every existing and newly created workspace through reconciliation. Keep the
frozen instance copy as the source; Studio need not be connected when a workspace
is added. Preserve custom rules and repository-owned instructions, and verify
that the supported agents load the generated context. Reconciliation propagates
the same identity; it cannot change the identity selected at container creation.

### Enclave membership across VMs

For example, Project Alpha can contain VM 1's container 1 as Engineer and VM 2's
container 3 as Tester. Studio selects the server first, then one of its reported
containers. Each member keeps its identity, workspaces, paths and lifecycle;
joining an enclave does not create a shared filesystem across VMs.

Use stable server and container references, independent of the connection
profile used to reach them. Multiple profiles can reach the same server.
Deleting an enclave keeps its member containers and their data. Group operations
show their exact targets and per-container outcomes, including offline members
and partial failures. Existing containers can remain outside any enclave.

A container can belong to several enclaves. Enclave membership does not reserve
its workspaces; all enclaves share the same one-active-task-per-workspace guard.
Before implementation, settle how server identity is verified. Template and enclave records use the accessible
directory described below; multi-device editing is outside the initial scope.

### UUIDs and target identification

Use human-readable names for display and UUIDs for persistent references. Renaming
an object must not change its ID or retarget an enclave member or task.

| Object | Reference | Ownership |
| --- | --- | --- |
| Server / VM | server_id | Orcan-owned host record, reported over the authenticated connection. |
| Container | container_id | Orcan-owned instance record; a new runtime incarnation gets a new ID. |
| Identity | identity_id plus immutable version | Studio template library, copied with the selected version to the host. |
| Enclave | enclave_id | Studio group definition. |
| Workspace | workspace_id plus container_id | Orcan-owned context record. |
| Flow run | run_id | Studio snapshot of one requested execution. |
| Step | step_id within run_id | One step in that run snapshot. |
| Attempt | attempt_id | One dispatch/execution attempt for a step. |

Use a standard UUID generator; no custom identifier service. Retain server ID
across normal CLI updates and container ID across start/stop/restart. A removed
and recreated container receives a new container ID, even with the same name;
retain its configuration separately and require explicit rebinding of old
enclave references. A cloned VM must receive a new server ID. Specify clone
initialization and duplicate-ID detection before relying on these references;
a copied ID file alone cannot prove host identity.

A profile only provides transport and credentials. After authentication, compare
reported server/container IDs with the expected target before dispatch or edit.
Changing a profile must not silently rebind an enclave. UUIDs do not replace SSH
host-key verification or authorization. Existing installations need an explicit
initialization plan; a read-only probe must not create IDs as a side effect.

Task results carry run_id, step_id, attempt_id and target references, with the
exact input/output commit. Proposed output layout is
`runs/<run_id>/<step_id>/<attempt_id>/`. Validate UUIDs and ownership before using
them as paths. Re-delivering the same attempt_id returns that attempt's recorded
status and cannot start another execution; an explicit retry uses a new ID.
Keep deduplication records through the run's retry window even when bulky outputs
expire. Expired/unknown old attempts require reconciliation, not automatic replay.

Acceptance: renames preserve references; two profiles reaching one server do not
duplicate members; a same-name replacement is blocked until explicitly rebound;
clone duplicates are detected; results match their exact attempts; and duplicate
delivery after reconnect or cleanup cannot execute the same attempt twice.

### Graphical enclave creator

Preparation belongs to Servers, before enclave composition: provision the host
CLI/image, then explicitly create and start containers with a selected identity
or Default. Default means the existing Orcan base instructions without an added
role template, not absence of all instructions. The enclave selects these
already configured containers; creating or opening the group does not provision
hosts, create runtimes or start stopped members automatically.

The first milestone is a manually usable enclave, not automatic execution.
Create identities and containers explicitly, select members, then enter their
workspaces and sign into chosen agent tools manually. Studio helps reach the
right environment; it does not log in as the user, distribute login secrets or
start task chains. Identity selection does not select an AI model or provider.

Use a 2D canvas in Studio. A side panel groups reported containers by VM/server;
users drag existing containers onto the canvas, arrange cards, name the enclave
and save. Cards show container name, server, immutable identity, observed state
and available workspaces. Joining an enclave changes no container configuration
and requires no restart. Removing a card or deleting the enclave keeps runtime
data and containers intact.

Membership and layout are the first canvas scope. Later, an execution view adds
explicit handoff edges and workspace selection for each task step. Layout alone
never starts work. Keep this canvas separate from the existing context relation
map: a project binding is not an execution edge. Editing a saved graph does not
change an already running job, which records its own graph snapshot.

In the initial milestone, omit execution edges/triggers or display any retained
relationship lines as descriptive only. Connecting cards, saving layout, opening
an enclave or receiving a status update never starts an agent or a task.
Each card offers access to its reported workspaces and supported terminal/tmux
entry. Prefer existing access mechanisms; do not assume a browser terminal is
available or expose one automatically. Verify Windows/WSL/SSH entry separately.

Provide an explicit **Attach** action on each canvas card. It opens a terminal
attached to that exact container and optionally its selected workspace/tmux
session, for manual agent login, setup and normal work. Display the server,
container and workspace target in the terminal entry. Attach does not submit
tasks, choose an agent or perform sign-in automatically.

Check the actual runtime before attach. For a stopped container, show a separate
explicit Start action using existing lifecycle guards, verify running state,
then offer Attach. For missing or unreachable containers, show recovery/check
actions rather than opening a misleading session or recreating them silently.
An attached terminal's closure must not remove the container or implicitly end
a persistent tmux session. Select the supported terminal/browser/external entry
mechanism during UX design; no new terminal stack is assumed by this plan.

Acceptance: create an enclave with containers on two VMs, reopen its saved
layout, identify each immutable identity, enter each selected workspace and
manually authenticate/use an agent. The user should know which sessions are
open and where to return to them. Agent sign-in readiness is unknown unless
reliably reported; an opened terminal alone does not prove authenticated state.
Keep credentials in the agent's supported store, outside identity/enclave files.

Automatic task orchestration remains a future option, not a requirement for
shipping this manual milestone. Validate the manual workflow before deciding
whether and how to activate execution edges.

### Accessible Studio data directory

Store planned identity templates, enclave definitions and run records in a
plain `studio-data/` directory beside the installed application, resolved from
its installation location rather than the shell's working directory. The goal
is direct user access for inspection, copying, backup and manual cleanup.
Provide **Open data directory** in Studio. Use readable Markdown reports and
versioned JSON records, without a database for these records.

```text
Orcan Studio/
  application
  studio-data/
    identities/
    enclaves/
    runs/<run_id>/
      run.json
      steps/<step_id>/<attempt_id>/
        result.json
        report.md
        execution.log
```

Installation must check write access to this directory; report a protected
location instead of silently falling back to another data directory. Updates
must preserve studio-data. Define platform-specific installation roots before
implementation, including macOS where the adjacent directory must be outside
the signed application bundle. This placement applies to the new planning/run
data; it does not authorize moving existing profiles or credential-vault secrets.

One Studio installation owns a run in the first version; no multi-device
synchronization. Host-side configuration, tasks and results remain on their VMs;
Studio stores orchestration records and retrieved result copies, not whole
workspaces. Manual deletion of local records never deletes remote containers,
repositories or tasks and does not cancel an already accepted remote execution.

Handle manually removed completed outputs as **Result removed**, without
redispatch. Prefer closing Studio before manual cleanup, especially deletion of
the whole directory. Missing active-run records require an explicit recovery
path from host task IDs; never reconstruct and resubmit a run automatically.
Retain malformed files for inspection and show a recoverable error rather than
overwriting them. Include missing files and update preservation in acceptance.

### Decisions before later automation

Keep these six design checks for future automation, outside the manual milestone:

1. Instruction composition: define Orcan/identity/repository layering and show
   the effective agent instructions. This is required for the identity milestone.
2. Agent delivery: verify a chosen tool's fresh-task or managed-session interface,
   completion and cancellation; preserve manual sessions. Decide after manual use.
3. Busy context: enforce workspace ownership across enclaves and detect shared
   writable project paths, not just different workspace IDs.
4. PR/MR scenario: pin revisions, collect tests/review, require explicit external
   posting and mark changed heads outdated.
5. Recovery: specify Studio close, lost SSH, stopped containers, missing results
   and manually deleted local records; no duplicate redispatch. Manual session
   access/reconnect is part of the first milestone; task recovery comes later.
6. Canvas meaning: cards are containers, future task steps choose workspaces,
   and future edges declare result/condition. Initial lines are inert; first
   automation, if pursued, uses a sequence without loops or arbitrary scripts.

## Planned task handoff and execution

The following is a future design beyond the manually usable enclave milestone.
The choice to implement it remains open until that workflow has been evaluated.

Studio coordinates the graph; Orcan runs one assigned task in a selected
container/workspace; the agent returns a result. A container does not need the
whole enclave graph or direct contact with other agents. Enclave membership is
separate from immutable identity and can be included as task metadata.

### First useful flow: GitHub PR and GitLab MR collaboration

An enclave can provide independent perspectives on the same PR/MR revision:
correctness, security, architecture or product behavior. Manual Attach is the
initial way to request these assessments and compare them. A later automated
review preset can collect independent reports side by side; it need not force
a sequential handoff or synthesize one verdict. The sequential tests/review flow
below is another future preset, not the definition of an enclave or identity.

The first use case is coordinated work on an existing GitHub pull request or
GitLab merge request. Both providers belong in the plan, with a common small
review model and provider-specific adapters. Do not assume one repository per
container or sandbox: a workspace may bind several projects, while each review
run selects one repository and one PR/MR explicitly.

The user selects an enclave, provider/repository and PR/MR, assigns Tester and
Reviewer to available workspaces, previews the exact base/head revisions and
starts. Tester checks that snapshot; Reviewer consumes the same change and test
report; Studio collects results for human acceptance. Failed tests stop the flow.
A changed PR/MR head makes the previous result outdated; do not present it as
review of the latest revision or silently restart it.

```text
GitHub PR / GitLab MR → pinned base/head → Tester → Reviewer → human decision
Later: requested correction → Engineer → new PR/MR revision → new review run
```

First support reading PR/MR metadata, changes and status, plus local review
execution and result display. Posting comments/reviews or check results is a
separate explicit action with provider permissions and duplicate-post prevention.
Automatic merge, push, repair loops and arbitrary pipelines remain out of scope.
Define provider authentication storage, required access and fork-revision fetching
before implementation; instructions/identity templates never contain tokens.

Each edge declares input and completion conditions. It carries an immutable
commit, artifact or structured report, never an implicitly shared live directory.
An agent exiting successfully is not enough: validate the result and test/review
verdict before releasing the next step. Findings stop for a human decision.

### Workspace, tmux session and agent execution

A workspace is the project context; tmux provides a persistent interactive session;
an execution attempt is one tracked task. Preserve the existing manual tmux
workflow. A separate process per task is one possible adapter mode, not a settled
requirement, and a dedicated automation workspace is optional rather than mandatory.

Plan agent-specific adapters with reported capabilities: launch a fresh task,
resume a supported session, or use a managed persistent agent session when its
interface permits reliable submission and completion tracking. Verify the actual
installed tool's non-interactive/session interfaces; do not infer support from its
terminal appearance or assume all agents have the same CLI. Choose one verified
execution mode for the first end-to-end flow, while retaining the adapter boundary.

For an existing agent session, require explicit selection and managed ownership;
do not inject work into an arbitrary terminal where a human may be typing. Specify
how a task is accepted, what session context persists, how completion/results are
identified, and how cancellation affects only that task. A tmux pane's existence
or parsed screen output alone is not a reliable completion protocol. Tools without
a reliable automation interface remain available for manual work.

A container can join several enclaves. Enforce one active automated task per
workspace across all runs/enclaves on the host, not only in one Studio view. Human
work must not be silently interrupted or its checkout changed. Offer a separate
workspace/worktree when needed, or block until the chosen context is safe. Different
workspace paths can still share writable source mounts; check underlying project
paths before claiming isolation or allowing conflicting checkouts.

### Task envelope and result

Define small versioned JSON contracts, reusing the existing
[agent inbox](agent-inbox.md) where it fits. Proposed envelope fields are:

- Run ID, step ID, attempt ID and enclave reference.
- Stable server/container reference, workspace and expected identity version.
- Goal, constraints, acceptance criteria and chosen supported executor.
- Provider, repository identity, PR/MR reference, pinned base/head commits and
  declared artifacts/reports.
- Output destination and result schema, scoped to this run and workspace.

The result carries matching IDs, execution outcome, domain verdict, input/output
revisions, report/artifact references, exit code and log references. Credentials
and whole chat transcripts are excluded. Identity governs how to work; this
envelope states what to do. Validate paths and result references on the Orcan
side. Do not treat agent-provided text as commands or as authority to run new tasks.

Existing inbox/executor code provides local manifests, atomic claims and basic
completion/output capture. It does not establish Studio graph scheduling,
cross-VM delivery, cancellation, reconnect recovery or structured test/review
verdicts. Inspect and extend these mechanisms rather than adding another queue.
Audit worker exclusivity and crash recovery before relying on claim semantics.

Store a human-readable report.md and a machine-readable result.json with each
attempt, alongside its task manifest and execution log. The agent produces the
report and domain verdict; Orcan validates them and records trusted execution
status and IDs. Publish the final result atomically after execution ends.
File presence alone does not mean completion. Studio retrieves the validated
result and report through the existing adapter; a missing or invalid result
blocks handoff. An execution can succeed while tests or review report failure.

### Result retention

Default retention is seven days for completed-run reports, logs and artifacts,
and thirty days for compact history (IDs, status, revisions and timestamps).
Start these clocks when the whole run reaches a terminal state, not when an
individual step finishes. Queued/running runs, runs awaiting human review and
outputs still needed by downstream steps are protected. Connection loss alone
does not start a retention clock or make files eligible for cleanup.

Studio offers a simple retention setting and a **Keep result** action. A kept
result retains its history and referenced output files until explicitly released
or deleted. Confirm the retention pin on each host holding those files; if a
host is offline, show the request as pending rather than promising preservation.

Orcan cleans its managed task-output directories on the VM; Studio cleans its
local copies. Run cleanup at startup and periodically while each component is
active. An offline or stopped host cleans eligible files when Orcan next runs;
TTL is an eligibility rule, not a guarantee of deletion at an exact time.

Cleanup is limited to recorded, owned task files and must not follow symlinks
or remove unknown files, live tasks, pinned results or dependent outputs. It
does not delete repositories, commits, workspaces or worktrees. Report expired
outputs explicitly; do not redispatch an old task merely because its report
was cleaned. A deliberately requested retry creates a new attempt.

Retention acceptance: expire eligible outputs and history at their respective
ages; preserve active, review-pending, pinned and downstream-required data;
recover after offline operation; and leave project data and unknown files intact.

### Delivery between VMs

Use existing authenticated Studio adapters for task submission and status/result
retrieval. Plan a narrow, capability-declared Orcan contract for submit, status,
logs, result and cancel; endpoint names are not public CLI commitments yet.
No MCP server or persistent HTTP service is required for the first version.
MCP can later expose the same contract if agents need interactive task tools.

For the first cross-VM flow, require every participating workspace to access the
same configured Git remote and fetch the exact published commit. Block startup
when a required revision is unavailable. Distinct workspace names and paths are
valid; resolve them through each destination's report. Git/SSH authentication
stays on that host. Do not reset dirty workspaces or rewrite an active session's
checkout; use a dedicated execution workspace or block with a recovery action.

For hosts without a common Git remote, a later explicit Studio-mediated Git
bundle/artifact transfer can reuse the existing transfer mechanisms. It is not
part of the first flow. Joining an enclave does not imply cross-host source,
cache or credential sharing.

### State, recovery and human control

Use queued, running, succeeded, failed and cancelled execution states. Track
connection uncertainty separately: loss of SSH is not proof that the task failed.
An accepted task can continue on its host, but Studio must remain open to
coordinate subsequent steps. No unattended orchestration service in version one.
Persist the run snapshot and IDs on the Studio device and task records on the
host; on reconnect, query existing attempts before submitting more work.

Submission must be idempotent for an attempt ID. A retry creates a new attempt
only after the previous attempt's status is known; no blind redispatch after a
timeout. Limit automated execution to one active task per workspace initially.
Cancellation stops further scheduling and asks the selected adapter to stop
the owned task, then verifies its state. Process mode can terminate its owned
process tree; persistent-session mode needs a supported task-specific stop path. It does not undo commits or filesystem
changes. Closing Studio does not silently cancel remote work; warn about active
runs and reconcile their state when reopening.

The UI shows per-step progress, logs, reports, blocked/offline status and the
exact revision under review. Start is separate from saving the graph. A failed
step offers explicit retry or a human-issued correction task, without an
automatic feedback loop. Final acceptance remains with the user.

## Delivery order and acceptance gates

| Stage | Scope | Completion evidence |
| --- | --- | --- |
| 0. Isolation | Align worktree helpers/registries with reported instance paths. | Two containers with identical workspace names can create/list/remove/prune independently; default instance remains compatible. |
| 1. Identities | Studio template editor and adaptation during creation only. | Selected version is retained on the host and loaded in every workspace; existing identities cannot change; tool mismatches block creation clearly. |
| 2. Manual enclave | Arrange containers from multiple VMs, save membership and enter workspaces/agent terminals. | Reconnect preserves members/layout; manual agent sign-in works on both VMs; lines trigger nothing; offline cards remain visible; deletion preserves containers. |
| 3. One task | Studio dispatch to the existing inbox/executor through a narrow Orcan contract, with result retention. | Real task yields a validated result and logs; duplicate delivery does not duplicate work; cancel, lost connection and Studio reopen reconcile correctly; cleanup respects TTL, pins and live/dependent data. |
| 4. PR/MR review | GitHub PR and GitLab MR selection with fixed tests/review flow. | Both providers resolve pinned base/head revisions; Tester and Reviewer consume the same snapshot; changed heads mark results outdated; failures block handoff; external posting requires explicit approval. |
| 5. Engineer handoff | Add implementation output before tests/review. | An explicitly published revision reaches the next step; unavailable commits and invalid results block safely; no automatic repair loop or merge. |

The maintainer has authorized stages 0–2. The initial
product milestone ends at stage 2: a manually usable enclave. Stages 3–5 are
optional future automation, to reconsider after testing the manual workflow.
Templates and enclave/run definitions use versioned JSON in the accessible
studio-data directory beside the app, with Orcan-owned runtime/task records on
hosts. Do not introduce multi-device
editing or a central coordination database in the first version. Specify stable
server/container identification before stage 2; membership in multiple enclaves
is allowed with workspace-level execution guards. The UUID contract above defines the intended references; host
clone handling and initialization of existing installations still need design.

Manual-milestone verification must use isolated test VMs and actual Windows →
WSL2 → SSH: selected users/distributions, system/native SSH, host-key rejection,
offline provisioning, protected ttyd, independent lifecycle, identity instruction
loading, Attach, manual sign-in and reconnect to persistent sessions. Later
automation adds exact-revision fetch, cancellation, task recovery and failed review.
Unit tests do not replace this field gate. Keep manual terminal/tmux work available.
Do not rebuild or restart the maintainer's live container for these checks.

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
