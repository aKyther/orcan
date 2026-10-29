"""Deterministic summaries: successful test output never enters an event payload."""

import xml.etree.ElementTree as ET
from pathlib import Path

from .settings import integer


def junit(directory: Path) -> dict:
    counts = dict(tests=0, failed=0, errors=0, skipped=0)
    failures = []
    for path in sorted(directory.glob("*.xml")):
        # Keep full traces in XML; stream cases instead of retaining the whole tree.
        for _, case in ET.iterparse(path, events=("end",)):
            if case.tag != "testcase":
                continue
            counts["tests"] += 1
            failure = case.find("failure")
            error = case.find("error")
            if failure is not None or error is not None:
                node = failure if failure is not None else error
                key = "failed" if failure is not None else "errors"
                counts[key] += 1
                failures.append(
                    {
                        "test": case.get("classname", "") + "." + case.get("name", ""),
                        "message": node.get("message", ""),
                        "artifact": "junit/" + path.name,
                    }
                )
            elif case.find("skipped") is not None:
                counts["skipped"] += 1
            case.clear()
    counts["passed"] = counts["tests"] - counts["failed"] - counts["errors"] - counts["skipped"]
    return {**counts, "failures": failures}


def log_tail(log: Path, limit: int = 1400) -> str:
    if not log.exists():
        return ""
    with log.open("rb") as source:
        source.seek(0, 2)
        source.seek(max(0, source.tell() - 8192))
        text = source.read().decode("utf-8", errors="replace")
    if "* What went wrong:" in text:
        text = text.split("* What went wrong:", 1)[1].split("* Try:", 1)[0].strip()
    return text[-limit:]


def compact(report: dict, log: Path) -> dict:
    maximum = integer("max-problems", 3, 10)
    message_chars = integer("max-message-chars", 400, 1000)
    summary = {key: report[key] for key in ("tests", "passed", "failed", "errors", "skipped")}
    if report["status"] != "passed":
        summary["problems"] = [
            {"test": item["test"][:200], "message": item["message"][:message_chars]}
            for item in report["failures"][:maximum]
        ]
        summary["omitted_failures"] = max(0, len(report["failures"]) - maximum)
        if report.get("error"):
            summary["error"] = report["error"][:500]
        if not report["failures"]:
            summary["log_tail"] = log_tail(log)
    return summary
