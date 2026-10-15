"""Offline recognition and confirmed actions; no model/command may execute implicitly."""

import importlib.util
import json
import socket
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "orcan_actions", ROOT / "docker/rootfs/usr/local/lib/orcan/actions.py"
)
actions = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = actions
SPEC.loader.exec_module(actions)


@pytest.fixture
def project(tmp_path):
    for name in ("hello", "tests-host", "diff-check"):
        actions.add_example(tmp_path, name)
    return tmp_path


@pytest.fixture(scope="module")
def catalog(tmp_path_factory):
    root = tmp_path_factory.mktemp("action-catalog")
    for name in ("hello", "tests-host", "diff-check"):
        actions.add_example(root, name)
    return actions.load_actions(root)


@pytest.fixture(scope="module")
def recognizer(catalog):
    return actions.Recognizer(catalog)


def test_real_classifier_beats_exact_matching_on_separate_examples(
    catalog, recognizer, monkeypatch
):
    def offline(*args, **kwargs):
        raise AssertionError("Offline classifier attempted a network connection")

    monkeypatch.setattr(socket, "create_connection", offline)
    cases = json.loads((ROOT / "tests/fixtures/actions/holdout.json").read_text())
    # Reuse the fitted model; the evaluation path itself must not use feedback.
    result = actions.evaluate(catalog, cases, lambda _: recognizer)
    assert result["cases"] == 24
    assert result["correct"] >= 20
    assert result["correct"] > result["exact_correct"]
    assert result["false_proposals"] == 0
    assert recognizer.predict("zrub testy")["action_id"] == "tests.host"
    assert recognizer.predict("sprawdz biale znaki")["action_id"] == "diff.check"


def test_approved_correction_improves_previously_uncertain_phrase(project, recognizer):
    catalog = actions.load_actions(project)
    selected = next(a for a in catalog if a.id == "tests.host")
    original_script = selected.script.read_bytes()
    actions.remember(project, "odpal tsty", selected)
    updated = actions.load_actions(project)
    learned = actions.Recognizer(updated)
    assert learned.predict("odpal tsty")["action_id"] == "tests.host"
    definition = json.loads((selected.script.parent / "action.json").read_text())
    assert definition["examples"][-1] == "odpal tsty"
    assert selected.script.read_bytes() == original_script
    assert not actions.feedback_path(project).exists()
    report = actions.evaluate(
        updated, [{"text": "odpal tsty", "expected": "tests.host"}], lambda _: learned
    )
    assert report["training_overlap"] == 1


def test_new_action_can_cover_a_previously_unknown_request(tmp_path):
    actions.add_example(tmp_path, "hello")
    path = tmp_path / ".orcan/actions/hello/action.json"
    definition = json.loads(path.read_text())
    definition.update(
        id="build.local",
        name="Build",
        description="Build the project",
        examples=["build the docker image", "zbuduj obraz docker", "zbuduj dockera"],
    )
    path.write_text(json.dumps(definition))
    model = actions.Recognizer(actions.load_actions(tmp_path))
    assert model.predict("build the docker image")["action_id"] == "build.local"


def test_conflicting_training_examples_are_reported(project):
    path = project / ".orcan/actions/hello/action.json"
    definition = json.loads(path.read_text())
    definition["examples"].append("zrób testy")
    path.write_text(json.dumps(definition))
    with pytest.raises(ValueError, match="two actions"):
        actions.Recognizer(actions.load_actions(project))


def test_decline_never_executes_or_learns(project, monkeypatch):
    catalog = actions.load_actions(project)
    before = {a.id: (a.script.parent / "action.json").read_bytes() for a in catalog}
    answers = iter(["n"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert (
        actions.ask(project, "powiedz czesc", catalog, {"action_id": "demo.hello"}) == 0
    )
    assert not actions.feedback_path(project).exists()
    assert {
        a.id: (a.script.parent / "action.json").read_bytes() for a in catalog
    } == before


def test_uncertain_request_does_not_choose_first_action(project, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "")
    assert (
        actions.ask(
            project, "unknown", actions.load_actions(project), {"action_id": None}
        )
        == 0
    )
    assert not actions.feedback_path(project).exists()


def test_script_change_after_review_prevents_run_and_feedback(project, monkeypatch):
    catalog = actions.load_actions(project)
    hello = next(a for a in catalog if a.id == "demo.hello")
    answers = iter(["y"])

    def answer(_):
        value = next(answers)
        if value == "y":
            hello.script.write_text("echo changed")
        return value

    monkeypatch.setattr("builtins.input", answer)
    with pytest.raises(ValueError, match="changed"):
        actions.ask(project, "hello", catalog, {"action_id": "demo.hello"})
    assert not actions.feedback_path(project).exists()


@pytest.mark.parametrize(
    "script", ["../outside.sh", "/tmp/outside.sh", "run.sh;echo x", ".env"]
)
def test_script_path_must_stay_within_action(project, script):
    path = project / ".orcan/actions/hello/action.json"
    definition = json.loads(path.read_text())
    definition["script"] = script
    path.write_text(json.dumps(definition))
    with pytest.raises(ValueError, match="script must"):
        actions.load_actions(project)


def test_rejects_duplicate_ids_and_never_overwrites_example(project):
    with pytest.raises(ValueError, match="already exists"):
        actions.add_example(project, "hello")
    path = project / ".orcan/actions/diff-check/action.json"
    definition = json.loads(path.read_text())
    definition["id"] = "demo.hello"
    path.write_text(json.dumps(definition))
    with pytest.raises(ValueError, match="Duplicate"):
        actions.load_actions(project)


@pytest.mark.parametrize(
    "target",
    [".orcan", ".orcan/actions", ".orcan/actions/hello", ".orcan/actions/hello/run.sh"],
)
def test_rejects_symlinked_action_paths(tmp_path, target):
    project = tmp_path / "project"
    project.mkdir()
    actions.add_example(project, "hello")
    path = project / target
    moved = tmp_path / "moved"
    path.rename(moved)
    path.symlink_to(moved)
    with pytest.raises(ValueError, match="symlink|regular file"):
        actions.load_actions(project)


def test_suggest_and_evaluate_do_not_write_or_execute(project, monkeypatch, capsys):
    monkeypatch.setattr(
        actions, "execute", lambda *args: pytest.fail("unexpected execution")
    )
    assert actions.main(["--project", str(project), "suggest", "zrub testy"]) == 0
    assert json.loads(capsys.readouterr().out)["action_id"] == "tests.host"
    assert not actions.feedback_path(project).exists()
    assert (
        actions.main(
            [
                "--project",
                str(project),
                "evaluate",
                str(ROOT / "tests/fixtures/actions/holdout.json"),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["false_proposals"] == 0
    assert not actions.feedback_path(project).exists()


def test_ollama_schema_and_local_catalog_contract(catalog, monkeypatch):
    requests = []

    def request(self, method, path, payload=None):
        requests.append((method, path, payload))
        if path == "/api/tags":
            return {"models": [{"name": "local:test"}]}
        return {"done": True, "message": {"content": '{"action_id":"tests.host"}'}}

    monkeypatch.setattr(actions.OllamaRecognizer, "request", request)
    model = actions.OllamaRecognizer(catalog, model="local:test")
    assert model.predict("odpal tsty")["action_id"] == "tests.host"
    payload = requests[-1][2]
    assert payload["stream"] is False
    assert payload["format"]["properties"]["action_id"]["enum"] == [
        None,
        *[a.id for a in catalog],
    ]
    assert "#!/usr/bin/env bash" not in json.dumps(payload)
    assert "UV_OFFLINE" not in json.dumps(payload)
    assert "run.sh" not in json.dumps(payload)
    assert "tools" not in payload


@pytest.mark.parametrize(
    "model", ["gpt:cloud", "gpt:120b-cloud", "https://example.com/model", ""]
)
def test_cloud_and_remote_model_names_are_rejected_before_connecting(catalog, model):
    with pytest.raises(ValueError, match="local Ollama model"):
        actions.OllamaRecognizer(catalog, model=model)


@pytest.mark.parametrize(
    "content",
    [
        '{"action_id":"unknown"}',
        '{"action_id":"tests.host","command":"rm"}',
        "not json",
    ],
)
def test_invalid_model_selection_is_not_executable(catalog, monkeypatch, content):
    def request(self, method, path, payload=None):
        if path == "/api/tags":
            return {"models": [{"name": "local:test"}]}
        return {"done": True, "message": {"content": content}}

    monkeypatch.setattr(actions.OllamaRecognizer, "request", request)
    model = actions.OllamaRecognizer(catalog, model="local:test")
    with pytest.raises(ValueError):
        model.predict("run something")


@pytest.mark.integration
def test_confirmed_script_runs_in_project_without_interpolating_request(
    project, monkeypatch, capfd
):
    catalog = actions.load_actions(project)
    answers = iter(["tak"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    phrase = "hello $(touch injected-file)"
    assert actions.ask(project, phrase, catalog, {"action_id": "demo.hello"}) == 0
    assert str(project) in capfd.readouterr().out
    assert not (project / "injected-file").exists()
    hello = next(a for a in actions.load_actions(project) if a.id == "demo.hello")
    assert phrase in hello.examples
    assert not actions.feedback_path(project).exists()


@pytest.mark.integration
def test_host_and_container_entry_points(project):
    import os

    environment = {**os.environ, "ORCAN_ACTIONS_PYTHON": sys.executable}
    for command in (
        [str(ROOT / "bin/orcan"), "actions"],
        [str(ROOT / "docker/rootfs/usr/local/bin/orcan-actions")],
    ):
        result = subprocess.run(
            [*command, "--project", str(project), "suggest", "sprawdz biale znaki"],
            capture_output=True,
            text=True,
            check=True,
            env=environment,
        )
        assert json.loads(result.stdout)["action_id"] == "diff.check"


@pytest.mark.integration
def test_ollama_loopback_http_protocol_without_real_model(catalog):
    """A protocol fixture, not a claim about LLM recognition quality."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            requests.append(self.path)
            body = {"models": [{"name": "local:test"}]}
            self.respond(body)

        def do_POST(self):
            requests.append(self.path)
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert payload["format"]["additionalProperties"] is False
            self.respond(
                {"done": True, "message": {"content": '{"action_id":"demo.hello"}'}}
            )

        def respond(self, payload):
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            model = actions.OllamaRecognizer(
                catalog, model="local:test", port=server.server_port
            )
            assert model.predict("czesc")["action_id"] == "demo.hello"
            assert requests == ["/api/tags", "/api/chat"]
        finally:
            server.shutdown()
            thread.join()


@pytest.mark.integration
def test_correction_is_recorded_only_after_final_confirmation(project, monkeypatch):
    catalog = actions.load_actions(project)
    index = next(i for i, a in enumerate(catalog, 1) if a.id == "demo.hello")
    answers = iter([str(index), "y"])
    monkeypatch.setattr("builtins.input", lambda _: next(answers))
    assert actions.ask(project, "say hi", catalog, {"action_id": "tests.host"}) == 0
    updated = actions.load_actions(project)
    assert "say hi" in next(a for a in updated if a.id == "demo.hello").examples
    assert "say hi" not in next(a for a in updated if a.id == "tests.host").examples
    assert not actions.feedback_path(project).exists()


def test_learning_deduplicates_case_and_whitespace(project):
    selected = next(a for a in actions.load_actions(project) if a.id == "demo.hello")
    definition = selected.script.parent / "action.json"
    original = definition.read_bytes()
    actions.remember(project, "  SAY   HELLO ", selected)
    assert definition.read_bytes() == original
    learned = actions.remember(project, "witaj orcanie", selected)
    after = definition.read_bytes()
    actions.remember(project, "WITAJ ORCANIE", learned)
    assert definition.read_bytes() == after


def test_learning_refuses_stale_and_conflicting_edits(project):
    catalog = actions.load_actions(project)
    hello = next(a for a in catalog if a.id == "demo.hello")
    definition = hello.script.parent / "action.json"
    original = definition.read_bytes()
    with pytest.raises(ValueError, match="already belongs"):
        actions.remember(project, "zrób testy", hello)
    assert definition.read_bytes() == original
    definition.write_bytes(original + b"\n")
    with pytest.raises(ValueError, match="changed"):
        actions.remember(project, "witaj orcanie", hello)
    assert definition.read_bytes() == original + b"\n"


def test_failed_atomic_write_keeps_definition(project, monkeypatch):
    hello = next(a for a in actions.load_actions(project) if a.id == "demo.hello")
    definition = hello.script.parent / "action.json"
    original = definition.read_bytes()

    def fail(*args):
        raise OSError("Simulated write failure")

    monkeypatch.setattr(actions.os, "replace", fail)
    with pytest.raises(OSError):
        actions.remember(project, "witaj orcanie", hello)
    assert definition.read_bytes() == original
    assert sorted(p.name for p in definition.parent.iterdir()) == [
        "action.json",
        "run.sh",
    ]


def test_legacy_journal_remains_readable_but_json_wins(project):
    catalog = actions.load_actions(project)
    hello = next(a for a in catalog if a.id == "demo.hello")
    path = actions.feedback_path(project)
    path.write_text(
        json.dumps(
            {
                "text": "stare powitanie",
                "selected_id": hello.id,
                "fingerprint": hello.fingerprint,
            }
        )
        + "\n"
    )
    original = path.read_bytes()
    assert actions.load_feedback(project, catalog) == [
        ("stare powitanie", "demo.hello")
    ]
    actions.remember(project, "stare powitanie", hello)
    assert actions.load_feedback(project, actions.load_actions(project)) == []
    assert path.read_bytes() == original
