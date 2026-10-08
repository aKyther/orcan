"""Private resumable receiver, sent over the selected transport; no network fetch."""

import fcntl
import hashlib
import os
import re
import subprocess
import sys
import time
from pathlib import Path


def cleanup(root):
    """Remove only recognized, idle partial transfers older than one day."""
    for directory in root.iterdir():
        if (
            not re.fullmatch(r"[a-f0-9-]{36}", directory.name)
            or directory.is_symlink()
            or not directory.is_dir()
        ):
            continue
        try:
            entries = list(directory.iterdir())
            if {item.name for item in entries} != {"payload", ".lease"} or any(
                item.is_symlink() or not item.is_file() for item in entries
            ):
                continue
            if time.time() - max(item.stat().st_mtime for item in entries) < 86400:
                continue
            with os.fdopen(
                os.open(directory / ".lease", os.O_RDWR | os.O_NOFOLLOW), "r+b"
            ) as lease:
                fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
                if time.time() - max(item.stat().st_mtime for item in entries) < 86400:
                    continue
                for item in entries:
                    item.unlink()
                directory.rmdir()
        except OSError:
            continue


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            value.update(block)
    return value.hexdigest()


def main():
    mode, token, *args = sys.argv[1:]
    if not re.fullmatch(r"[a-f0-9-]{36}", token):
        raise ValueError("Invalid transfer token")
    root = Path.home() / ".cache" / "orcan-studio-transfers"
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.is_symlink() or root.stat().st_mode & 0o077:
        raise ValueError("Transfer directory must be private (700) and not a symlink")
    cleanup(root)
    directory = root / token
    directory.mkdir(mode=0o700, exist_ok=True)
    if directory.is_symlink() or directory.stat().st_mode & 0o077:
        raise ValueError("Unsafe transfer directory")
    with os.fdopen(
        os.open(directory / ".lease", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600),
        "r+b",
    ) as lease:
        fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        path = directory / "payload"
        with os.fdopen(
            os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600), "r+b"
        ) as payload:
            if mode == "inspect":
                print(f"{path.stat().st_size}\t{digest(path)}")
            elif mode == "append":
                offset, total, expected = args
                if path.stat().st_size != int(offset):
                    raise ValueError(
                        "Destination offset changed; retry to inspect it again"
                    )
                payload.seek(int(offset))
                remaining = int(total) - int(offset)
                while block := sys.stdin.buffer.read(min(1024 * 1024, remaining + 1)):
                    if len(block) > remaining:
                        raise ValueError("Transfer exceeds expected size")
                    payload.write(block)
                    payload.flush()
                    remaining -= len(block)
                os.fsync(payload.fileno())
                if remaining or digest(path) != expected:
                    raise ValueError(
                        "Incomplete transfer or checksum mismatch; installation was not started"
                    )
            elif mode == "install":
                total, expected, command = args
                if path.stat().st_size != int(total) or digest(path) != expected:
                    raise ValueError(
                        "Payload verification failed; installation was not started"
                    )
                payload.seek(0)
                subprocess.run(
                    ["bash", "-lc", 'export PATH="$HOME/.local/bin:$PATH"; ' + command],
                    stdin=payload,
                    check=True,
                )
            elif mode != "remove":
                raise ValueError("Unknown receiver operation")
        if mode == "remove":
            path.unlink()
            (directory / ".lease").unlink()
            directory.rmdir()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Transfer receiver: {error}", file=sys.stderr)
        raise SystemExit(1)
