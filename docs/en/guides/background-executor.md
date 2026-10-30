# Background executor

Long checks can fill an agent conversation with build output and delay the next
turn. The optional executor plugin runs project procedures in the background, checks
an exact Git commit and sends a small result. Success carries counters, not logs.
Failures carry up to three short test messages. Read long diagnostics in chunks.

## Enable the plugin

Build an updated Orcan image, then start it from the host:

```sh
orcan up --with-redis
orcan executor doctor
```

The flag enables Redis, one Celery worker, retention maintenance and a read-only
FastAPI/Uvicorn dashboard in the **same Orcan container**, managed by Supervisor. Redis is
bound to container loopback and has no published port. The dashboard is published
at a **separate port on the same host/Tailscale binding as ttyd**. The default
is port 8765, for example `http://YOUR-TAILSCALE-IP:8765/`.
`TTYD_BIND` selects the shared host interface; set it to the host's Tailscale IP
for a Tailscale-only bind. `ORCAN_EXECUTOR_PORT` changes the dashboard port without
changing ttyd. `orcan executor url` prints the URL; wildcard binds print localhost,
so use the host's Tailscale address when opening it from another device.
`--web-terminal-auth USER:PASS` also protects the dashboard with the same credentials.
Redis remains on container loopback with no published port.

Plain `orcan up` disables the plugin; `orcan up --resume` restores the saved choice.
It combines with existing SSH, Docker, network and terminal flags. No Docker socket
is required by the executor itself. Services run as the existing developer user.
Dependencies are locked in a separate Python 3.12 environment in the image.

Workspace `AGENTS.md` and `CLAUDE.md` are generated at startup and reconcile. They
show the configured state and teach agents how to submit and consume results.
A configured flag is not health: `doctor` checks broker and local worker readiness.
When disabled or unavailable, agents use the usual direct workflow.

## Commands for users and agents

Use `orcan executor help` on the host, or `orcan-executor help` inside Orcan.
`orcan executor url` prints the dashboard URL. The built image installs the CLI,
locked dependencies and supervised services; users do not need manual uv, Redis,
Celery or Uvicorn commands. Host commands take the same subcommands and canonical
repository paths as the container CLI. `orcan up --with-redis` is the only runtime
opt-in. Agents learn these commands from their generated workspace context.

## Define project procedures

Inside Orcan, in a project:

```sh
orcan-executor init --repo . --kind python
# Review .orcan/checks.json, adjust commands and commit it with your changes.
orcan-executor profiles --repo .
```

Choose `python`, `java`, `scala` or `custom`. This scaffolds a JSON configuration;
it does not install project tools or overwrite an existing file. Python examples
use locked uv dependencies, pytest, Ruff and MkDocs. Java uses the project Gradle
wrapper, including a `java/` subdirectory when present. Scala uses sbt. Adjust
profiles for Maven, multi-module builds, Scala on Gradle or other project layouts.
Required tools and project dependencies must already be available to Orcan.

```json
{
  "version": 1,
  "profiles": {
    "selected": {
      "requires_tests": true,
      "steps": [
        {"argv": ["uv", "run", "--locked", "pytest", "-q", "{tests}", "--junitxml", "{junit}"], "cwd": "."}
      ]
    },
    "docs": {
      "steps": [{"argv": ["uv", "run", "--locked", "mkdocs", "build", "--strict"]}]
    }
  }
}
```

Procedures are read from the submitted commit, not mutable agent files. Each step
is an argument array executed directly, without a shell. `cwd` is relative to the
snapshot. Multiple steps run in order and stop on failure. Approved scripts can be
called explicitly. These procedures have developer access: review them as code.
They are not a security sandbox, and ignored local credentials are not copied.

Standalone placeholders expand to arguments: `{tests}` for pytest node IDs,
`{gradle_tests}` for repeated `--tests` options, `{sbt_tests}` for a `testOnly`
command and `{junit}` for an executor-owned JUnit XML path. JVM procedures list
snapshot-relative `junit` globs, such as `build/test-results/test/*.xml` or
`target/test-reports/*.xml`. pytest and JVM XML produce the same test counters,
skip counts and bounded failure summaries. A procedure without XML reports its
exit status; zero test counters do not claim tests ran.

## Submit and receive

```sh
orcan-executor submit --repo . --sha HEAD --profile selected \
  --test tests/test_feature.py --task feature-change
# Java: --test 'example.FeatureTest.method'
# Scala: --test 'example.FeatureSpec'
# Documentation: --profile docs, without --test
```

Commit first. Submission returns a job ID and full SHA immediately. The worker
creates a detached worktree using the durable Git common directory and pins
`refs/orcan/executor/jobs/JOB`. Removing an agent branch or task worktree does not
lose the queued snapshot. Keep the underlying Git repository accessible.
The agent returns to the conversation. New edits need a new commit and job.
Full suites and coverage require an explicit profile/scope choice.

A **separate controller process**, not an interactive agent tool call, owns:

```sh
orcan-executor listen --after 0-0
```

Each completion is one JSON line. Save `stream_id` and resume with `--after ID`.
Delivery is at least once; deduplicate `event_id` within this executor state.
The listener does not invoke a model or resume a chat. Controller integration is
needed to deliver a new turn. `wait JOB --timeout SECONDS` is only for scripts
that deliberately block. Without that integration, return verification as pending.

```sh
orcan-executor result JOB
orcan-executor logs JOB --offset 0 --limit 4000
orcan-executor artifacts JOB
orcan-executor logs JOB --artifact report.json --offset 0 --limit 4000
```

Use `artifacts --after NAME` for the next page of XML/report filenames.
Artifact reads support long failure traces without a full model-facing dump.
Log reads return `next_offset` and `more`; each read is capped at 16000 bytes.
`result --full` gives artifact paths rather than dumping full traces into the model.
The dashboard offers full JSON and log downloads. It has no submit, merge or deploy
controls. Successful stdout never enters a completion event. A passed result means
no detected error in that procedure; skipped integration tests did not run.

## Communication and retention

Celery uses a dedicated Redis queue, late acknowledgements and one prefetched job.
Per-job OS locks prevent duplicate active execution. There is no automatic retry
of failed tests. Redis Streams carry queued, running, procedure-step and completed
events. The dashboard consumes them through blocking reads and SSE; the agent
listener emits only completed results. No periodic model/status polling is needed.

The default retention is **3600 seconds after completion**. Set
`ORCAN_EXECUTOR_RETENTION_SECONDS` at `orcan up` to a value from 60 to 86400.
Stream entries are age-trimmed and capped at 10000; an inactive stream expires.
Under high volume, a stream cursor can fall behind the retained history before
an hour. Completed reports, logs, SQLite rows and pinned refs are cleaned locally
within roughly 30 seconds after their deadline. Unread results can expire too.
Save evidence you need before that deadline. Active and queued jobs do not expire.
Dirty retained worktrees keep their job evidence until safe cleanup is possible.

SQLite is the durable job/outbox store; files hold full logs and XML. They live
under `~/.local/share/orcan/history/executor/INSTANCE` (default instance: `default`), in the existing persistent history
mount. Named instances use separate state and default queue names. Redis uses AOF and a 128 MiB no-eviction limit. Large log files are never
copied into broker memory. Queue/outbox publication failures leave local evidence;
commands do not expose credential-bearing broker errors.

```sh
orcan-executor recover --job JOB       # explicitly requeue a pending/interrupted job
orcan-executor recover                # publish pending events
orcan-executor recover --replay-events
```

Stop an old worker/build before recovering an interrupted job. A build inherits
its job lock so recovery cannot run another copy while that build survives.
No result implies automatic acceptance: verify the exact committed SHA. No merge,
push, deployment, remote execution or automatic AI invocation is added.


## Check whether the flow helps

The dashboard measures usage and data reduction globally and for each retained job:
queue time, execution time, procedure scope, full-log bytes/lines, and completion
JSON bytes/lines. Sizes use UTF-8 and count the final model-facing JSON line, excluding the Redis
stream cursor added by the listener. Dashboard metrics stay in Redis/local state
and are stripped from agent completion messages. Counts and reduction
are exact for those artifacts. This is a comparison against sending the full log,
not proof that a particular agent would otherwise have read that entire log.
It does not include total transport traffic or separately requested diagnostic chunks.

Reduction can be negative for a small quiet check. The UI preserves that result.
Estimated avoided tokens use a simple four-bytes-per-token heuristic. They are not
billed tokens or a measured model CPU/GPU saving. Executor CPU measures only the
Python worker's user/system CPU during the job, excluding build subprocesses and
models. The log scan is chunked; full failure traces remain in saved XML.
Statistics cover the current retention window, not a permanent usage ledger.

Use short background checks when the exact snapshot, compact result or isolation
helps. Use longer procedures to avoid tying up an agent turn while a build runs.
Combine related checks in a profile when they share a snapshot. Selected pytest
node IDs, Java methods or Scala suites keep scope small; broader suites remain an
explicit choice. Even without a byte saving, a separate process and worktree can
be useful. Background execution itself does not promise faster test execution.


## Executor stress and resilience checks

`uv run --project executor --locked python executor/smoke/run.py` runs an isolated
same-container Redis/Celery/Supervisor fixture, using the installed Orcan image as
a base. It never changes the live Orcan container or its image tag. The fixture
submits 50 actual pytest jobs through eight producers, with ten duplicate queue
deliveries and a deliberate 40-pass/10-failure split. It checks one execution per
job, exact SHA, safe worktree cleanup, bounded agent output and a consumer reconnect
after 25 completions. It also checks a stopped/restarted worker, broker outage with
a durable submission and explicit recovery, event replay, and TTL cleanup while
preserving queued work. These are local functional measurements, not a production
throughput guarantee or a full JVM run.

A profile may declare `artifacts` as snapshot-relative file globs. The executor
archives matching files before removing its checkout, including diagnostic logs
when a step fails. Full files follow the same completed-job TTL and remain available
through `artifacts` / bounded `logs --artifact ...` reads. Orcan's `executor-final`
profile uses this to preserve smoke reports and Supervisor logs from nested worktrees.
Supervisor's fixture socket uses a short container-local path, since Unix sockets
have a small path limit; diagnostic files are copied to the retained report.

## Executor plugin, admission and consumption

The plugin ID is `executor`; Redis is its internal communication broker, not the
execution engine. `--with-redis` remains the activation flag for compatibility.
Use `orcan plugins list`, `orcan plugins validate` and
`orcan plugins doctor --plugin executor`. Descriptors live in `plugins/` and do
not execute third-party hooks. No agent message is sent without explicit notification opt-in; no merge or deployment starts automatically.

Each project owns named procedures in `.orcan/checks.json`. Python/pytest,
Java/Gradle, Scala/sbt, lint, documentation and small custom checks use the same
submit/result flow. Choose a scoped procedure rather than silently running a full
suite. Success reports contain counters; failures contain bounded excerpts with
an explicit count of omitted failures. Use `artifacts` and paginated `logs` to
consume all relevant long traces or JUnit XML, without dumping them into context.

```sh
orcan-executor submit --repo . --sha HEAD --profile selected --test tests/test_api.py --reuse
orcan-executor cancel JOB_ID
orcan-executor ack JOB_ID
```

`--reuse` atomically reuses an identical queued or running check (same Git common
directory, SHA, procedure, selectors and timeout). Completed checks are not silently
reused. The returned job may retain its original task label. Without this option,
independent repeated checks remain possible. `cancel` only cancels queued work;
it never terminates an agent or a running build. Late deliveries of a cancelled
job perform no checks. Cancellation also frees admission capacity.

`ack` explicitly records that a terminal result was consumed. It is idempotent,
does not delete the report, and does not mean the code passed or was accepted.
Listening and displaying a result alone do not prove it was consumed. The dashboard
shows confirmed receipts, CLI detail-read counts/bytes, and log/result sizes grouped
by status. This separates successful-output suppression from failure compaction.
These measurements exclude model CPU/GPU and do not claim measured token savings.

The default admission limit is **100 queued plus running jobs**, enforced atomically
across producers. Set `ORCAN_EXECUTOR_MAX_PENDING=50` before starting Orcan to change
it (range 1..10000). Queue saturation rejects new work with a short actionable error;
it never drops an existing task. Each worker has prefetch one and executes one task
at a time. Avoid raising parallelism blindly on memory-constrained JVM workloads.

### Separate lightweight and heavyweight queues

A procedure can declare `"lane": "light"` or `"lane": "heavy"`; omitted means
`"default"`. Routing reads the committed procedure, not dirty configuration.
Set `ORCAN_EXECUTOR_SPLIT_LANES=1` when starting Orcan to supervise one additional
worker for each lane. This permits at most three simultaneous checks, one per lane,
and keeps lightweight checks out of a queue occupied by JVM work. It does not impose
CPU or memory quotas. Keep it disabled on small machines unless needed.

For isolated development, foreground `orcan-executor worker --lane light` or
`--lane heavy` serves the corresponding queue. A lane without a matching worker
remains queued; the default worker does not steal its jobs. General `doctor`
readiness means at least one worker is available, not that every optional lane is
served. Use the Supervisor process list to verify enabled lane workers.

### Recovery and retention

Celery uses late acknowledgements, JSON messages, prefetch one and redelivery after
worker loss. Per-job locks and terminal-state checks prevent duplicate execution.
Interrupted execution can be recovered explicitly with `recover --job JOB_ID`;
after three interrupted starts the job becomes an infrastructure error. Ordinary
test failures and timeouts are terminal, never automatically retried until green.
A broker's visibility timeout can delay redelivery; explicit recovery is the prompt
operator path after checking the previous process has stopped. Child build processes
inherit the execution lock, preventing a second run while an orphan still executes.

Completed communication/report retention defaults to **one hour**, including
cancelled jobs. Active jobs are not expired with their results. Worker readiness
has a renewable 45-second Redis lease. Durable local metadata and a transactional
outbox permit event recovery after broker loss. Redis Streams carry bounded events;
full logs and report files stay local. Dirty retained worktrees remain protected.

## Projects without Git

Use an explicit directory snapshot; Orcan does not initialize or modify Git in the
source project. Scaffold `.orcan/checks.json`, then select the source files required
by the chosen procedure:

```sh
orcan-executor init --repo /projects/plain --kind python
orcan-executor submit --repo /projects/plain --directory \
  --include pyproject.toml --include uv.lock \
  --include app.py --include tests/test_app.py \
  --profile selected --test tests/test_app.py --reuse
```

The procedure configuration is included automatically. Every `--include` names one
regular project-relative file; directory traversal, symlinks, Git metadata, `.env`
files, `runtime.conf` and named SSH private keys are rejected before reading them.
There is no recursive scan or automatic copying of dependencies, caches or secrets.
Limit: 512 files, 8 MiB per file and 32 MiB total. This explicit mode is intended for
small source sets; large projects should use a normal Git workflow.

Orcan privately packages these files in an executor-owned Git snapshot, pins its
commit and uses the existing isolated-worktree pipeline. The SHA identifies that
snapshot, **not a commit in the user's project**. Selected files and execute bits
are stable; edits in the source after submission do not affect execution. Identical
snapshots are reusable. Unreferenced owned source caches expire after the retention
period; caches referenced by active or retained jobs remain available. Project
`.git` metadata, agent worktrees and original files are untouched.

## Deliver compact results to a Codex session

The executor can opt in to **local** `codex queue` notifications. A dedicated
Supervisor service (`executor-notifications`) consumes Redis Stream events and
passes a bounded result to the explicitly selected conversation. It does not type
into tmux, open a separate chat, choose a model, or use a remote execution endpoint.
The normal submit/listen flow remains unchanged when no destination is registered.

```sh
# Run inside the Codex session that requested the check.
# Use CODEX_THREAD_ID only when supplied by that session; never guess a destination.
orcan-executor submit --repo . --sha HEAD --profile selected \
  --test tests/test_api.py --task api-check --reuse \
  --notify-codex-thread "$CODEX_THREAD_ID"

# Or attach a known session UUID to an existing job, including a completed job:
orcan-executor notify JOB_ID --codex-thread SESSION_UUID
orcan-executor deliveries --job JOB_ID

# After the target agent actually consumes the result:
orcan-executor ack JOB_ID --codex-thread SESSION_UUID
orcan-executor stats
```

All commands also work through `orcan executor` on the host. UUIDs are required;
session names, `--last`, and inferred destinations are intentionally unsupported.
Empty or invalid submit destinations are rejected before creating a job. `--reuse`
can share an active check between sessions; each session has an independent delivery
record, with at most 16 subscriptions per job. Re-registering the same job and UUID
is idempotent. A notification contains at most **4096 UTF-8 bytes**: job ID, exact
SHA, status, counters, bounded failure excerpts, and commands for details and receipt.
Successful stdout and dashboard instrumentation are excluded. Diagnostic excerpts
are explicitly marked as untrusted project output.

| State | Meaning |
| --- | --- |
| `pending` | Registered; waiting for a terminal result or the controller |
| `sending` | The controller has claimed the attempt |
| `queued` | `codex queue` exited successfully; consumption is unconfirmed |
| `consumed` | The specific session explicitly acknowledged the result |
| `unavailable` | Codex could not be started; no delivery was attempted |
| `unknown` | Timeout, nonzero exit, or an interrupted attempt; acceptance is uncertain |

The controller has a single local process lock. Per-job execution locks and an
atomic delivery claim prevent duplicate attempts from replayed events or concurrent
handlers. On restart, durable pending registrations are recovered even if Redis
history has been lost or trimmed. Broker reconnection retries transport only.
A registration for a running job waits for its completion event.

**This adapter does not claim exactly-once delivery.** The CLI does not let Orcan
supply a provider idempotency key. A crash after Codex accepted a message but before
Orcan stored the outcome is ambiguous. `sending` becomes `unknown` on controller
restart, with no automatic resend. Nonzero exits and timeouts are also not retried.
Re-registering preserves these states; inspect the target queue before manually
sending a replacement. This first adapter has no automatic retry for unavailable
Codex either. Install/select Codex and verify the controller before opting in.

A successful CLI exit means the message was queued, not that an active turn was
steered or an idle conversation started working. Delivery depends on the Codex
session consuming its queue. A session receipt confirms reading, **not that the
checks passed, the commit is accepted, or code should be merged**. Standard `ack JOB`
records job consumption without claiming consumption by any specific session.

Install a Codex image profile that includes a CLI with `codex queue --help` support.
After upgrading Orcan, rebuild the image and recreate the container with
`--with-redis` to install the supervised controller. `orcan sync` updates generated
agent guidance but cannot add a service or binary to an older running image.
Use the existing `orcan-supervisor-status` helper inside Orcan to inspect services. A manually started controller must run in
its own process, never as an indefinite listener in an interactive agent turn.

Notification records share the job's default one-hour completed-result TTL. Queued
or running jobs and their registrations are retained; notification attempts hold
the same lock as cleanup. Expiry is not proof that a message was consumed, and
local expiry cannot delete a message already accepted by Codex.

The supported command is documented in the [Codex CLI reference](https://learn.chatgpt.com/docs/developer-commands).
The [App Server protocol](https://learn.chatgpt.com/docs/app-server) exposes session
and turn operations over JSON-RPC. A future adapter can use that protocol to track
queue identifiers and active turns directly; this implementation invokes the CLI.

## Measure the benefit without inventing model usage

Celery schedules work; **compacting the output** reduces the text supplied to the
agent. The dashboard and `stats` distinguish:

- Full log bytes/lines versus canonical compact completion JSONL bytes. Reduction
  may be negative for quiet tasks. Success and failure totals are also shown separately.
- Raw detail bytes versus the exact emitted CLI JSONL bytes, including escaping and
  metadata. Re-reading a chunk counts again. Dashboard downloads are not CLI reads.
- Notification payload bytes attempted, accepted by the Codex queue, explicitly
  consumed by sessions, and of uncertain status. Acknowledging a session does not
  count its message twice. Shared checks may produce one notification per session.
- Queue time, execution time, and local adapter duration. Adapter duration includes
  the CLI operation, not model response time. Executor CPU measures only the Python
  executor process, excluding child tools and model CPU/GPU.

Do not add canonical completion bytes to notification bytes as if both were always
read by the same agent: these are separate delivery paths, not a complete ledger of
all agent input. The reports do not count the rest of a conversation or tool usage.

Token estimates use a labeled **UTF-8 bytes / 4 heuristic**. They are not tokenizer
counts or measured token savings. Codex queue does not return provider usage,
cached-input counts, reasoning/output tokens or billing cost; `stats` reports
measured model tokens and cost as unavailable. Fewer payload bytes do not establish
how much model compute, cost or wall time was saved. Provider-reported usage would
need a separate session integration and an explicit comparison baseline.

For evaluation, compare the same procedure, SHA and test scope. Inspect failures
separately: a compact error is useful only if the agent can recover the necessary
trace through bounded reads. Watch pending/unknown notifications, receipt counts,
queue delays and repeated detail reads alongside byte reduction. Statistics cover
retained jobs, not an unbounded lifetime history.
