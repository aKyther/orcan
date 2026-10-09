"""Git access preparation using disposable keys only; no live SSH or network."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "studio/app/src-tauri/src/ssh_access.py"
spec = importlib.util.spec_from_file_location("studio_ssh_access", SCRIPT)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


@pytest.fixture
def source(tmp_path):
    home = tmp_path / "source"
    ssh = home / ".ssh"
    ssh.mkdir(parents=True, mode=0o700)
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(ssh / "id_test")],
        check=True,
    )
    return home


def run(home, *args, data=b""):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input=data,
        capture_output=True,
        env={**os.environ, "HOME": str(home)},
        check=False,
    )


def export(source):
    listed = run(source, "list")
    assert listed.returncode == 0, listed.stderr
    identity = json.loads(listed.stdout)["keys"][0]
    payload = run(source, "export", identity["name"], identity["fingerprint"])
    assert payload.returncode == 0, payload.stderr
    return identity, payload.stdout.strip()


def install(destination, identity, payload, configure="no", key="id_test"):
    return run(
        destination,
        "install",
        key,
        identity["fingerprint"],
        hashlib.sha256(payload).hexdigest(),
        "github.com",
        "git",
        configure,
        data=payload,
    )


def test_inventory_contains_public_metadata_only_and_export_verifies_pair(source):
    identity, payload = export(source)
    assert set(identity) == {"name", "algorithm", "fingerprint"}
    assert identity["fingerprint"].startswith("SHA256:")
    assert "private" not in run(source, "list").stdout.decode()
    data = json.loads(payload)
    assert base64.b64decode(data["private"]) == (source / ".ssh/id_test").read_bytes()
    changed = run(source, "export", "id_test", "SHA256:changed")
    assert changed.returncode != 0
    assert not changed.stdout


def test_generated_include_restores_global_host_scope():
    assert helper.git_config("id_test", "github.com", "git").endswith(b"Host *\n")


def test_install_rejects_fifo_lock_without_hanging(source, tmp_path):
    identity, payload = export(source)
    destination = tmp_path / "destination"
    ssh = destination / ".ssh"
    ssh.mkdir(parents=True, mode=0o700)
    os.mkfifo(ssh / ".orcan-git.lock", 0o600)
    result = install(destination, identity, payload)
    assert result.returncode != 0
    assert not (ssh / "id_test").exists()


def test_transfer_creates_private_pair_but_does_not_copy_config_or_trust(
    source, tmp_path
):
    identity, payload = export(source)
    (source / ".ssh/config").write_text("Host secret-source-alias\n")
    (source / ".ssh/known_hosts").write_text("not transferred\n")
    destination = tmp_path / "destination"
    destination.mkdir()
    result = install(destination, identity, payload)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["fingerprint"] == identity["fingerprint"]
    ssh = destination / ".ssh"
    assert ssh.stat().st_mode & 0o777 == 0o700
    for name in ("id_test", "id_test.pub", "orcan-git-id_test.conf"):
        assert (ssh / name).stat().st_mode & 0o777 == 0o600
    assert not (ssh / "known_hosts").exists()
    assert not (ssh / "config").exists()
    before = (ssh / "id_test").read_bytes()
    collision = install(destination, identity, payload)
    assert collision.returncode != 0
    assert (ssh / "id_test").read_bytes() == before
    assert not run(destination, "check", "id_test", "github.com", "git").returncode == 0


def test_git_configuration_requires_opt_in_and_preserves_existing_bytes(
    source, tmp_path
):
    identity, payload = export(source)
    destination = tmp_path / "destination"
    ssh = destination / ".ssh"
    ssh.mkdir(parents=True, mode=0o700)
    original = b"# keep me\nHost internal\n  User example\n"
    (ssh / "config").write_bytes(original)
    result = install(destination, identity, payload, configure="yes")
    assert result.returncode == 0, result.stderr
    assert (
        ssh / "config"
    ).read_bytes() == b"Include ~/.ssh/orcan-git-id_test.conf\n" + original
    snippet = (ssh / "orcan-git-id_test.conf").read_text()
    assert "Host github.com\n" in snippet
    assert "StrictHostKeyChecking yes" in snippet
    assert not (ssh / "orcan-git-id_test.conf.pending").exists()


def test_bad_digest_invalid_names_and_symlinked_destination_never_install(
    source, tmp_path
):
    identity, payload = export(source)
    destination = tmp_path / "destination"
    destination.mkdir()
    for key in (
        "../escape",
        "config",
        "known_hosts",
        "authorized_keys",
        "bad.conf",
        "a;b",
    ):
        assert install(destination, identity, payload, key=key).returncode != 0
    bad = run(
        destination,
        "install",
        "id_test",
        identity["fingerprint"],
        "0" * 64,
        "github.com",
        "git",
        "no",
        data=payload,
    )
    assert bad.returncode != 0
    assert not (destination / ".ssh/id_test").exists()
    (destination / ".ssh").rmdir()
    (destination / ".ssh").symlink_to(source / ".ssh", target_is_directory=True)
    assert install(destination, identity, payload).returncode != 0


def test_source_symlinks_and_unsafe_private_permissions_are_not_listed(source):
    key = source / ".ssh/id_test"
    key.chmod(0o644)
    assert json.loads(run(source, "list").stdout)["keys"] == []
    key.chmod(0o600)
    key.rename(source / "outside")
    key.symlink_to(source / "outside")
    assert json.loads(run(source, "list").stdout)["keys"] == []


def test_encrypted_key_is_transferred_unchanged_without_a_passphrase_prompt(
    source, tmp_path
):
    key = source / ".ssh/id_test"
    subprocess.run(
        [
            "ssh-keygen",
            "-q",
            "-p",
            "-P",
            "",
            "-N",
            "disposable-test-passphrase",
            "-f",
            str(key),
        ],
        check=True,
        capture_output=True,
    )
    identity, payload = export(source)
    destination = tmp_path / "destination"
    destination.mkdir()
    installed = install(destination, identity, payload)
    assert installed.returncode == 0, installed.stderr
    assert json.loads(installed.stdout)["encrypted"] is True
    assert (destination / ".ssh/id_test").read_bytes() == key.read_bytes()


def test_mismatched_public_pair_is_refused_before_export(source, tmp_path):
    extra = tmp_path / "other"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(extra)], check=True
    )
    (source / ".ssh/id_test.pub").write_bytes(extra.with_suffix(".pub").read_bytes())
    identity = json.loads(run(source, "list").stdout)["keys"][0]
    result = run(source, "export", "id_test", identity["fingerprint"])
    assert result.returncode != 0
    assert not result.stdout


def test_partial_failure_preserves_a_racing_foreign_file(source, tmp_path, monkeypatch):
    identity, payload = export(source)
    directory = tmp_path / "receiver"
    directory.mkdir(mode=0o700)
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    original = helper.write_new

    def raced(fd, filename, value):
        if filename.endswith(".pub"):
            (directory / filename).write_bytes(b"foreign")
        original(fd, filename, value)

    monkeypatch.setattr(helper, "write_new", raced)
    try:
        with pytest.raises(FileExistsError):
            helper.install(
                fd,
                [
                    "id_test",
                    identity["fingerprint"],
                    hashlib.sha256(payload).hexdigest(),
                    "github.com",
                    "git",
                    "no",
                ],
                payload,
            )
    finally:
        os.close(fd)
    assert not (directory / "id_test").exists()
    assert (directory / "id_test.pub").read_bytes() == b"foreign"


def test_host_trust_is_rechecked_and_never_replaces_changed_or_revoked_keys(
    source, monkeypatch
):
    pub = (source / ".ssh/id_test.pub").read_bytes()
    metadata, _ = helper.public(pub)
    key = b" ".join(pub.split()[:2]).decode()
    identity = {"host": "github.com", "key": key, **metadata}
    monkeypatch.setattr(helper, "scan", lambda _host: identity)
    fd = os.open(source / ".ssh", os.O_RDONLY | os.O_DIRECTORY)
    try:
        with pytest.raises(ValueError):
            helper.trust(fd, "github.com", "SHA256:changed", key)
        assert helper.trust(fd, "github.com", metadata["fingerprint"], key)["trusted"]
        before = (source / ".ssh/known_hosts").read_bytes()
        helper.trust(fd, "github.com", metadata["fingerprint"], key)
        assert (source / ".ssh/known_hosts").read_bytes() == before
        (source / ".ssh/known_hosts").write_text("@revoked github.com " + key + "\n")
        with pytest.raises(ValueError):
            helper.trust(fd, "github.com", metadata["fingerprint"], key)
        assert (source / ".ssh/known_hosts").read_text().startswith("@revoked")
    finally:
        os.close(fd)
