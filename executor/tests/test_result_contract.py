"""Evidence requirements and output isolation at the real command/result boundary."""

import json
import sys
from pathlib import Path

import pytest
from conftest import commit

from orcan_executor import engine, notifications, profiles, store


def procedure(repo, scripts, **policy):
    definition = {"steps": [], **policy}
    for index, script in enumerate(scripts, 1):
        name = f"step{index}.py"
        (repo / name).write_text(script)
        definition["steps"].append({"argv": [sys.executable, name]})
    (repo / profiles.CONFIG).write_text(
        json.dumps({"version": 1, "profiles": {"check": definition}})
    )
    (repo / ".gitignore").write_text("*.xml\n")
    commit(repo)
    job = engine.submit(repo, "HEAD", "evidence", "check", [], 10)
    result = engine.run_job(job["id"])
    return result, Path(result["report"]).parent


@pytest.mark.parametrize("xml", [None, "<testsuite/>"])
def test_exit_zero_without_required_test_evidence_is_error(repo, xml):
    script = "print('PASSED_NOISE')\n"
    if xml:
        script += f"from pathlib import Path\nPath('tests.xml').write_text({xml!r})\n"
    result, root = procedure(repo, [script], require_junit=True, junit=["tests.xml"])
    assert result["status"] == "error"
    assert "PASSED_NOISE" not in notifications.message(store.get(result["job_id"]))
    assert "log_tail" not in result["summary"]
    assert (root / "diagnostics.json").is_file()


def test_each_required_glob_must_match_even_if_another_report_passes(repo):
    result, _ = procedure(
        repo,
        [
            "from pathlib import Path\nPath('unit.xml').write_text('<testsuite><testcase name=\"ok\"/></testsuite>')"
        ],
        require_junit=True,
        junit=["unit.xml", "integration/*.xml"],
    )
    assert result["status"] == "error"
    assert "integration/*.xml" in result["summary"]["error"]


def test_explicit_zero_test_policy_is_supported(repo):
    result, _ = procedure(
        repo,
        ["from pathlib import Path\nPath('empty.xml').write_text('<testsuite/>')"],
        require_junit=True,
        minimum_tests=0,
        junit=["empty.xml"],
    )
    assert result["status"] == "passed"


def test_failed_non_test_step_does_not_send_any_raw_output(repo):
    result, root = procedure(
        repo,
        [
            "print('SUCCESSFUL_STEP_SECRET_NOISE')\n",
            "import sys\nprint('FAILED_STEP_OK_LINE')\nprint('compile failed', file=sys.stderr)\nsys.exit(7)\n",
            "raise AssertionError('must not run')\n",
        ],
    )
    assert result["status"] == "failed"
    summary = result["summary"]
    assert summary["failed_step"] == dict(
        step=2, exit_code=7, outcome="failed", log="steps/step-002.log"
    )
    message = notifications.message(store.get(result["job_id"]))
    assert "SUCCESSFUL_STEP_SECRET_NOISE" not in message
    assert "FAILED_STEP_OK_LINE" not in message
    assert (
        "compile failed" not in message
    )  # Unknown output is not guessed to be structured diagnostics.
    assert "--artifact diagnostics.json" in message
    assert "SUCCESSFUL_STEP_SECRET_NOISE" in (root / "output.log").read_text()
    assert "SUCCESSFUL_STEP_SECRET_NOISE" not in (root / "steps/step-002.log").read_text()
    assert not (root / "steps/step-003.log").exists()
    diagnostic = json.loads((root / "diagnostics.json").read_text())
    assert diagnostic["failed_step"]["exit_code"] == 7
    assert "FAILED_STEP_OK_LINE" not in json.dumps(diagnostic)


def test_structured_failure_has_no_passed_case_content_or_prior_step_noise(repo):
    xml = """<testsuite><testcase name="ok"><system-out>PASSED_CASE_NOISE</system-out></testcase>
    <testcase name="bad"><failure message="expected 4, got 5">FAILURE_TRACE</failure></testcase></testsuite>"""
    result, root = procedure(
        repo,
        [
            "print('SUCCESSFUL_BUILD_NOISE')\n",
            f"from pathlib import Path\nPath('TEST-unit.xml').write_text({xml!r})\nprint('MIXED_OK_LINE')\n",
        ],
        require_junit=True,
        junit=["TEST-*.xml", "TEST-unit.xml"],
    )
    assert result["status"] == "failed"
    assert result["summary"]["tests"] == 2  # Overlapping report globs do not double count cases.
    assert result["summary"]["passed"] == 1
    message = notifications.message(store.get(result["job_id"]))
    assert "expected 4, got 5" in message
    for noise in ("PASSED_CASE_NOISE", "SUCCESSFUL_BUILD_NOISE", "MIXED_OK_LINE", "FAILURE_TRACE"):
        assert noise not in message
    artifact = result["summary"]["problems"][0]["artifact"]
    assert "FAILURE_TRACE" in (root / artifact).read_text()
    diagnostic = (root / "diagnostics.json").read_text()
    assert "expected 4, got 5" in diagnostic and "PASSED_CASE_NOISE" not in diagnostic


def test_real_pytest_failure_is_parsed_and_passed_output_stays_on_disk(repo):
    (repo / "test_sample.py").write_text("""def test_ok():
    print("PYTEST_PASSED_OUTPUT")

def test_bad():
    assert 4 == 5
""")
    definition = {
        "require_junit": True,
        "steps": [
            {
                "argv": [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-q",
                    "test_sample.py",
                    "--junitxml",
                    "{junit}",
                ]
            }
        ],
    }
    (repo / profiles.CONFIG).write_text(
        json.dumps({"version": 1, "profiles": {"check": definition}})
    )
    commit(repo)
    job = engine.submit(repo, "HEAD", "pytest-contract", "check", [], 20)
    result = engine.run_job(job["id"])
    assert result["status"] == "failed"
    assert result["summary"]["tests"] == 2
    assert result["summary"]["passed"] == result["summary"]["failed"] == 1
    assert "assert 4 == 5" in result["summary"]["problems"][0]["message"]
    assert "PYTEST_PASSED_OUTPUT" not in notifications.message(store.get(result["job_id"]))


def test_timeout_points_to_the_interrupted_step_without_raw_log(repo):
    (repo / "check.py").write_text("import time\nprint('NOISE', flush=True)\ntime.sleep(30)")
    commit(repo)
    job = engine.submit(repo, "HEAD", "timeout-contract", "quality", [], 1)
    result = engine.run_job(job["id"])
    assert result["status"] == "timed_out"
    assert result["summary"]["failed_step"]["outcome"] == "timed_out"
    assert "NOISE" not in notifications.message(store.get(result["job_id"]))
    assert (Path(result["report"]).parent / "steps/step-001.log").read_text() == "NOISE\n"


@pytest.mark.parametrize(
    "policy",
    [
        {"require_junit": 1},
        {"require_junit": True},
        {"minimum_tests": 1},
        {"require_junit": True, "junit": ["*.xml"], "minimum_tests": -1},
        {"require_junit": True, "junit": ["*.xml"], "minimum_tests": True},
    ],
)
def test_invalid_report_policy_is_rejected(policy):
    definition = {"steps": [{"argv": ["true"]}], **policy}
    with pytest.raises(ValueError):
        profiles.load(json.dumps({"version": 1, "profiles": {"check": definition}}))


def test_unchanged_report_in_snapshot_does_not_count_as_evidence(repo):
    (repo / "tracked.xml").write_text('<testsuite><testcase name="old"/></testsuite>')
    commit(repo)
    result, _ = procedure(
        repo, ["print('no tests actually ran')"], require_junit=True, junit=["tracked.xml"]
    )
    assert result["status"] == "error"
    assert result["summary"]["tests"] == 0


def test_malformed_required_report_is_error_without_raw_output(repo):
    result, root = procedure(
        repo,
        [
            "from pathlib import Path\nPath('broken.xml').write_text('<testsuite>')\nprint('PASSED_NOISE')"
        ],
        require_junit=True,
        junit=["broken.xml"],
    )
    assert result["status"] == "error"
    assert "ParseError" in result["summary"]["error"]
    assert "PASSED_NOISE" not in notifications.message(store.get(result["job_id"]))
    assert (root / "junit/TEST-0.xml").is_file()


def test_non_junit_xml_cannot_satisfy_report_contract(repo):
    result, _ = procedure(
        repo,
        ["from pathlib import Path\nPath('wrong.xml').write_text('<document/>')"],
        require_junit=True,
        minimum_tests=0,
        junit=["wrong.xml"],
    )
    assert result["status"] == "error"
    assert "not JUnit XML" in result["summary"]["error"]
