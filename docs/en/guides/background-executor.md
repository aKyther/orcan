# Background executor

Long checks can fill an agent conversation with build output and delay the next
turn. The optional Redis module runs project procedures in the background, checks
an exact Git commit and sends a small result. Success carries counters, not logs.
Failures carry up to three short test messages. Read long diagnostics in chunks.

## Enable the module

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

Plain `orcan up` disables the module; `orcan up --resume` restores the saved choice.
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
