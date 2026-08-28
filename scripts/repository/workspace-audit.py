#!/usr/bin/env python3
"""Audit workspace symlink / mount health for ``orcan doctor`` and diagnostics."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent


def _load_apply_config():
    import importlib.util

    spec = importlib.util.spec_from_file_location("apply_config", SCRIPTS / "apply-config.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


apply_config = _load_apply_config()


@dataclass(frozen=True)
class Finding:
    level: str  # ok | warn | fail
    label: str
    detail: str = ""


def _resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path


def load_runtime(home: Path) -> dict:
    env = os.environ.get("ORCAN_CONFIG_HOST", "").strip()
    path = Path(env) if env else home / "mounts" / "runtime-config.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def compose_bind_paths(compose_file: Path) -> set[str]:
    if not compose_file.is_file():
        return set()
    paths: set[str] = set()
    for line in compose_file.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s+-\s+([^:#]+):([^:#\s]+)\s*$", line)
        if not m:
            continue
        host, container = m.group(1).strip(), m.group(2).strip()
        if host == container:
            paths.add(host)
    return paths


def path_visible_in_container(container: str, path: str) -> bool:
    if not container:
        return True
    proc = subprocess.run(
        ["docker", "exec", container, "test", "-d", path],
        capture_output=True,
        check=False,
    )
    return proc.returncode == 0


def audit(
    *,
    home: Path,
    managed_root: Path | None,
    compose_file: Path,
    container: str = "",
) -> list[Finding]:
    findings: list[Finding] = []
    runtime = load_runtime(home)
    workspaces = runtime.get("workspaces") or []
    if not workspaces:
        findings.append(Finding("ok", "workspace mapping", "no runtime workspaces (run: orcan sync)"))
        return findings

    binds = compose_bind_paths(compose_file)
    enabled = [ws for ws in workspaces if isinstance(ws, dict) and ws.get("enabled") is not False]

    for ws in enabled:
        ws_name = str(ws.get("name") or "?")
        meta_raw = str(ws.get("meta_path") or "").strip()
        if not meta_raw:
            findings.append(
                Finding("fail", f"workspace {ws_name}", "missing meta_path in runtime config")
            )
            continue
        meta = Path(meta_raw)
        if not meta.is_dir():
            findings.append(
                Finding("fail", f"workspace {ws_name}", f"meta dir missing: {meta}")
            )
            continue

        for bak in sorted(meta.glob("*.orcan-reconcile-bak*")):
            findings.append(
                Finding(
                    "warn",
                    f"workspace {ws_name}",
                    f"stale backup dir {bak.name} — remove after verifying symlinks",
                )
            )

        for proj in ws.get("projects") or []:
            if not isinstance(proj, dict):
                continue
            pname = str(proj.get("name") or "?")
            label = f"{ws_name}/{pname}"
            host_path = str(proj.get("path") or "").strip()
            if not host_path:
                findings.append(Finding("fail", label, "empty projects[].path"))
                continue

            expected = _resolve(Path(host_path))
            if not expected.is_dir():
                findings.append(Finding("fail", label, f"project path missing on host: {host_path}"))
                continue

            slot = meta / pname
            if slot.is_symlink():
                if _resolve(slot) != expected:
                    findings.append(
                        Finding(
                            "fail",
                            label,
                            f"symlink → {slot.resolve()} (expected {expected})",
                        )
                    )
                else:
                    findings.append(Finding("ok", label, f"symlink → {expected}"))
            elif slot.is_dir() and not slot.is_symlink():
                findings.append(
                    Finding(
                        "fail",
                        label,
                        "real directory blocks symlink — run: orcan sync",
                    )
                )
            elif not slot.exists():
                findings.append(
                    Finding(
                        "fail",
                        label,
                        "symlink missing — run: orcan sync",
                    )
                )
            else:
                findings.append(Finding("fail", label, f"unexpected slot type: {slot}"))

            needs_bind = True
            if managed_root is not None and apply_config._is_under(expected, managed_root):
                needs_bind = False
            if needs_bind and binds and str(expected) not in binds:
                findings.append(
                    Finding(
                        "warn",
                        label,
                        "path not in compose-projects.generated.yml — run: orcan down && orcan up",
                    )
                )

            if container and not path_visible_in_container(container, host_path):
                findings.append(
                    Finding(
                        "fail",
                        label,
                        f"not visible in container {container} — run: orcan down && orcan up",
                    )
                )

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", default=os.environ.get("ORCAN_HOME", "").strip())
    parser.add_argument(
        "--compose",
        default="",
        help="compose-projects.generated.yml (default: $ORCAN_HOME/mounts/...)",
    )
    parser.add_argument(
        "--container",
        default="",
        help="Running container name for in-container path checks",
    )
    parser.add_argument(
        "--format",
        choices=("doctor", "text"),
        default="doctor",
        help="doctor: LEVEL\\tLABEL\\tDETAIL lines; text: human-readable",
    )
    args = parser.parse_args()

    if not args.home:
        print("Error: ORCAN_HOME is not set", file=sys.stderr)
        return 1

    home = Path(args.home).resolve()
    compose = (
        Path(args.compose)
        if args.compose
        else Path(
            os.environ.get(
                "ORCAN_COMPOSE_PROJECTS",
                str(home / "mounts" / "compose-projects.generated.yml"),
            )
        )
    )
    managed = apply_config.managed_projects_root(dict(os.environ))

    findings = audit(
        home=home,
        managed_root=managed,
        compose_file=compose,
        container=args.container.strip(),
    )

    fails = 0
    for f in findings:
        if args.format == "doctor":
            detail = f.detail.replace("\t", " ")
            print(f"{f.level}\t{f.label}\t{detail}")
        else:
            prefix = {"ok": "ok", "warn": "WARN", "fail": "FAIL"}[f.level]
            line = f"{prefix}  {f.label}"
            if f.detail:
                line += f" ({f.detail})"
            print(line)
        if f.level == "fail":
            fails += 1

    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
