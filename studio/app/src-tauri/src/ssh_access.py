"""Explicit Git/SSH preparation, sent through the profile transport.

Only export emits private data, to the native process, never to the UI. All
filesystem access is relative to a no-follow directory descriptor. No archives,
source config, known_hosts or multiplexing sockets are transferred.
"""

import base64
import fcntl
import fnmatch
import hashlib
import hmac
import json
import os
import re
import stat
import struct
import subprocess
import sys
from pathlib import Path

LIMIT = 256 * 1024
ALGORITHMS = {
    "ssh-ed25519",
    "ssh-rsa",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
}


def name(value):
    if (
        not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}", value)
        or value
        in {
            "config",
            "known_hosts",
            "known_hosts2",
            "authorized_keys",
            "authorized_keys2",
        }
        or value.endswith((".pub", ".conf", ".pending"))
    ):
        raise ValueError(
            "Use 1–64 letters, digits, dots, underscores or hyphens for the key name"
        )
    return value


def host(value):
    if len(value) > 253 or not re.fullmatch(
        r"[a-zA-Z0-9][a-zA-Z0-9.-]*[a-zA-Z0-9]|[a-zA-Z0-9]", value
    ):
        raise ValueError("Enter a Git hostname, without URL, user or port")
    return value


def directory(create=False):
    path = Path.home() / ".ssh"
    if create:
        path.mkdir(mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    info = os.fstat(fd)
    if info.st_uid != os.getuid() or info.st_mode & 0o022:
        os.close(fd)
        raise ValueError(
            "SSH directory must belong to this user and not be writable by others"
        )
    if create:
        os.fchmod(fd, 0o700)
    return fd


def read(fd, filename, private=False):
    handle = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    try:
        info = os.fstat(handle)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_size > LIMIT
        ):
            raise ValueError(
                "SSH file must be a bounded regular file owned by this user"
            )
        if private and info.st_mode & 0o077:
            raise ValueError("Source private key must have private permissions (600)")
        with os.fdopen(handle, "rb", closefd=False) as stream:
            value = stream.read(LIMIT + 1)
        if len(value) > LIMIT:
            raise ValueError("SSH file is too large")
        return value
    finally:
        os.close(handle)


def public(value):
    fields = value.decode("ascii").split()
    if len(fields) < 2 or fields[0] not in ALGORITHMS:
        raise ValueError(
            "Unsupported public key (hardware-backed keys cannot be copied)"
        )
    blob = base64.b64decode(fields[1], validate=True)
    checked = subprocess.run(
        ["ssh-keygen", "-lf", "/dev/stdin"],
        input=value,
        capture_output=True,
        timeout=5,
        check=False,
    )
    if checked.returncode != 0:
        raise ValueError("Invalid SSH public key")
    fingerprint = "SHA256:" + base64.b64encode(
        hashlib.sha256(blob).digest()
    ).decode().rstrip("=")
    return {"algorithm": fields[0], "fingerprint": fingerprint}, blob


def paired(private, blob):
    # OpenSSH stores its public key outside the encrypted private section. This
    # verifies the pair without asking for or transferring its passphrase.
    lines = private.splitlines()
    if (
        not lines
        or lines[0] != b"-----BEGIN OPENSSH PRIVATE KEY-----"
        or lines[-1] != b"-----END OPENSSH PRIVATE KEY-----"
    ):
        raise ValueError(
            "Only OpenSSH-format private keys are supported; the source key was not changed"
        )
    raw = base64.b64decode(b"".join(lines[1:-1]), validate=True)
    prefix = b"openssh-key-v1\x00"
    if not raw.startswith(prefix):
        raise ValueError("Invalid OpenSSH key")
    offset = len(prefix)

    def string():
        nonlocal offset
        size = struct.unpack_from(">I", raw, offset)[0]
        offset += 4
        value = raw[offset : offset + size]
        if len(value) != size:
            raise ValueError("Invalid OpenSSH key")
        offset += size
        return value

    cipher = string()
    string()  # KDF name
    string()  # KDF options
    count = struct.unpack_from(">I", raw, offset)[0]
    offset += 4
    if count != 1 or string() != blob:
        raise ValueError("Private/public key pair changed or does not match")
    return cipher != b"none"


def write_new(fd, filename, data):
    handle = os.open(
        filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd
    )
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        os.unlink(filename, dir_fd=fd)
        raise


def inventory(fd):
    keys = []
    for filename in sorted(os.listdir(fd)):
        if not filename.endswith(".pub"):
            continue
        try:
            key = name(filename[:-4])
            info = os.stat(key, dir_fd=fd, follow_symlinks=False)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_mode & 0o077
            ):
                continue
            metadata, _ = public(read(fd, filename))
            keys.append({"name": key, **metadata})
        except (OSError, ValueError, UnicodeError):
            continue
    return keys


def git_config(key, hostname, user):
    host(hostname)
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", user):
        raise ValueError("Invalid Git SSH user")
    return f"Host {hostname}\n  HostName {hostname}\n  User {user}\n  IdentityFile ~/.ssh/{key}\n  IdentitiesOnly yes\n  StrictHostKeyChecking yes\nHost *\n".encode()


def scan(hostname):
    host(hostname)
    scanned = subprocess.run(
        ["ssh-keyscan", "-T", "5", "-t", "ed25519", hostname],
        capture_output=True,
        timeout=10,
        check=False,
    )
    identities = set()
    for line in scanned.stdout.splitlines():
        if line.startswith(b"#"):
            continue
        fields = line.split()
        if len(fields) == 3 and fields[1] == b"ssh-ed25519":
            identities.add(fields[1] + b" " + fields[2])
    if len(identities) != 1:
        raise ValueError("Git host did not report one consistent Ed25519 identity")
    pub = identities.pop()
    metadata, _ = public(pub)
    return {"host": hostname, **metadata, "key": pub.decode()}


def known(fd, hostname):
    try:
        content = read(fd, "known_hosts")
    except FileNotFoundError:
        return set()
    matches = set()
    for line in content.splitlines():
        fields = line.split()
        marker = b""
        if fields and fields[0].startswith(b"@"):
            marker = fields[0] + b" "
            fields = fields[1:]
        if len(fields) < 3:
            continue
        names = fields[0].decode(errors="replace")
        matched = False
        if names.startswith("|1|"):
            try:
                _, _, salt, expected = names.split("|")
                matched = hmac.compare_digest(
                    hmac.digest(base64.b64decode(salt), hostname.encode(), "sha1"),
                    base64.b64decode(expected),
                )
            except (ValueError, TypeError):
                continue
        else:
            positive = [item for item in names.split(",") if not item.startswith("!")]
            negative = [item[1:] for item in names.split(",") if item.startswith("!")]
            matched = any(
                fnmatch.fnmatchcase(hostname, item) for item in positive
            ) and not any(fnmatch.fnmatchcase(hostname, item) for item in negative)
        if matched:
            matches.add((marker + fields[1] + b" " + fields[2]).decode())
    return matches


def trust(fd, hostname, fingerprint, key):
    identity = scan(hostname)
    if identity["fingerprint"] != fingerprint or identity["key"] != key:
        raise ValueError("Git host identity changed since approval; nothing accepted")
    handle = os.open(
        "known_hosts",
        os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
        0o600,
        dir_fd=fd,
    )
    with os.fdopen(handle, "r+b") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o022
        ):
            raise ValueError("Unsafe destination known_hosts file")
        fcntl.flock(stream, fcntl.LOCK_EX)
        existing = known(fd, hostname)
        if existing and key not in existing:
            raise ValueError(
                "A different Git host identity is already trusted; it was not replaced"
            )
        if not existing:
            stream.write(b"\n" + hostname.encode() + b" " + key.encode() + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
    return {"trusted": True}


def install(fd, args, payload):
    key, fingerprint, digest, hostname, user, configure = args
    name(key)
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError("Transfer integrity check failed; nothing installed")
    data = json.loads(payload)
    private = base64.b64decode(data["private"], validate=True)
    pub = base64.b64decode(data["public"], validate=True)
    metadata, blob = public(pub)
    if metadata["fingerprint"] != fingerprint:
        raise ValueError("Source identity changed; check the keys again")
    encrypted = paired(private, blob)
    config_name = f"orcan-git-{key}.conf"
    snippet = git_config(key, hostname, user)
    filenames = [key, key + ".pub", config_name]
    with os.fdopen(
        os.open(
            ".orcan-git.lock",
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
            0o600,
            dir_fd=fd,
        ),
        "r+b",
    ) as lock:
        info = os.fstat(lock.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
            or info.st_nlink != 1
        ):
            raise ValueError(
                "Unsafe SSH installation lock; inspect destination permissions"
            )
        fcntl.flock(lock, fcntl.LOCK_EX)
        for filename in filenames:
            try:
                os.stat(filename, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise ValueError(
                "Destination name already exists; skip or choose a different key name"
            )
        existing = None
        if configure == "yes":
            try:
                existing = read(fd, "config")
            except FileNotFoundError:
                existing = b""
        created = []
        try:
            for filename, value in zip(filenames, [private, pub, snippet], strict=True):
                write_new(fd, filename, value)
                created.append(filename)
            if existing is not None:
                # Exact host stanza takes priority only for the explicitly
                # selected Git host. Existing configuration bytes are retained.
                updated = b"Include ~/.ssh/" + config_name.encode() + b"\n" + existing
                write_new(fd, config_name + ".pending", updated)
                created.append(config_name + ".pending")
                try:
                    current = read(fd, "config")
                except FileNotFoundError:
                    current = b""
                if current != existing:
                    raise ValueError(
                        "SSH configuration changed during installation; retry"
                    )
                if not existing:
                    # No-replace publication protects a concurrently created file.
                    try:
                        os.stat("config", dir_fd=fd, follow_symlinks=False)
                    except FileNotFoundError:
                        os.link(
                            config_name + ".pending",
                            "config",
                            src_dir_fd=fd,
                            dst_dir_fd=fd,
                            follow_symlinks=False,
                        )
                        os.unlink(config_name + ".pending", dir_fd=fd)
                    else:
                        os.replace(
                            config_name + ".pending",
                            "config",
                            src_dir_fd=fd,
                            dst_dir_fd=fd,
                        )
                else:
                    os.replace(
                        config_name + ".pending", "config", src_dir_fd=fd, dst_dir_fd=fd
                    )
        except Exception:
            for filename in reversed(created):
                try:
                    os.unlink(filename, dir_fd=fd)
                except FileNotFoundError:
                    pass
            raise
    return {
        "name": key,
        **metadata,
        "encrypted": encrypted,
        "configured": configure == "yes",
        "config": str(Path.home() / ".ssh" / config_name),
    }


def main():
    mode, *args = sys.argv[1:]
    if mode == "list" and not (Path.home() / ".ssh").exists():
        print(json.dumps({"keys": []}))
        return
    if mode == "check":
        key, hostname, user = args
        name(key)
        git_config(key, hostname, user)
        if not (Path.home() / ".ssh").exists():
            print(json.dumps({"ready": True}))
            return
    fd = directory(create=mode == "install")
    try:
        if mode == "list":
            result = {"keys": inventory(fd)}
        elif mode == "check":
            for filename in [
                args[0],
                args[0] + ".pub",
                f"orcan-git-{args[0]}.conf",
                f"orcan-git-{args[0]}.conf.pending",
            ]:
                try:
                    os.stat(filename, dir_fd=fd, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                raise ValueError(
                    "Destination name already exists; skip or choose a different key name"
                )
            result = {"ready": True}
        elif mode == "export":
            key, fingerprint = args
            name(key)
            pub = read(fd, key + ".pub")
            metadata, blob = public(pub)
            if metadata["fingerprint"] != fingerprint:
                raise ValueError("Source identity changed; check the keys again")
            private = read(fd, key, private=True)
            paired(private, blob)
            result = {
                "private": base64.b64encode(private).decode(),
                "public": base64.b64encode(pub).decode(),
            }
        elif mode == "install":
            payload = sys.stdin.buffer.read(2 * LIMIT + 1)
            if len(payload) > 2 * LIMIT:
                raise ValueError("Transfer payload is too large")
            result = install(fd, args, payload)
        elif mode == "host-identity":
            result = scan(args[0])
            existing = known(fd, args[0])
            result["changed"] = bool(existing and result["key"] not in existing)
        elif mode == "trust-host":
            result = trust(fd, *args)
        elif mode == "test":
            key, hostname = args
            name(key)
            host(hostname)
            config = f"orcan-git-{key}.conf"
            read(fd, config)  # Refuse symlinks/foreign files before invoking SSH.
            checked = subprocess.run(
                [
                    "ssh",
                    "-F",
                    str(Path.home() / ".ssh" / config),
                    "-T",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "ConnectTimeout=10",
                    hostname,
                ],
                capture_output=True,
                timeout=15,
                check=False,
            )
            output = (checked.stdout + checked.stderr).decode(errors="replace")
            success = (
                checked.returncode == 0
                or "successfully authenticated" in output
                or "Welcome to GitLab" in output
            )
            untrusted = (
                not success
                and "Host key verification failed" in output
                and "REMOTE HOST IDENTIFICATION HAS CHANGED" not in output
            )
            result = {
                "ready": success,
                "untrusted": untrusted,
                "detail": "Git SSH authentication succeeded"
                if success
                else "Git access not ready. The Git host identity must be trusted and an encrypted key must be unlocked on the destination; no identity was accepted automatically.",
            }
        else:
            raise ValueError("Unknown SSH preparation action")
        print(json.dumps(result))
    finally:
        os.close(fd)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Never print key material, subprocess output or arbitrary parse errors.
        message = (
            str(error)
            if isinstance(error, ValueError)
            and not isinstance(error, (UnicodeError, json.JSONDecodeError))
            else "SSH preparation failed; check permissions, OpenSSH format and required tools"
        )
        print(message, file=sys.stderr)
        raise SystemExit(2) from None
