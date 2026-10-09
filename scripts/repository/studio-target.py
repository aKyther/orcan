"""Explicit target registration and retirement; probes never allocate IDs."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import platform
import re
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4


def fingerprint() -> str:
    for path in (Path("/etc/machine-id"), Path("/var/lib/dbus/machine-id")):
        if path.is_file():
            return hashlib.sha256(path.read_bytes().strip()).hexdigest()
    return hashlib.sha256(platform.node().encode()).hexdigest()


def canonical(value: object) -> str:
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError("Invalid target UUID")
    return value


def read(path: Path) -> dict:
    if path.is_symlink():
        raise ValueError("Target records must not be symlinks")
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("Invalid target record")  # noqa: TRY004
    return value


def write(path: Path, value: dict) -> None:
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError("Target storage must not use symlinks")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as stream:
        pending = Path(stream.name)
        json.dump(value, stream, indent=2)
        stream.write("\n")
    try:
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def snapshot(host_root: Path, config: Path) -> dict:
    try:
        record = host_root / "studio-host.json"
        if not record.exists():
            return {
                "state": "unregistered",
                "reason": "Register this container before adding it to an enclave.",
            }
        host = read(record)
        host_id = canonical(host.get("id"))
        if host.get("fingerprint") != fingerprint():
            return {
                "state": "mismatch",
                "reason": "Host fingerprint changed. A cloned VM needs explicit target rekeying.",
            }
        if not config.exists():
            return {
                "state": "missing",
                "host_id": host_id,
                "reason": "Container configuration is missing.",
            }
        cfg = read(config)
        if not cfg.get("container_id"):
            return {
                "state": "unregistered",
                "host_id": host_id,
                "reason": "Register this existing container.",
            }
        if cfg.get("host_id") != host_id:
            return {
                "state": "mismatch",
                "reason": "Configuration belongs to a different host identity.",
            }
        return {
            "state": "ready",
            "host_id": host_id,
            "container_id": canonical(cfg["container_id"]),
        }
    except (OSError, ValueError) as error:
        return {"state": "invalid", "reason": str(error)}


@contextmanager
def locked(host_root: Path):
    if host_root.is_symlink():
        raise ValueError("Target storage must not use symlinks")
    host_root.mkdir(parents=True, exist_ok=True)
    path = host_root / ".studio-target.lock"
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("Invalid target lock")
    with path.open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def register(host_root: Path, config: Path, new_target: bool = False) -> dict:
    with locked(host_root):
        return _register(host_root, config, new_target)


def _register(host_root: Path, config: Path, new_target: bool = False) -> dict:
    cfg = read(config)
    host_root.mkdir(parents=True, exist_ok=True)
    path = host_root / "studio-host.json"
    if path.exists():
        host = read(path)
        canonical(host.get("id"))
        if host.get("fingerprint") != fingerprint():
            raise ValueError(
                "Host fingerprint changed; use studio target clone --yes on the clone first"
            )
    else:
        host = {"id": str(uuid4()), "fingerprint": fingerprint()}
        # Exclusive creation prevents two initial registrations inventing different hosts.
        try:
            with path.open("x") as stream:
                json.dump(host, stream)
        except FileExistsError:
            host = read(path)
            canonical(host.get("id"))
            if host.get("fingerprint") != fingerprint():
                raise ValueError("Host fingerprint changed")
    if cfg.get("host_id") not in (None, host["id"]) and not new_target:
        raise ValueError("Use register --new-target --yes on a cloned configuration")
    cfg["container_id"] = (
        str(uuid4())
        if new_target
        else canonical(cfg["container_id"])
        if cfg.get("container_id")
        else str(uuid4())
    )
    cfg["host_id"] = host["id"]
    write(config, cfg)
    return snapshot(host_root, config)


def retire(
    host_root: Path, config: Path, container: str, expected: str, apply: bool
) -> dict:
    if apply:
        with locked(host_root):
            return _retire(host_root, config, container, expected, True)
    return _retire(host_root, config, container, expected, False)


def _retire(
    host_root: Path, config: Path, container: str, expected: str, apply: bool
) -> dict:
    target = snapshot(host_root, config)
    if target.get("container_id") != canonical(expected) or target["state"] != "ready":
        raise ValueError("Container identity changed; refresh before replacement")
    home = config.parent
    if (
        home.parent != host_root / "instances"
        or home.is_symlink()
        or not re.fullmatch(r"[a-z][a-z0-9-]{0,47}", home.name)
        or container != f"orcan-{home.name}"
    ):
        raise ValueError("Replacement supports named instances only")
    result = subprocess.run(
        ["docker", "inspect", "--format", "{{.Id}}", container],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        raise ValueError(
            "Remove the container with Down first; replacement never stops sessions automatically"
        )
    # Do not interpret a daemon/permission failure as an absent container.
    subprocess.run(["docker", "info"], capture_output=True, check=True)
    inventory = subprocess.run(
        [
            "docker",
            "ps",
            "--all",
            "--filter",
            f"name=^{container}$",
            "--format",
            "{{.ID}}",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    if inventory.stdout.strip():
        raise ValueError("Container still exists; replacement was not prepared")
    cfg = read(config)
    paths = [
        project.get("path", "")
        for ws in cfg.get("workspaces", [])
        for project in ws.get("projects", [])
    ]
    paths.extend(
        [
            cfg.get("projects_root", ""),
            os.environ.get("ORCAN_DATA", ""),
            os.environ.get("ORCAN_PROJECTS_ROOT", ""),
        ]
    )
    if any(
        Path(path).resolve().is_relative_to(home.resolve()) for path in paths if path
    ):
        raise ValueError(
            "A project lives inside the instance directory; move it explicitly before replacement"
        )
    archive = host_root / "retired" / f"{home.name}-{expected}"
    if archive.exists() or archive.parent.is_symlink():
        raise ValueError("Replacement archive already exists or is unsafe")
    plan = {
        "ready": True,
        "archive": str(archive),
        "changes": [
            "archive instance configuration and workspace metadata",
            "keep shared projects, cache and agent data",
            "create replacement separately with a new UUID and chosen identity",
        ],
    }
    if apply:
        archive.parent.mkdir(parents=True, exist_ok=True)
        home.rename(archive)
    return plan


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode", choices=["register", "clone", "verify", "replace-plan", "replace-apply"]
    )
    parser.add_argument("--host-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--container")
    parser.add_argument("--expected-id")
    parser.add_argument("--expected-host-id")
    parser.add_argument("--new-target", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    try:
        if args.mode not in ("replace-plan", "verify") and not args.yes:
            raise ValueError("Explicit --yes required")
        if args.host_root.is_symlink() or args.config.parent.is_symlink():
            raise ValueError("Symlinked target storage is not supported")
        if args.mode == "verify":
            result = snapshot(args.host_root, args.config)
            if (
                result.get("state") != "ready"
                or result.get("container_id") != args.expected_id
                or result.get("host_id") != args.expected_host_id
            ):
                raise ValueError("Target UUID mismatch; no session was attached")
        elif args.mode == "clone":
            with locked(args.host_root):
                write(
                    args.host_root / "studio-host.json",
                    {"id": str(uuid4()), "fingerprint": fingerprint()},
                )
            result = {
                "state": "rekeyed",
                "detail": "Register each cloned container with --new-target. Existing enclaves keep their original IDs.",
            }
        elif args.mode == "register":
            result = register(args.host_root, args.config, args.new_target)
        else:
            if not args.container or not args.expected_id:
                raise ValueError("Replacement requires container and expected UUID")
            result = retire(
                args.host_root,
                args.config,
                args.container,
                args.expected_id,
                args.mode == "replace-apply",
            )
        print(json.dumps({"ok": True, "result": result}))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
