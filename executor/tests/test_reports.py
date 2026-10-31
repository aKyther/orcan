import json

from orcan_executor import reports


def test_junit_leaf_failures_errors_and_skips_are_classified(tmp_path):
    (tmp_path / "TEST-cases.xml").write_text("""<testsuite>
        <testcase classname="A" name="ok"><system-out>not useful</system-out></testcase>
        <testcase classname="A" name="failure"><failure message="wrong"/></testcase>
        <testcase classname="A" name="error"><error message="crash">trace</error></testcase>
        <testcase classname="A" name="skip"><skipped/></testcase>
        </testsuite>""")
    result = reports.junit(tmp_path)
    assert (
        result["tests"],
        result["passed"],
        result["failed"],
        result["errors"],
        result["skipped"],
    ) == (4, 1, 1, 1, 1)
    assert [item["message"] for item in result["failures"]] == ["wrong", "crash"]
    result["status"] = "failed"
    compact = reports.compact(result, tmp_path / "missing.log")
    assert "details" not in json.dumps(compact)
    assert "not useful" not in json.dumps(compact)


def test_success_summary_discards_all_stdout_and_traces(tmp_path):
    result = dict(
        status="passed",
        tests=5000,
        passed=5000,
        failed=0,
        errors=0,
        skipped=0,
        failures=[],
        error="not copied",
    )
    log = tmp_path / "output.log"
    log.write_text("huge stdout" * 100000)
    summary = reports.compact(result, log)
    assert len(json.dumps(summary)) < 100
    assert "log_tail" not in summary


def test_failure_without_message_uses_failure_text_not_passed_output(tmp_path):
    (tmp_path / "TEST.xml").write_text(
        '<testsuite><testcase name="ok"><system-out>OK_NOISE</system-out></testcase><testcase name="bad"><failure>AssertionError: wrong value</failure></testcase></testsuite>'
    )
    result = reports.junit(tmp_path)
    assert result["failures"][0]["message"] == "AssertionError: wrong value"
    assert "OK_NOISE" not in json.dumps(result)


def test_namespaced_junit_keeps_failure_only(tmp_path):
    (tmp_path / "TEST.xml").write_text(
        '<testsuite xmlns="urn:junit"><testcase name="ok"><system-out>OK_NOISE</system-out></testcase><testcase name="bad"><error message="broken"/></testcase></testsuite>'
    )
    result = reports.junit(tmp_path)
    assert result["passed"] == result["errors"] == 1
    assert result["failures"][0]["message"] == "broken"
    assert "OK_NOISE" not in json.dumps(result)
