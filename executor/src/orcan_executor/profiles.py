"""Orcan-managed procedures, frozen at submission, never interpreted through a shell."""

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

CONFIG = ".orcan/checks.json"


def external_path(repo: Path) -> Path:
    """One Orcan-owned procedure registry per Git common directory/project."""
    from .settings import state_dir

    repo = repo.resolve()
    if not repo.is_dir():
        raise ValueError("Project directory does not exist")
    try:
        identity = subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except subprocess.CalledProcessError:
        identity = str(repo)
    key = hashlib.sha256(os.fsencode(identity)).hexdigest()
    path = state_dir() / "project-profiles" / key / "checks.json"
    if path.is_relative_to(repo):
        raise ValueError("Executor state must stay outside the source project")
    return path


def external_text(repo: Path) -> str | None:
    path = external_path(repo)
    if not path.exists():
        return None
    with path.open("rb") as stream:
        content = stream.read(1024 * 1024 + 1)
    if len(content) > 1024 * 1024:
        raise ValueError("Orcan project profiles exceed 1 MiB")
    text = content.decode("utf-8")
    load(text)
    return text


def definitions(repo: Path, sha: str) -> dict:
    text = external_text(repo)
    if text is None:
        try:
            text = subprocess.check_output(
                ["git", "-C", str(repo), "show", sha + ":" + CONFIG],
                text=True,
                stderr=subprocess.DEVNULL,
            )
        except subprocess.CalledProcessError:
            raise ValueError(
                "No project profiles; run orcan-executor init --repo PATH --kind KIND"
            ) from None
    return load(text)


def for_job(job: dict, root: Path | None = None) -> dict:
    """Use the submitted procedure, never a later edit of a mutable registry."""
    definition = job.get("profile_definition")
    if definition is not None:
        return definition
    # Compatibility for jobs pinned before procedure snapshots were persisted.
    if root is not None:
        text = (root / CONFIG).read_text()
    else:
        repo = Path(job["repo"]) if Path(job["repo"]).exists() else Path(job["git_dir"])
        text = subprocess.check_output(
            ["git", "-C", str(repo), "show", job["sha"] + ":" + CONFIG],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    return load(text)[job["profile"]]


def procedure_digest(definition: dict) -> str:
    return hashlib.sha256(
        json.dumps(definition, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def load(text: str) -> dict:
    value = json.loads(text)
    profiles = value.get("profiles")
    if value.get("version") != 1 or not isinstance(profiles, dict) or not 1 <= len(profiles) <= 32:
        raise ValueError("Expected version 1 and 1..32 project profiles")
    for name, profile in profiles.items():
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", name) or not isinstance(profile, dict):
            raise ValueError("Invalid profile")
        if not isinstance(profile.get("requires_tests", False), bool):
            raise ValueError("requires_tests must be a boolean")
        if profile.get("lane", "default") not in {"default", "light", "heavy"}:
            raise ValueError("Profile lane must be default, light or heavy")
        if "timeout_seconds" in profile and (
            type(profile["timeout_seconds"]) is not int
            or not 1 <= profile["timeout_seconds"] <= 21600
        ):
            raise ValueError("Profile timeout_seconds must be an integer from 1 to 21600")
        if type(profile.get("require_junit", False)) is not bool:
            raise ValueError("require_junit must be a boolean")
        if "reuse" in profile:
            from .reuse import validate

            validate(profile["reuse"])
        if "minimum_tests" in profile and (
            not profile.get("require_junit")
            or type(profile["minimum_tests"]) is not int
            or not 0 <= profile["minimum_tests"] <= 1000000000
        ):
            raise ValueError("minimum_tests requires require_junit and a non-negative integer")
        steps = profile.get("steps")
        if not isinstance(steps, list) or not 1 <= len(steps) <= 20:
            raise ValueError("A profile requires 1..20 steps")
        for step in steps:
            argv = step.get("argv")
            if (
                not isinstance(argv, list)
                or not 1 <= len(argv) <= 100
                or any(not isinstance(a, str) or not a or len(a) > 2000 for a in argv)
            ):
                raise ValueError("Each step requires a bounded argv list")
            relative(step.get("cwd", "."))
        if profile.get("requires_tests") and not any(
            a in {"{tests}", "{gradle_tests}", "{sbt_tests}"}
            for step in steps
            for a in step["argv"]
        ):
            raise ValueError("A selected profile must use its explicit test selectors")
        if profile.get("require_junit") and not (
            profile.get("junit") or any("{junit}" in step["argv"] for step in steps)
        ):
            raise ValueError("require_junit needs junit globs or a {junit} output argument")
        for field in ("junit", "artifacts"):
            patterns = profile.get(field, [])
            if not isinstance(patterns, list) or len(patterns) > 20:
                raise ValueError("Invalid artifact patterns")
            for pattern in patterns:
                relative(pattern)
    return profiles


def relative(value: str) -> Path:
    if not isinstance(value, str) or not value or len(value) > 300:
        raise ValueError("Invalid project-relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Paths must stay within the snapshot")
    return path


def inside(root: Path, value: str) -> Path:
    path = (root / relative(value)).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Path escapes the snapshot")
    return path


def commands(root: Path, job: dict) -> list:
    profile = for_job(job, root)
    tests = job["selectors"]
    steps = []
    for step in profile["steps"]:
        argv = []
        for item in step["argv"]:
            if item == "{tests}":
                argv.extend(tests)
            elif item == "{gradle_tests}":
                for test in tests:
                    argv.extend(["--tests", test])
            elif item == "{sbt_tests}":
                if any(not re.fullmatch(r"[A-Za-z0-9_.*$]+", test) for test in tests):
                    raise ValueError("Unsupported sbt test selector")
                argv.append("testOnly " + " ".join(tests))
            elif item == "{junit}":
                argv.append(str(Path(job["artifact_dir"]) / "junit.xml"))
            else:
                argv.append(item)
        steps.append((argv, inside(root, step.get("cwd", "."))))
    return steps


def template(kind: str, root: Path) -> dict:
    def profile(argv, *, selected=False, cwd=".", junit=None):
        return {
            "requires_tests": selected,
            "steps": [{"argv": argv, "cwd": cwd}],
            "junit": junit or [],
        }

    if kind == "python":
        profiles = {
            "selected": profile(
                ["uv", "run", "--locked", "pytest", "-q", "{tests}", "--junitxml", "{junit}"],
                selected=True,
            ),
            "full": profile(["uv", "run", "--locked", "pytest", "-q", "--junitxml", "{junit}"]),
            "quality": profile(["uv", "run", "--locked", "ruff", "check", "."]),
            "docs": profile(["uv", "run", "--locked", "mkdocs", "build", "--strict"]),
        }
    elif kind == "java":
        cwd = "java" if (root / "java/gradlew").exists() else "."
        junit = [f"{cwd}/build/test-results/test/*.xml"]
        profiles = {
            "selected": profile(
                ["./gradlew", "--console=plain", "--max-workers=1", "test", "{gradle_tests}"],
                selected=True,
                cwd=cwd,
                junit=junit,
            ),
            "full": profile(
                ["./gradlew", "--console=plain", "--max-workers=1", "check"], cwd=cwd, junit=junit
            ),
            "docs": profile(
                ["./gradlew", "--console=plain", "--max-workers=1", "javadoc"], cwd=cwd
            ),
        }
    elif kind == "scala":
        profiles = {
            "selected": profile(
                ["sbt", "-batch", "{sbt_tests}"], selected=True, junit=["target/test-reports/*.xml"]
            ),
            "full": profile(["sbt", "-batch", "test"], junit=["target/test-reports/*.xml"]),
            "docs": profile(["sbt", "-batch", "doc"]),
        }
    else:
        profiles = {"quality": profile(["git", "diff", "--check", "HEAD^", "HEAD"])}
    for name, definition in profiles.items():
        if kind in {"python", "java", "scala"} and name in {"selected", "full"}:
            definition["require_junit"] = True
    return {"version": 1, "profiles": profiles}
