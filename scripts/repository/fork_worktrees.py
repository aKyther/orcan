"""Resolve owner:branch worktree sources through GitHub, without guessing URLs."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse


class ForkSourceError(ValueError):
    """An explicit fork source could not be resolved or fetched."""


def worktree_branch(source: str) -> str:
    """Validate a source and return its collision-separated local branch name."""
    source = source.strip()
    if ":" in source:
        owner, branch = source.split(":", 1)
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", owner):
            raise ForkSourceError("Use owner:branch, for example alice:fix/login.")
        local = f"fork/{owner.lower()}/{branch}"
    else:
        branch = source
        local = branch
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", branch):
        raise ForkSourceError(f"Invalid branch source: {source}")
    for value in (branch, local):
        if subprocess.run(
            ["git", "check-ref-format", "--branch", value],
            capture_output=True,
            check=False,
        ).returncode:
            raise ForkSourceError(f"Invalid branch source: {source}")
    return local


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise ForkSourceError("Cannot inspect the repository remote configuration.")
    return result.stdout.strip()


def _api(repo: Path, endpoint: str, *, hostname: str, pages: bool = False):
    args = ["gh", "api", "--hostname", hostname, endpoint]
    if pages:
        args += ["--paginate", "--slurp"]
    try:
        result = subprocess.run(
            args,
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            env={**os.environ, "GH_PROMPT_DISABLED": "1"},
        )
        if result.returncode:
            raise ForkSourceError(
                f"GitHub lookup failed on {hostname}. Check gh auth status --hostname {hostname} and repository access, then retry."
            )
        data = json.loads(result.stdout)
        valid = (
            (
                isinstance(data, list)
                and all(
                    isinstance(page, list)
                    and all(isinstance(item, dict) for item in page)
                    for page in data
                )
            )
            if pages
            else isinstance(data, dict)
        )
        if not valid:
            raise ForkSourceError("GitHub returned an invalid repository response.")
        return data
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        raise ForkSourceError(
            "Fork lookup needs GitHub CLI (gh), GitHub access and a working connection."
        ) from exc


def _remote_source(url: str) -> tuple[str, str, str]:
    """Return API host, repository name and clone prefix from HTTPS/SSH remotes."""
    scp = re.fullmatch(
        r"((?:[A-Za-z0-9_.-]+@)?([A-Za-z0-9][A-Za-z0-9.-]*)):([^/].*)", url
    )
    if scp:
        hostname = scp[2].lower()
        name = scp[3].removesuffix(".git")
        prefix = scp[1] + ":"
    else:
        try:
            parsed = urlparse(url)
            host = parsed.hostname or ""
            port = parsed.port
        except ValueError as exc:
            raise ForkSourceError("Invalid GitHub remote URL.") from exc
        if (
            parsed.scheme not in ("https", "ssh")
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", host)
            or parsed.query
            or parsed.fragment
            or parsed.password is not None
        ):
            raise ForkSourceError(
                "Automatic owner:branch lookup needs an HTTPS or SSH GitHub remote (including GitHub Enterprise)."
            )
        hostname = host.lower()
        authority = hostname + (f":{port}" if port is not None else "")
        if parsed.scheme == "https":
            hostname = authority  # HTTPS port also applies to API requests.
        elif parsed.username:
            authority = parsed.username + "@" + authority
        name = parsed.path.strip("/").removesuffix(".git")
        prefix = f"{parsed.scheme}://{authority}/"
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", name):
        raise ForkSourceError(
            "Cannot identify the GitHub repository from its remote URL."
        )
    return hostname, name, prefix


def resolve_fork(repo: Path, owner: str, remote: str = "origin") -> tuple[str, str]:
    """Return (full_name, clone_url), including renamed Enterprise forks."""
    url = _git(repo, "remote", "get-url", remote)
    hostname, name, prefix = _remote_source(url)
    base = _api(repo, f"repos/{name}", hostname=hostname)
    root = base.get("source", base).get("full_name", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", root):
        raise ForkSourceError("GitHub returned an invalid source repository.")
    candidates = (
        [base]
        if base.get("owner", {}).get("login", "").lower() == owner.lower()
        else []
    )
    if not candidates:
        candidates = [
            item
            for page in _api(
                repo, f"repos/{root}/forks?per_page=100", hostname=hostname, pages=True
            )
            for item in page
            if item.get("owner", {}).get("login", "").lower() == owner.lower()
        ]
    if len(candidates) != 1:
        raise ForkSourceError(
            f"Expected one accessible fork owned by {owner}; found {len(candidates)}. Check the owner and GitHub access."
        )
    full_name = candidates[0].get("full_name", "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", full_name):
        raise ForkSourceError("GitHub returned an invalid fork repository.")
    return full_name, f"{prefix}{full_name}.git"


def fetch_fork(repo: Path, source: str, remote: str = "origin") -> tuple[str, str]:
    """Fetch the exact branch, keep the original checkout and remote untouched."""
    local = worktree_branch(source)
    owner, branch = source.split(":", 1)
    full_name, clone = resolve_fork(repo, owner, remote)
    fork_remote = "orcan-fork-" + owner.lower()
    remotes = _git(repo, "remote").splitlines()
    if fork_remote in remotes:
        if _git(repo, "config", "--get", f"remote.{fork_remote}.url") != clone:
            raise ForkSourceError(
                f"Remote {fork_remote} points elsewhere. Rename it before retrying; Orcan will not overwrite it."
            )
    else:
        _git(repo, "remote", "add", fork_remote, clone)
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes -o ConnectTimeout=5")
    ref = f"refs/remotes/{fork_remote}/{branch}"
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "fetch",
                "--quiet",
                "--no-tags",
                fork_remote,
                f"+refs/heads/{branch}:{ref}",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ForkSourceError(
            f"Could not fetch {full_name}:{branch}. Check access and connection, then retry."
        ) from exc
    if result.returncode:
        raise ForkSourceError(
            f"Could not fetch {full_name}:{branch}. Check that the branch exists and is accessible."
        )
    return local, f"{fork_remote}/{branch}"
