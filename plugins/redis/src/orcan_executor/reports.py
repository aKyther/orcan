"""Deterministic summaries: successful test output never enters an event payload."""

import xml.etree.ElementTree as ET
from pathlib import Path

from .settings import integer


def junit(directory: Path) -> dict:
    counts = dict(tests=0, failed=0, errors=0, skipped=0)
    failures = []
    for path in sorted(directory.glob("*.xml")):
        # Keep full traces in XML; stream cases instead of retaining the whole tree.
        root_seen = False
        for event, case in ET.iterparse(path, events=("start", "end")):
            tag = case.tag.rsplit("}", 1)[-1]
            if not root_seen:
                if tag not in {"testsuite", "testsuites"}:
                    raise ValueError("Report is not JUnit XML: " + path.name)
                root_seen = True
            if event != "end" or tag != "testcase":
                continue
            counts["tests"] += 1
            failure = case.find("{*}failure")
            error = case.find("{*}error")
            if failure is not None or error is not None:
                node = failure if failure is not None else error
                key = "failed" if failure is not None else "errors"
                counts[key] += 1
                failures.append(
                    {
                        "test": case.get("classname", "") + "." + case.get("name", ""),
                        "message": node.get("message")
                        or next(
                            (
                                line.strip()
                                for line in (node.text or "").splitlines()
                                if line.strip()
                            ),
                            "Failure without a message; inspect the JUnit artifact",
                        ),
                        "artifact": "junit/" + path.name,
                    }
                )
            elif case.find("{*}skipped") is not None:
                counts["skipped"] += 1
            case.clear()
    counts["passed"] = counts["tests"] - counts["failed"] - counts["errors"] - counts["skipped"]
    return {**counts, "failures": failures}


def compact(report: dict, log: Path) -> dict:
    maximum = integer("max-problems", 3, 10)
    message_chars = integer("max-message-chars", 400, 1000)
    summary = {key: report[key] for key in ("tests", "passed", "failed", "errors", "skipped")}
    if report["status"] != "passed":
        summary["problems"] = [
            {
                "test": item["test"][:200],
                "message": item["message"][:message_chars],
                **({"artifact": item["artifact"]} if item.get("artifact") else {}),
            }
            for item in report["failures"][:maximum]
        ]
        summary["omitted_failures"] = max(0, len(report["failures"]) - maximum)
        if report.get("error"):
            summary["error"] = report["error"][:500]
        summary["diagnostic_artifact"] = "diagnostics.json"
        step = next(
            (
                step
                for step in reversed(report.get("commands", []))
                if step.get("outcome", "failed" if step.get("exit_code") else "passed") != "passed"
            ),
            None,
        )
        if step:
            summary["failed_step"] = {
                key: step[key] for key in ("step", "exit_code", "outcome", "log")
            }
        if not report["failures"] and not report.get("error"):
            summary["diagnostic_note"] = (
                "No structured test failures; inspect the failed step artifact if needed."
            )
    return summary
