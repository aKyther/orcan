---
description: Add JSON and Bash actions, test local recognition, and confirm before execution.
---

# Offline actions (experimental)

Repeated requests such as “run the tests” should lead to a known operation in the
right project. Orcan actions pair a description and example requests with a Bash
script. A local recognizer proposes an action; you inspect and confirm it before
anything runs. This is a terminal experiment, separate from the coding agent's
chat and the Studio canvas.

Two recognizers use the same files:

- **scikit-learn**, the default: character and word TF-IDF features with logistic
  regression, trained locally from examples. No downloaded model or network.
- **Ollama**, optional: sends the catalog to an already running local model. It
  can interpret broader requests, but its accuracy and resource cost need testing.
  There is no cloud fallback, model installation or automatic model selection.

## Try one action inside Orcan

Run from the project directory, inside a container built with this feature:
The scikit-learn backend also needs the optional ML environment described below.

```bash
orcan-actions init hello
orcan-actions list
orcan-actions suggest "powiedz mi czesc"
orcan-actions ask "powiedz mi czesc"
```

`suggest` returns JSON and executes nothing. `ask` shows the proposed action,
project directory and script contents. Enter `y` or `tak` to run it, an action
number to choose a different action, or Enter to cancel. Selecting a number
shows that action and requires a separate confirmation. There is no `--yes` flag.

The greeting script prints its project directory, so it is a small end-to-end
check. Discovery and copying an example never execute it. `init` refuses to
overwrite an existing directory.

On the host, use `orcan actions` with the same arguments. Host commands execute
on the host; the container helper executes inside the container. Use `--project
/absolute/project/path` before the subcommand to select an explicit project.
Neither path implicitly attaches to Docker or intercepts coding-agent messages.

## Add your own JSON + script

Each immediate subdirectory of `.orcan/actions/` is one action:

```text
.orcan/actions/tests-host/
├── action.json
└── run.sh
```

For the Orcan checkout, copy the test example:

```bash
orcan-actions init tests-host
orcan-actions ask "przetestuj moje zmiany bez budowania dockera"
```

Its JSON looks like this (shortened example list):

```json
{
  "id": "tests.host",
  "name": "Testy hosta",
  "description": "Testy hosta Orcana bez budowania obrazu Docker.",
  "examples": [
    "uruchom testy hosta",
    "przetestuj zmiany lokalnie",
    "sprawdź kod testami bez budowania dockera"
  ],
  "script": "run.sh"
}
```

```bash
#!/usr/bin/env bash
set -euo pipefail
export UV_OFFLINE=1
make test-host
```

Edit these two files for another project. The test example requires the Orcan
checkout and cached uv test dependencies. `diff-check` is another bundled example
that runs `git diff --check`; it is not a full linter.

Examples describe intent, not exact aliases. Start with at least 3 varied examples per
action. More distinct actions are easier to separate than several actions called
“check everything.” The prototype supports up to 32 actions. IDs must be unique,
and the script must be a regular `.sh` file in its action directory. Scripts run
with the project as their working directory. Request text is never interpolated
into Bash. Scripts retain normal access to the environment where you run them;
use trusted scripts and inspect the displayed code.

## How examples improve recognition

After confirmation, Orcan appends your wording directly to `examples` in the
selected alias's `action.json`. For example, confirming “wez pusc te tsty frnotu”
for frontend tests teaches that wording to the frontend alias. The Bash script
does not change. Correcting a proposal teaches the alias you selected, not the
original proposal. Cancelling changes no examples.

Duplicate wording is ignored after normalizing case and whitespace. Each alias
can hold up to 200 examples within its 64 KiB JSON budget. A phrase already
assigned to another alias is reported as a conflict; edit those examples before
reassigning it. Writes preserve file permissions and replace the JSON atomically.
Concurrent Orcan learners serialize writes; changed definitions/scripts require
a fresh review. Other editors should avoid saving during the short learning step.
If learning fails, the command stops before executing the script.

scikit-learn fits a small classifier once per invocation from these JSON examples.
Your saved wording participates on the next invocation, without downloading or
loading executable model files. A later script failure does not undo learning:
confirmation established the intended alias, independently of execution success.

Older `.orcan/action-feedback.jsonl` files remain readable for compatibility but
are no longer written. JSON examples take precedence. Historical records are used
only while their action revision still matches. Keep old feedback files out of
Git; definitions and the learned JSON examples can be versioned together.

A high classifier score is not a guarantee of correct intent. Low scores or
close alternatives produce no proposal; you can choose an action yourself. The
bundled “other” examples include questions, negations and compound requests.
Always review the proposal, especially with newly added actions.

## Compare recognition without running scripts

The checkout includes 24 evaluation requests, separate from training examples:
Polish, English, missing accents, typos, questions, negations and unsupported
operations. Evaluation ignores personal feedback and never runs scripts.

```bash
orcan-actions init diff-check
orcan-actions evaluate /absolute/orcan/tests/fixtures/actions/holdout.json
```

Install all three examples before using this particular evaluation file. Once you
teach an evaluation phrase, it is a training example rather than an unseen test.
The report flags overlapping requests. The
JSON report includes per-request results, exact-match baseline results, false
proposals and setup time. It is a small regression fixture, not evidence of
general language understanding. Keep your own unseen evaluation requests outside
action examples and feedback when comparing approaches.

## Optional local Ollama

If Ollama and the model already exist in the same container, start the server
with cloud features disabled, then select the exact installed local model:

```bash
OLLAMA_NO_CLOUD=1 OLLAMA_HOST=127.0.0.1:11434 ollama serve
# In a second terminal, replace local-model:tag with your installed model:
orcan-actions --backend ollama --model local-model:tag ask "odpal tsty"
orcan-actions --backend ollama --model local-model:tag evaluate /absolute/orcan/tests/fixtures/actions/holdout.json
```

The adapter uses only `127.0.0.1`, checks the local model list, rejects cloud
model names, and requests a schema-constrained action ID or `null`. It does not
send scripts, tool definitions, repository contents or a conversation transcript.
It never calls a pull endpoint, follows redirects, uses proxy variables or falls
back to another backend. Missing models and invalid responses fail explicitly.
Catalog/request context is capped at 6000 UTF-8 bytes to avoid silent truncation;
shorten descriptions or examples if the helper reports this limit.
The server itself must also be configured for local-only use.

For a separate Docker experiment, the checkout provides
`examples/actions/compose.ollama.yml`. Set these variables to existing local
resources, using canonical absolute host paths for mounts:

```bash
export OLLAMA_IMAGE=ollama/ollama:YOUR_INSTALLED_TAG
export OLLAMA_MODELS_DIR=/absolute/existing/ollama-model-store
export ORCAN_ACTIONS_MODEL=local-model:tag
export ORCAN_SOURCE_DIR=/absolute/orcan
export ACTIONS_PROJECT_DIR=/absolute/project
docker compose --env-file /dev/null -f "$ORCAN_SOURCE_DIR/examples/actions/compose.ollama.yml" run --rm actions init hello
docker compose --env-file /dev/null -f "$ORCAN_SOURCE_DIR/examples/actions/compose.ollama.yml" run --rm actions ask "powiedz mi czesc"
docker compose --env-file /dev/null -f "$ORCAN_SOURCE_DIR/examples/actions/compose.ollama.yml" down
```

This stack uses an internal network, no published ports, no Docker socket, and
no image pulls. The client shares the Ollama network namespace, so loopback works
between them. The model store is mounted read-only. No model is supplied: preload
or transfer a model store before going offline. The default CPU/memory limits are
only a starting point; adjust them to your chosen model. Ollama is not included
in the Orcan image and this experiment does not change the live Orcan container.

Ollama documents [local-only mode](https://docs.ollama.com/faq#how-do-i-disable-ollamas-cloud-features)
and [structured outputs](https://docs.ollama.com/capabilities/structured-outputs).

## Checkout development

The default image includes the helper and examples without the roughly 207 MiB
scikit-learn environment measured during development. To include that optional
environment at build time, set `INSTALL_ACTIONS_ML=1` on the host:

```bash
INSTALL_ACTIONS_ML=1 orcan build --agent codex
```

This installs scikit-learn in `/opt/orcan-actions/venv`, separately from context
helpers and the cockpit. The default is `0`; Ollama needs no scikit-learn packages.
Runtime recognition makes no package downloads.
For host development, prepare a separate uv environment once:

```bash
uv venv /absolute/actions-venv
uv pip install --python /absolute/actions-venv/bin/python -r requirements-actions.txt
export ORCAN_ACTIONS_PYTHON=/absolute/actions-venv/bin/python
./bin/orcan actions --project /absolute/project suggest "zrub testy"
```

Package installation needs a package source or preloaded wheel cache; the
installed classifier itself works offline. An updated image is required for the
installed container helper. Checkout development can invoke the helper directly
without rebuilding or restarting the live container.
