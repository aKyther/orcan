"""Opt-in, content-addressed verification receipts; never infer a dependency graph."""

import fcntl
import fnmatch
import hashlib
import importlib
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import types
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path, PurePosixPath

from .settings import state_dir

VERSION = 1
MAX_FILES = 2048
MAX_BYTES = 64 * 1024 * 1024
ENVIRONMENT = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "TZ",
    "JAVA_HOME",
    "PYTHONPATH",
    "PYTHONHASHSEED",
    "CI",
    "ORCAN_EXECUTOR_CACHE_EPOCH",
)
SECRET_NAME = re.compile(r"TOKEN|SECRET|PASSWORD|CREDENTIAL|PRIVATE_KEY|API_KEY|ACCESS_KEY", re.I)


def validate(policy):
    if not isinstance(policy, dict) or set(policy) - {
        "ttl_seconds",
        "inputs",
        "tools",
        "environment",
    }:
        raise ValueError("reuse requires ttl_seconds, tools and optional inputs/environment")
    if type(policy.get("ttl_seconds")) is not int or not 1 <= policy["ttl_seconds"] <= 86400:
        raise ValueError("reuse ttl_seconds must be between 1 and 86400")
    tools = policy.get("tools")
    if not isinstance(tools, list) or not 1 <= len(tools) <= 8:
        raise ValueError("reuse tools must declare 1..8 bounded version commands")
    for argv in tools:
        if (
            not isinstance(argv, list)
            or not 2 <= len(argv) <= 8
            or any(not isinstance(a, str) or not a or len(a) > 300 for a in argv)
            or ("/" in argv[0] and not Path(argv[0]).is_absolute())
            or not any(a in {"--version", "-version", "-V"} for a in argv[1:])
            or any(a not in {"--version", "-version", "-V", "--no-daemon"} for a in argv[1:])
        ):
            raise ValueError("reuse tools need a system executable and an explicit version flag")
    if "inputs" in policy:
        inputs = policy["inputs"]
        if (
            not isinstance(inputs, list)
            or not 1 <= len(inputs) <= 64
            or any(
                not isinstance(p, str)
                or not p
                or len(p) > 300
                or PurePosixPath(p).is_absolute()
                or ".." in PurePosixPath(p).parts
                for p in inputs
            )
        ):
            raise ValueError("reuse inputs must be bounded project-relative patterns")
    environment = policy.get("environment", [])
    if (
        not isinstance(environment, list)
        or len(environment) > 32
        or any(
            not isinstance(n, str)
            or not re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", n)
            or SECRET_NAME.search(n)
            for n in environment
        )
    ):
        raise ValueError("reuse environment must name bounded non-secret variables")


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def file_digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def matches(path: str, pattern: str) -> bool:
    """Segment globs: ** matches zero or more directories, * never crosses /."""
    parts, patterns = tuple(path.split("/")), pattern_parts(pattern)
    if all(not any(c in p for c in "*?[") for p in patterns):
        return parts == patterns
    if patterns[-1] == "**" and all(not any(c in p for c in "*?[") for p in patterns[:-1]):
        return parts[: len(patterns) - 1] == patterns[:-1]

    @lru_cache(None)
    def visit(i, j):
        if j == len(patterns):
            return i == len(parts)
        if patterns[j] == "**":
            return visit(i, j + 1) or (i < len(parts) and visit(i + 1, j))
        return i < len(parts) and fnmatch.fnmatchcase(parts[i], patterns[j]) and visit(i + 1, j + 1)

    return visit(0, 0)


@lru_cache(256)
def pattern_parts(pattern: str):
    return PurePosixPath(pattern).parts


def environment_key(policy=None) -> str:
    runner = {p.name: file_digest(p) for p in sorted(Path(__file__).parent.glob("*.py"))}
    value = {
        "version": VERSION,
        "runner": runner,
        "loaded_runner": loaded_runner_key(),
        "runtime_generation": runtime_generation(),
        "image": {
            str(p): file_digest(p)
            for p in (
                Path("/etc/orcan/version"),
                Path("/etc/orcan/build-profile.json"),
                Path("/opt/java/release"),
            )
            if p.is_file()
        },
        "python": sys.version,
        "platform": [sys.platform, platform.machine()],
        "environment": {
            name: os.environ.get(name)
            for name in sorted(set(ENVIRONMENT) | set((policy or {}).get("environment", [])))
        },
        "tools": [],
    }
    for argv in (policy or {}).get("tools", []):
        executable = shutil.which(argv[0])
        if executable is None:
            raise ValueError("reuse tool unavailable")
        executable = Path(executable).resolve()
        # Probe outside the producer's potentially dirty repository. Only hashes
        # of version output/environment are stored, never raw output or values.
        result = subprocess.run(
            [str(executable), *argv[1:]],
            cwd=state_dir(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=5,
            check=False,
        )
        if result.returncode or len(result.stdout) > 65536:
            raise ValueError("reuse version probe unavailable")
        value["tools"].append(
            [
                argv,
                str(executable),
                file_digest(executable),
                hashlib.sha256(result.stdout).hexdigest(),
            ]
        )
    return digest(value)


def runtime_generation():
    namespace = Path("/proc/self/ns/mnt")
    boot = Path("/proc/sys/kernel/random/boot_id")
    # A new container can change libraries without changing version strings.
    return [
        namespace.stat().st_ino if namespace.exists() else None,
        file_digest(boot) if boot.is_file() else None,
    ]


@lru_cache(1)
def loaded_runner_key() -> str:
    # A producer and an old worker can coexist during a rolling update. Hash
    # loaded validation code as well as files, so they cannot certify one another.
    result = {}
    for name in ("engine", "profiles", "reports", "reuse"):
        module = importlib.import_module("orcan_executor." + name)
        result[name] = {
            key: digest(code_data(value.__code__))
            for key, value in vars(module).items()
            if isinstance(value, types.FunctionType) and value.__module__ == module.__name__
        }
    return digest(result)


def code_data(code: types.CodeType):
    def constant(value):
        if isinstance(value, types.CodeType):
            return code_data(value)
        if isinstance(value, bytes):
            return {"bytes": value.hex()}
        if isinstance(value, tuple):
            return {"tuple": [constant(item) for item in value]}
        if isinstance(value, frozenset):
            return {
                "frozenset": sorted(
                    (constant(item) for item in value), key=lambda v: json.dumps(v, sort_keys=True)
                )
            }
        if isinstance(value, complex):
            return {"complex": [value.real, value.imag]}
        if value is Ellipsis:
            return {"ellipsis": True}
        return value

    # marshal's object-reference encoding can depend on prior serialization.
    # Compare executable code/values, using canonical ordering for set constants.
    return {
        "code": code.co_code.hex(),
        "constants": [constant(v) for v in code.co_consts],
        "names": code.co_names,
        "variables": code.co_varnames,
        "free": code.co_freevars,
        "cells": code.co_cellvars,
        "flags": code.co_flags,
        "arguments": [code.co_argcount, code.co_posonlyargcount, code.co_kwonlyargcount],
        "exceptions": code.co_exceptiontable.hex(),
    }


def identity(repo: Path, job: dict, definition: dict) -> dict:
    policy = definition.get("reuse")
    try:
        state_dir().mkdir(parents=True, exist_ok=True, mode=0o700)
        environment = environment_key(policy)
        common = {
            "repo": job["git_dir"],
            "profile": job["profile"],
            "definition": definition,
            "selectors": job["selectors"],
            "timeout": job["timeout"],
            "lane": job["lane"],
            "environment": environment,
        }
        result = {
            "execution_key": digest(common | {"sha": job["sha"]}),
            "environment_key": environment,
        }
        if not policy:
            return result
        entries = subprocess.check_output(
            ["git", "-C", str(repo), "ls-tree", "-rz", "--full-tree", job["sha"]],
            stderr=subprocess.DEVNULL,
        ).split(b"\0")
        patterns = policy.get("inputs")
        selected, matched = [], set()
        for entry in entries:
            if not entry:
                continue
            metadata, path_bytes = entry.split(b"\t", 1)
            path = path_bytes.decode("utf-8")
            hits = [p for p in patterns or [] if matches(path, p)]
            if patterns is not None and not hits:
                continue
            mode, kind, oid = metadata.decode().split()
            if mode not in {"100644", "100755"} or kind != "blob":
                raise ValueError("reuse inputs include a symlink or submodule")
            matched.update(hits)
            selected.append([path, mode, oid])
        if not selected or (patterns is not None and set(patterns) != matched):
            raise ValueError("reuse input pattern has no committed files")
        result["input_key"] = digest(selected)
        result["verification_key"] = digest(common | {"inputs": result["input_key"]})
        return result
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError):
        # An incomplete identity is a cache miss, never permission to skip work.
        return {"reuse_note": "Reuse identity unavailable; fresh verification required"}


def seal(job: dict, definition: dict, report: Path) -> str | None:
    if not job.get("verification_key") or not job.get("reuse_environment_valid"):
        return None
    try:
        if environment_key(definition["reuse"]) != job["environment_key"]:
            return None
        root = report.parent
        paths = [
            report,
            *sorted((root / "junit").glob("*.xml")),
            *sorted((root / "artifacts").rglob("*")),
        ]
        manifest, total = [], 0
        for path in paths:
            if path.is_dir():
                continue
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or not path.resolve().is_relative_to(root.resolve()):
                return None
            total += info.st_size
            if total > MAX_BYTES or len(manifest) >= MAX_FILES:
                return None
            manifest.append([path.relative_to(root).as_posix(), info.st_size, file_digest(path)])
        return json.dumps(manifest)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def environment_valid(job: dict, definition: dict) -> bool:
    try:
        return (
            bool(job.get("verification_key"))
            and environment_key(definition["reuse"]) == job["environment_key"]
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def receipt(source: dict, job: dict) -> tuple[dict, Path] | None:
    """Called under SQLite admission; acquire source lock nonblocking to avoid
    reversing the retention lock order. Copy evidence so source expiry is safe.
    """
    target = state_dir() / "jobs" / job["id"] / "reuse"
    try:
        source_dir = state_dir() / "jobs" / source["id"]
        with (source_dir / "run.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return None
            original = Path(source["report"])
            root = original.parent
            if not root.resolve().is_relative_to(source_dir.resolve()):
                return None
            manifest = json.loads(source["evidence_manifest"])
            if not isinstance(manifest, list) or not 1 <= len(manifest) <= MAX_FILES:
                return None
            target.mkdir(parents=True)
            total = 0
            for name, size, expected in manifest:
                relative = PurePosixPath(name)
                if (
                    relative.is_absolute()
                    or ".." in relative.parts
                    or type(size) is not int
                    or size < 0
                ):
                    raise ValueError("Invalid cached evidence")
                path = root / name
                if not path.resolve().is_relative_to(root.resolve()) or not stat.S_ISREG(
                    path.lstat().st_mode
                ):
                    raise ValueError("Invalid cached evidence")
                total += size
                if (
                    total > MAX_BYTES
                    or path.stat().st_size != size
                    or file_digest(path) != expected
                ):
                    raise ValueError("Changed cached evidence")
                copy = target / "evidence" / name
                copy.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, copy)
                if file_digest(copy) != expected:
                    raise ValueError("Evidence changed while copying")
            if not any(item[0] == original.name for item in manifest):
                raise ValueError("Cached report missing")
            proof = json.loads((target / "evidence" / original.name).read_text())
            if proof.get("status") != "passed" or proof.get("sha") != source["sha"]:
                raise ValueError("Invalid cached verdict")
            previous = json.loads(source["summary"])
            counters = ("tests", "passed", "failed", "errors", "skipped")
            if any(proof.get(k, 0) != previous.get(k, 0) for k in counters):
                raise ValueError("Cached counters disagree with evidence")
            if not proof.get("commands") or any(c.get("exit_code") != 0 for c in proof["commands"]):
                raise ValueError("Cached commands are incomplete")
            origin = proof.get("verification") or {}
            if (
                origin.get("inputs_sha256") != job["input_key"]
                or origin.get("environment_sha256") != job["environment_key"]
            ):
                raise ValueError("Cached identity disagrees with evidence")
            junit = target / "evidence" / "junit"
            if origin.get("junit_required") and not any(junit.glob("*.xml")):
                raise ValueError("Cached JUnit evidence missing")
            from .reports import junit as read_junit

            counts = read_junit(junit)
            if any(counts[k] != previous.get(k, 0) for k in counters):
                raise ValueError("Cached JUnit counters disagree")
            verification = {
                "kind": "reused",
                "source_job_id": source["id"],
                "source_sha": source["sha"],
                "verified_at": source["finished"],
                "inputs_sha256": job["input_key"],
                "environment_sha256": job["environment_key"],
                "counts": {
                    k: previous.get(k, 0)
                    for k in ("tests", "passed", "failed", "errors", "skipped")
                },
                "evidence": "evidence/report.json",
            }
            summary = {
                "tests": 0,
                "passed": 0,
                "failed": 0,
                "errors": 0,
                "skipped": 0,
                "verification": verification,
            }
            report = target / "report.json"
            report.write_text(
                json.dumps(
                    {
                        "job_id": job["id"],
                        "sha": job["sha"],
                        "profile": job["profile"],
                        "status": "passed",
                        **summary,
                    },
                    indent=2,
                )
                + "\n"
            )
            return summary, report
    except (OSError, ValueError, TypeError, KeyError, AttributeError, ET.ParseError):
        if target.exists():
            shutil.rmtree(target)
        return None
