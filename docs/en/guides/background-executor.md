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

## Caller contract: keep useful evidence, leave successful output on disk

Generated workspace `AGENTS.md`/`CLAUDE.md` instruct callers to use committed
procedures and consume compact results first. Configure pytest with
`--junitxml {junit}`. For Gradle and other JVM runners, declare accurate `junit`
globs for every test task in the procedure. A custom runner should emit JUnit XML
or use a reviewed wrapper that preserves the real command exit code.

Do not hide errors with `|| true` or a pipeline that turns a failing command into
success. Check that the expected report exists and the intended test scope ran;
missing XML or zero tests is not evidence that the tests passed. Set
`"require_junit": true` on test profiles to enforce this contract. The default
`minimum_tests` is 1; set a non-negative value explicitly if a different minimum
is expected. Every declared `junit` glob must match an execution-generated or
updated report, and `{junit}` output must exist when used. Missing, unchanged or
malformed reports and insufficient test counts prevent a passed result. An empty
suite is accepted only with an explicit `minimum_tests: 0` and an existing valid
report. New Python, Java and Scala test profile templates enable `require_junit`;
existing profiles keep their policy until explicitly updated.

Successful output stays in disk artifacts. Return status, exact SHA and counters;
on failure, include bounded failure diagnostics. Read a failed-case report or a
small relevant log fragment only when the compact result is insufficient. Do not
load full logs or passed-case output after success. Non-test procedures use exit
codes. Each executed step writes a separate `steps/step-NNN.log`. Its complete
output is appended to `output.log` when the step exits, including on timeout.
A failed run also writes `diagnostics.json`: counters, structured failures and
references to JUnit files and the failed step log. The notification points to this
artifact, not to a combined log tail. If no structured failure is available, it
reports the step, outcome and exit code and explains that the step artifact must
be inspected. It does not guess which raw output lines are errors. Legacy saved
results may still contain their old log-tail diagnostics.

## Configure queues and execution budgets

Use `orcan settings` to edit the executor section without changing workspaces:

```json
{
  "executor": {
    "split_lanes": false,
    "workers": 5,
    "max_running": 5,
    "max_pending": 100,
    "timeout_seconds": 1800,
    "retention_seconds": 3600,
    "redis_memory_mb": 128,
    "visibility_timeout_seconds": 86400
  }
}
```

`orcan sync` validates these values and materializes an explicitly configured
executor section into the runtime environment. Then recreate the container with
its intended access flags, including `--with-redis`. Sync alone does not restart
workers. Drain queued and running work before changing queue topology; already
pinned jobs retain their recorded lane and are not automatically migrated. Without
an executor section, existing environment settings remain valid.
`orcan-executor settings` shows the effective process settings and their source.

`workers` (1..5, default 1) starts independent Celery workers on one shared queue
when `split_lanes` is false. Each worker executes one job at a time and has its own
process lock, heartbeat and log. All profiles use the shared queue in this mode,
including profiles labelled `light` or `heavy`. Set both `workers` and
`max_running` to 5 to allow five procedures to run concurrently. Queued work
from multiple sessions waits for a free worker; repository turns still apply.
`doctor` reports `configured_workers`, `ready_workers` and individual slots per
lane. One worker stopping does not clear the other workers' readiness.
The environment equivalent is `ORCAN_EXECUTOR_WORKERS=5`.

`max_running` (1..5, default 2) is an atomic instance-wide admission cap shared by
all lanes. Workers defer capacity-blocked jobs for a later attempt without running
their procedures or consuming an execution attempt. Failed procedures are not
retried by this mechanism. Queued jobs can still be cancelled. A stale running job
after worker loss occupies capacity until explicitly recovered.

This cap limits jobs, not CPU or memory. Docker's `resources.cpus` and
`resources.memory` limits apply to the whole container. Gradle/JVM/compiler
parallelism must be set in project commands. For a small JVM environment, start
with one heavy build and a lightweight lane, then measure resource pressure.
Do not assume that three worker processes mean three total OS processes.

A profile may set `"timeout_seconds": 600`. Explicit `submit --timeout` wins,
then the committed profile timeout, then the runtime default. `max_pending`
remains 1..10000; detailed-result retention remains 60..86400 seconds.

Use `doctor --lane heavy` to require a matching live worker lock and readiness
lease. `doctor` without a lane reports whether any worker is ready. Submission
will not publish a task into an unavailable lane: it preserves a local queued job
and reports `queued_locally` with recovery instructions. Start/fix the lane worker,
then use `recover --job JOB`. Optional lane readiness is also shown by plugin doctor.

## Redis diagnostics and controlled recovery

`orcan-executor diagnostics` inspects the local instance without changing jobs.
It returns only selected numeric Redis INFO fields, AOF write status, worker
heartbeat timestamps, publication counters and execution-lock conditions. It does
not return Redis configuration, client lists, broker URLs or raw exceptions.

The maintenance service samples health about every 30 seconds and stores only the
latest bounded snapshot in SQLite. Health events wake the existing dashboard SSE
connection; they coalesce in the durable outbox during an outage. The dashboard
reads cached health without polling Redis. Its SSE keepalive also refreshes local
cached data so a stopped sampler becomes visibly stale after 90 seconds.

The Redis panel shows memory against its actual limit, AOF state, recorded key
evictions and error replies, event backlog, publication failures, lane heartbeats
and possible interrupted jobs. Communication counters are cumulative for the local
instance; Redis server counters are cumulative since its restart. Queue median/p95
use completed jobs in the selected time window. Oldest queued age and interrupted
candidates describe the current instance, not a historical window.

`executor.redis_memory_mb` accepts 32..4096 MiB (default 128) and changes the Redis
process's maxmemory budget after recreation. The noeviction policy remains: a full
broker can reject new writes, rather than silently evict task keys. This is a Redis
budget, not a whole-container reservation. Memory pressure is reported from 85%.
AOF stays enabled with fsync every second; this does not guarantee zero data loss
on host failure. Back up persistent state if needed.

`executor.visibility_timeout_seconds` accepts 22200..86400 seconds (default 86400).
The lower bound leaves a margin above the maximum six-hour task deadline. A long
visibility timeout may delay broker redelivery after a crash. Explicit recovery
can be used without waiting for it, but only after verifying execution stopped.
All workers sharing a queue must use the same visibility timeout.

A running row with a free execution lock is an interrupted-job **candidate**.
A missing heartbeat alone is insufficient: a child JVM may still hold the inherited
lock. An unreadable lock is unknown, not free. Inspection covers at most 100 active
rows, with running jobs first. Active rows are prioritized in the dashboard list.

```sh
orcan-executor diagnostics
orcan-executor doctor --lane heavy
orcan-executor recover --job JOB
```

Recovery locks the job again, rechecks its state and holds that lock through
publication. It refuses a lock held by any process, and refuses a completed job.
A confirmed interrupted row becomes queued, freeing its stale running slot. Failed
publication leaves a durable pending job for a later explicit recovery. The job's
SHA and attempt count remain pinned; previous worktrees are preserved. The existing
three-attempt interruption limit still terminates exhausted jobs without rerunning
their procedure. No failed test or uncertain Codex notification is automatically resent.

Publication states distinguish `published`, `lane_unavailable`,
`readiness_unavailable`, `uncertain`, `recovery_pending` and legacy `unknown`. An error while publishing
may mean acceptance is uncertain. Repeated delivery can happen; execution locks
and terminal-state checks prevent concurrent or completed-job execution. Stream
publication also remains at least once; consumers deduplicate event IDs.

Official references: [Redis INFO](https://redis.io/docs/latest/commands/info/) and
[Celery Redis visibility timeout](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html).

## Jobs in the cockpit and dashboard measurements

Open **Jobs** in the cockpit utility rail or **Background jobs** in its command
palette. The panel shows the instance's latest 20 jobs from the last three hours,
plus active jobs, profile queue, step, commit and readiness. Refresh explicitly
with the button or `r`; Escape closes it. It does not type into tmux or acknowledge
results. Use the shown CLI commands for result retrieval or queued cancellation.
The dashboard remains available through `orcan executor url`.

Dashboard charts use local JavaScript without a CDN. They show completed tasks,
log bytes against compact completion plus CLI detail bytes, and average queue/run
time. A table exposes the same values. Time buckets use completion timestamps;
lines connect buckets that contain completed jobs. Profile/repository/queue usage
shows which procedures used the executor.

The result-plus-details comparison is a baseline against reading all logs, not a
measurement of actual model input. Notification bytes are separate to avoid
counting a delivered result twice. A negative difference is shown honestly.
Task duration is not developer time saved. Token figures remain a bytes/4 estimate;
actual model tokens, cached input and billing costs are unavailable.

Child CPU counters cover OS-accounted waited-for child processes during the job,
including tools that exit and are reaped. They exclude still-running JVM daemons,
unreaped descendants and remote models. They are not whole-container CPU usage.

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

## First verification after startup

Run `orcan-executor doctor` inside Orcan. All readiness fields should be true.
List committed procedures with `orcan-executor profiles --repo .`, then submit
one small check from a committed revision. Save the returned job ID and SHA.

Open the dashboard to follow the job. After completion, read
`orcan-executor result JOB` and confirm that the result SHA matches the submitted
commit. Run `orcan-executor ack JOB` after reading the result. An acknowledgement
records consumption; it does not turn a failed check into a passed check.

A healthy worker alone does not verify this full path. The first completed job
checks submission, isolated worktree execution and result retrieval together.

## Heavy tasks beyond tests

When the executor is ready, agents should prefer it for approved heavy or verbose
work: compilation, builds, static analysis, code generation, reports and docs, as
well as tests. Keep quick reads and small interactive edits direct. Use a reviewed,
committed project profile; the executor is not permission to deploy or change
external systems. A missing profile must be prepared and committed first.

For example, a Java `build` profile can contain:

```json
{"steps": [{"argv": ["./gradlew", "--console=plain", "--max-workers=1", "classes"]}]}
```

Add it under `profiles` in `.orcan/checks.json` and commit. Then submit
`orcan-executor submit --repo . --sha HEAD --profile build --task compile`.
No `--test` is needed. Zero test counters mean no tests were reported, not a failed
build. Register the requesting Codex session with `--notify-codex-thread` when
available and return control; the controller delivers the compact result.
Profiles may declare output files with `artifacts` for bounded retrieval before TTL.

## Compact history and time windows

Detailed reports, logs, notification subscriptions and pinned snapshots have a
short lifetime. Compact job records and numeric measurements remain available
for **30 days**, with at most **10000 expired entries**. Cleanup strips diagnostic
text, test selectors, progress, artifact/worktree paths and the Git-directory path.
It preserves the task, repository, SHA, profile, status, timestamps, elapsed time,
test counters, byte measurements and delivery/receipt measurements. Active jobs
and dirty retained worktrees are never removed by these history limits.

The dashboard defaults to the **last 3 hours**. Choose 24 hours, 7 days or 30 days.
Counts and measurements use the selected completion-time window; active jobs are
always visible. The list shows at most 100 recent submissions.
All terminal jobs, including cancellations and jobs without metrics, count as
completed. Measured JSON lines are counted separately. The coverage note gives
sample counts for logs, results, returned bytes and durations. Recovered records
can lack notification and detail-read measurements; they are marked as partial,
not treated as measured zeros. Byte reduction compares only jobs with both log
and result measurements. Returned-byte comparisons exclude recovered records
whose detail-read history is unknown.

Counts, profile usage, durations and chart values share one SQLite read snapshot.
Charts include idle intervals: grouped bars distinguish successful, failed and
cancelled jobs; duration lines break at missing or incomplete samples. Queue p95
uses the nearest-rank percentile of individual measured jobs, not bucket averages.
The accessible data table shows missing-data coverage for incomplete buckets.

An expired entry
has no report or log link. Total execution time is measured job duration, not a
claim about saved developer/model time.

```sh
orcan-executor history --hours 3
orcan-executor stats --hours 3
```

`stats` without a window covers up to 30 days. History is local to the Orcan
instance and stored in its persistent SQLite database, not in Redis. Restarts
preserve it when the history mount is preserved. Old rows already deleted by an
earlier version cannot be recovered. Profile definitions work in an isolated
snapshot; a build that needs uncommitted local files requires a suitable committed
profile or explicitly selected directory snapshot.

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
an hour. Completed reports, logs and pinned refs are cleaned locally
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
`"default"`. With split lanes enabled, routing reads the committed procedure, not dirty configuration.
In shared-queue mode, lane labels do not create separate queues.
Keep `workers` at 1 when using split lanes; combining a shared pool with split lanes
is rejected. Set `ORCAN_EXECUTOR_SPLIT_LANES=1` when starting Orcan to supervise one additional
worker for each lane. This starts three workers, one per lane; the global max_running cap (default 2) limits simultaneous checks,
and keeps lightweight checks out of a queue occupied by JVM work. It does not impose
CPU or memory quotas. The shared pool is the simpler choice when all jobs should use the same queue.

For isolated development, foreground `orcan-executor worker --slot 2` serves a second shared-queue slot.
Use `orcan-executor worker --lane light` or
`--lane heavy` serves the corresponding queue. With split lanes enabled, a lane without a matching worker
is retained locally with queued_locally until explicitly recovered; the default worker does not steal its jobs. General `doctor`
readiness means at least one worker is available, not that every optional lane is
served. Use doctor --lane LANE and the Supervisor process list to verify enabled lane workers.

### Fair admission and pending replacement

Admission rotates repository turns within each lane. Worktrees sharing a Git common
directory share one turn. FIFO is normally preserved within a repository (with
the missing-delivery fallback below). A repository that
has not had a turn is served before one that has; otherwise the least recently
served repository goes next. A lone repository can keep using available capacity.
Only known-published queued entries and the current dequeued entry participate;
locally unsent rows do not block a healthy queue.

This is non-preemptive admission fairness, not a CPU-time quota or one global
ordering across lanes. Running work is never interrupted. Existing capacity/fairness
waits use Celery's bounded-delay retries (currently three seconds), without consuming
an execution attempt. If the same preferred queued entry is not delivered for 30
seconds, another entry may proceed and records a fairness bypass. This prevents a
lost broker message from blocking the whole lane forever; it does not restart the
missing job. The counter is visible in statistics. No separate polling agent or scheduler is started. The Jobs
panel and dashboard distinguish waiting for capacity from waiting for another repo.
Fairness records expire after 30 inactive days; active repositories remain tracked.

For a continuing task whose latest revision replaces its earlier pending check:

```sh
orcan-executor submit --repo . --sha HEAD --profile selected \
  --test tests/test_feature.py --task feature-check \
  --replace-pending feature-check --notify-codex-thread "$CODEX_THREAD_ID"
```

Use a unique group for that task/workstream. The group is 1..80 ASCII letters,
digits or `._:/-`, starting with a letter or digit. Without the flag, no existing
job is replaced. `--reuse` is a separate, mutually exclusive choice for identical
SHA checks. Replacement is unavailable for non-Git directory snapshots.

Replacement requires the same Git common directory, group, owner session, profile,
ordered selectors, lane and timeout, plus a different SHA that is a descendant of
the old SHA. For manual submissions without a notification target, the owner scope
is empty: choose a group unique to that manual workstream. No session is inferred.
A check subscribed to by another session is protected. Running or already claimed
work is protected even if its row still briefly says queued. Equal, older,
divergent or rebased commits do not automatically cancel each other.

Scoped submissions are serialized through a bounded set of 64 lock files. The scan
checks at most 100 candidates with a short ancestry-check budget; unknown or busy
candidates are preserved. Locks are held through a single SQLite transaction that
cancels eligible old rows and accepts the new row. Replaced jobs release queue
capacity, so a full queue can accept their replacement atomically. A failed new
admission does not cancel old work.

Old entries become `cancelled`, retain `superseded_by` pointing to the new job and
keep their pinned refs until artifact TTL cleanup. Existing notification subscribers
receive a cancellation with that link. The dashboard counts replaced entries but
records no execution duration or test run for them. A superseded result is **not**
acceptance of the new commit. Read and acknowledge the new job's exact-SHA result.
If the broker is unavailable, replacement metadata remains durable and the new job
reports queued_locally; explicitly recover it after readiness is restored.

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

Notification delivery is limited by the default one-hour detailed-result TTL; compact delivery states and numeric measurements remain with history. Queued
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
