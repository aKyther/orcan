#!/usr/bin/env python3
"""Context Assertion store + Applicability Layer (RFC-0001 v2).

Orcan stays the Context Manager: this module never talks to an agent and
never runs during a session. It is a pre-session compiler stage only.

Model (see docs/en/ideas/context-assertions.md for the full RFC writeup):

- A **Context Assertion** is one record: content + kind (presentational
  label only) + justification (why it exists / what problem it solves) +
  an applicability predicate + a lifecycle status
  (proposed -> accepted -> rejected|retired).
- Assertions are *anchored* to a project path for storage/versioning only.
  The anchor never determines when an assertion applies — that is the
  applicability predicate's job. This is the fix for the v1 "Project
  Knowledge" model, where storage location and scope were conflated.
- The **Applicability Layer** (select_for_workspace) is a pure function of
  (accepted assertions anchored to this workspace's projects) x
  (Context Signature: workspace name, repo set, per-repo branch) ->
  matched assertions + a mechanical, non-LLM justification trail.
- MVP composition rule: AND across atom types, OR within an atom's list.
  Full nested AND/OR/NOT expressions are explicitly deferred.
- MVP does not attempt automated conflict detection between assertions;
  it relies on all matched assertions being rendered together, visibly,
  so a human/agent can spot contradictions. A shared "topic" key for
  real conflict detection is a natural v2 extension.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

STATUSES = ("proposed", "accepted", "rejected", "retired")
APPLICABILITY_KEYS = (
    "workspace",
    "repo_set_all_of",
    "repo_set_any_of",
    "repo_set_none_of",
    "branch",
    "valid_from",
    "valid_until",
)
EPISTEMIC_STATUSES = ("fact", "interpretation", "hypothesis", "conclusion")
CRITICALITY_LEVELS = ("normal", "high")
RELATION_TYPES = ("depends_on", "risk_of", "supersedes", "conflicts_with")
MAX_RELATION_HOPS = 1  # bounded on purpose — see select_for_workspace


def die(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    raise SystemExit(1)


# ---------------------------------------------------------------------------
# Storage paths ($ORCAN_DATA/context/<project-id>/) — mirrors worktrees'
# $ORCAN_PROJECTS_ROOT/.worktrees layout and env var convention.
# ---------------------------------------------------------------------------


def orcan_data_root() -> Path:
    raw = os.environ.get("ORCAN_DATA", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".config" / "orcan").resolve()


def store_root(*, ensure: bool = False) -> Path:
    root = orcan_data_root() / "context"
    if ensure:
        root.mkdir(parents=True, exist_ok=True)
    return root


def _git_common_dir(project_path: Path) -> Path | None:
    """The git dir shared by a repo's main checkout and all its worktrees.

    Returns None for non-git directories (caller falls back to the path).
    """
    r = subprocess.run(
        ["git", "-C", str(project_path), "rev-parse", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        return None
    out = r.stdout.strip()
    if not out:
        return None
    p = Path(out)
    if not p.is_absolute():
        p = project_path / p
    return p.resolve()


def project_id(project_path: Path) -> str:
    """Stable, collision-resistant id keyed by git identity, not working-copy path.

    All worktrees of one repo (the main checkout, plus any created by
    `orcan context worktree create`) share the same git *common dir* even
    though each lives at its own filesystem path. Keying identity on that
    common dir — instead of on `project_path` itself — means a branch
    worktree of a repo shares its Context Assertion store with the main
    checkout, refined only by the `branch` applicability atom, rather than
    starting from an empty store just because it happens to live elsewhere
    on disk. Directories that aren't git repos fall back to their resolved
    path (stable, just not worktree-aware).
    """
    resolved = project_path.resolve()
    common_dir = _git_common_dir(resolved)
    if common_dir is not None:
        identity = str(common_dir)
        base_source = common_dir.parent if common_dir.name == ".git" else common_dir
    else:
        identity = str(resolved)
        base_source = resolved
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:10]
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", base_source.name).strip("-") or "project"
    return f"{base}-{digest}"


def project_store_dir(project_path: Path, *, ensure: bool = False) -> Path:
    store_dir = store_root(ensure=ensure) / project_id(project_path)
    if ensure:
        (store_dir / "objects").mkdir(parents=True, exist_ok=True)
        _git_init_if_needed(store_dir)
        _write_anchor_meta(store_dir, project_path)
    return store_dir


def _write_anchor_meta(store_dir: Path, project_path: Path) -> None:
    meta_path = store_dir / "anchor.json"
    if meta_path.exists():
        return
    meta_path.write_text(
        json.dumps({"anchor_path": str(project_path.resolve())}, indent=2) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Git plumbing — one repo per anchor, history = version history.
# ---------------------------------------------------------------------------


def run_git(store_dir: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(store_dir), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def _git_init_if_needed(store_dir: Path) -> None:
    if (store_dir / ".git").is_dir():
        return
    run_git(store_dir, "init", "--quiet")
    run_git(store_dir, "config", "user.email", "context-assertions@orcan.local")
    run_git(store_dir, "config", "user.name", "orcan-context-assertions")


def _commit(store_dir: Path, message: str) -> None:
    run_git(store_dir, "add", "-A")
    # Host GIT_AUTHOR_*/GIT_COMMITTER_* env vars (set — sometimes empty — by
    # orcan sync's git-identity copy) outrank local `git config`. Pin this
    # store's bot identity explicitly so an empty host identity can't break
    # commits here (see update-env.sh's own warning about unset host identity).
    env = dict(os.environ)
    for key in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        env[key] = "orcan-context-assertions"
    for key in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        env[key] = "context-assertions@orcan.local"
    r = subprocess.run(
        ["git", "-C", str(store_dir), "commit", "--quiet", "-m", message],
        capture_output=True,
        text=True,
        env=env,
    )
    if r.returncode != 0 and "nothing to commit" not in (r.stdout + r.stderr).lower():
        die(f"git commit failed in {store_dir}: {(r.stderr or r.stdout).strip()}")


# ---------------------------------------------------------------------------
# Index (objects/<id>.json holds the full record; index.json is the "simple
# index" — enough to list/filter without reading every object file).
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _index_path(store_dir: Path) -> Path:
    return store_dir / "index.json"


def _load_index(store_dir: Path) -> dict[str, dict]:
    p = _index_path(store_dir)
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        die(f"invalid context-assertions index {p}: {exc}")


def _save_index(store_dir: Path, index: dict[str, dict]) -> None:
    _index_path(store_dir).write_text(
        json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _index_entry(obj: dict) -> dict:
    return {
        "title": obj["title"],
        "kind": obj["kind"],
        "status": obj["status"],
        "epistemic_status": obj.get("epistemic_status", "fact"),
        "criticality": obj.get("criticality", "normal"),
        "created_at": obj["created_at"],
        "updated_at": obj["updated_at"],
    }


def _object_path(store_dir: Path, object_id: str) -> Path:
    return store_dir / "objects" / f"{object_id}.json"


def _load_object(store_dir: Path, object_id: str) -> dict:
    p = _object_path(store_dir, object_id)
    if not p.is_file():
        die(f"unknown context assertion: {object_id}")
    return json.loads(p.read_text(encoding="utf-8"))


def _save_object(store_dir: Path, obj: dict) -> None:
    _object_path(store_dir, obj["id"]).write_text(
        json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    index = _load_index(store_dir)
    index[obj["id"]] = _index_entry(obj)
    _save_index(store_dir, index)


# ---------------------------------------------------------------------------
# Applicability predicate — validated, normalised, never silently ignored.
# ---------------------------------------------------------------------------


def normalize_applicability(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    unknown = set(raw) - set(APPLICABILITY_KEYS)
    if unknown:
        die(f"unknown applicability keys: {sorted(unknown)}")
    out: dict[str, Any] = {}
    for key in ("workspace", "repo_set_all_of", "repo_set_any_of", "repo_set_none_of", "branch"):
        val = raw.get(key)
        if val is None:
            continue
        if isinstance(val, str):
            val = [val]
        if not isinstance(val, list) or not all(isinstance(v, str) for v in val):
            die(f"applicability.{key} must be a string or list of strings")
        out[key] = [v.strip() for v in val if v.strip()]
    for key in ("valid_from", "valid_until"):
        val = raw.get(key)
        if val is None:
            continue
        try:
            date.fromisoformat(str(val))
        except ValueError:
            die(f"applicability.{key} must be YYYY-MM-DD")
        out[key] = str(val)
    return out


def normalize_relations(raw: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    """Typed edges, always attached to the SOURCE (the assertion being
    authored) — never mutates the target. Closed vocabulary on purpose:
    free-text "related to" is just notes with extra steps. Each target must
    already exist (existence is checked here; the target's own status is
    re-checked at select time, since it may be retired later)."""
    if not raw:
        return []
    out: list[dict[str, str]] = []
    for i, rel in enumerate(raw):
        if not isinstance(rel, dict):
            die(f"relations[{i}] must be an object")
        rel_type = str(rel.get("type") or "").strip()
        target_id = str(rel.get("target_id") or "").strip()
        target_project = str(rel.get("target_project") or "").strip()
        if rel_type not in RELATION_TYPES:
            die(f"relations[{i}].type must be one of {RELATION_TYPES}, got {rel_type!r}")
        if not target_id or not target_project:
            die(f"relations[{i}] needs target_id and target_project")
        target_path = Path(target_project)
        if not target_path.is_absolute():
            die(f"relations[{i}].target_project must be an absolute path")
        try:
            get_object(target_path, target_id)
        except SystemExit:
            die(f"relations[{i}]: no such assertion {target_id!r} anchored at {target_project}")
        out.append({"type": rel_type, "target_id": target_id, "target_project": str(target_path.resolve())})
    return out


# ---------------------------------------------------------------------------
# Reflection / propose — produces a candidate, status "proposed".
# Nothing here is used by compilation until Review accepts it.
# ---------------------------------------------------------------------------


def _normalize_epistemic_status(value: str) -> str:
    value = (value or "fact").strip() or "fact"
    if value not in EPISTEMIC_STATUSES:
        die(f"epistemic_status must be one of {EPISTEMIC_STATUSES}, got {value!r}")
    return value


def _normalize_criticality(value: str) -> str:
    value = (value or "normal").strip() or "normal"
    if value not in CRITICALITY_LEVELS:
        die(f"criticality must be one of {CRITICALITY_LEVELS}, got {value!r}")
    return value


def propose(
    project_path: Path,
    *,
    content: str,
    justification: str,
    title: str = "",
    kind: str = "fact",
    applicability: dict[str, Any] | None = None,
    epistemic_status: str = "fact",
    criticality: str = "normal",
    relations: list[dict[str, Any]] | None = None,
) -> dict:
    content = content.strip()
    justification = justification.strip()
    if not content:
        die("assertion content is empty")
    if not justification:
        die("justification is required: what problem does this solve?")
    store_dir = project_store_dir(project_path, ensure=True)
    object_id = uuid.uuid4().hex[:12]
    now = _now()
    obj = {
        "id": object_id,
        "anchor_path": str(project_path.resolve()),
        "title": title.strip() or content.splitlines()[0][:80],
        "content": content,
        "kind": kind.strip() or "fact",
        "justification": justification,
        "applicability": normalize_applicability(applicability),
        "epistemic_status": _normalize_epistemic_status(epistemic_status),
        "criticality": _normalize_criticality(criticality),
        "relations": normalize_relations(relations),
        "status": "proposed",
        "created_at": now,
        "updated_at": now,
    }
    _save_object(store_dir, obj)
    _commit(store_dir, f"propose {object_id}: {obj['title']}")
    return obj


def _transition(
    project_path: Path,
    object_id: str,
    *,
    to_status: str,
    from_statuses: tuple[str, ...],
    verb: str,
    edited_content: str = "",
    edited_justification: str = "",
    edited_applicability: dict[str, Any] | None = None,
    edited_epistemic_status: str = "",
    edited_criticality: str = "",
    edited_relations: list[dict[str, Any]] | None = None,
) -> dict:
    store_dir = project_store_dir(project_path, ensure=True)
    obj = _load_object(store_dir, object_id)
    if obj["status"] not in from_statuses:
        die(f"cannot {verb} {object_id}: status is {obj['status']!r}, expected one of {from_statuses}")
    if edited_content.strip():
        obj["content"] = edited_content.strip()
    if edited_justification.strip():
        obj["justification"] = edited_justification.strip()
    if edited_applicability is not None:
        obj["applicability"] = normalize_applicability(edited_applicability)
    if edited_epistemic_status.strip():
        obj["epistemic_status"] = _normalize_epistemic_status(edited_epistemic_status)
    if edited_criticality.strip():
        obj["criticality"] = _normalize_criticality(edited_criticality)
    if edited_relations is not None:
        obj["relations"] = normalize_relations(edited_relations)
    obj["status"] = to_status
    obj["updated_at"] = _now()
    _save_object(store_dir, obj)
    _commit(store_dir, f"{verb} {object_id}: {obj['title']}")
    return obj


def accept(
    project_path: Path,
    object_id: str,
    *,
    edited_content: str = "",
    edited_justification: str = "",
    edited_applicability: dict[str, Any] | None = None,
    edited_epistemic_status: str = "",
    edited_criticality: str = "",
    edited_relations: list[dict[str, Any]] | None = None,
) -> dict:
    """Review Gate: the only path to 'accepted'. Never automatic.

    The reviewer — not the proposer — is best placed to correct a
    Reflection-drafted guess at scope, epistemic status, criticality, or
    relations, same reasoning for all four: the author sees intent, the
    reviewer sees whether it actually holds.
    """
    return _transition(
        project_path,
        object_id,
        to_status="accepted",
        from_statuses=("proposed",),
        verb="accept",
        edited_content=edited_content,
        edited_justification=edited_justification,
        edited_applicability=edited_applicability,
        edited_epistemic_status=edited_epistemic_status,
        edited_criticality=edited_criticality,
        edited_relations=edited_relations,
    )


def reject(project_path: Path, object_id: str) -> dict:
    return _transition(project_path, object_id, to_status="rejected", from_statuses=("proposed",), verb="reject")


def retire(project_path: Path, object_id: str) -> dict:
    return _transition(project_path, object_id, to_status="retired", from_statuses=("accepted",), verb="retire")


def list_objects(project_path: Path, *, status: str = "") -> list[dict]:
    store_dir = project_store_dir(project_path, ensure=False)
    items = [{"id": oid, **entry} for oid, entry in _load_index(store_dir).items()]
    if status:
        items = [i for i in items if i["status"] == status]
    items.sort(key=lambda i: i["created_at"])
    return items


def get_object(project_path: Path, object_id: str) -> dict:
    store_dir = project_store_dir(project_path, ensure=False)
    return _load_object(store_dir, object_id)


# ---------------------------------------------------------------------------
# Context Signature — facts about "now", derived from what Orcan already
# knows for free (workspace config + git). Declared task intent/tags are an
# explicitly deferred extension (see docs) — v1 evaluates only what is
# knowable before the agent starts without a new input surface.
# ---------------------------------------------------------------------------


def build_signature(workspace_name: str, projects: list[dict[str, str]]) -> dict[str, Any]:
    repos = [p["name"] for p in projects if p.get("name")]
    branches: dict[str, str] = {}
    for p in projects:
        name = p.get("name")
        path = p.get("path")
        if not name or not path:
            continue
        branches[name] = _current_branch(Path(path))
    return {"workspace": workspace_name, "repos": repos, "branches": branches}


def _current_branch(path: Path) -> str:
    if not path.is_dir():
        return ""
    r = subprocess.run(
        ["git", "-C", str(path), "branch", "--show-current"],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        return ""
    return r.stdout.strip()


# ---------------------------------------------------------------------------
# Applicability Layer — pure matching, mechanical (non-LLM) justification.
# ---------------------------------------------------------------------------


def matches(applicability: dict[str, Any], signature: dict[str, Any]) -> tuple[bool, list[str]]:
    """AND across atom types, OR within an atom's list. Empty predicate = always matches."""
    reasons: list[str] = []
    repos = set(signature.get("repos") or [])
    branches: dict[str, str] = signature.get("branches") or {}

    ws_list = applicability.get("workspace")
    if ws_list:
        if signature.get("workspace") not in ws_list:
            return False, []
        reasons.append(f"workspace={signature.get('workspace')}")

    all_of = applicability.get("repo_set_all_of")
    if all_of:
        missing = [r for r in all_of if r not in repos]
        if missing:
            return False, []
        reasons.append(f"repo_set_all_of={all_of} present")

    any_of = applicability.get("repo_set_any_of")
    if any_of:
        hit = [r for r in any_of if r in repos]
        if not hit:
            return False, []
        reasons.append(f"repo_set_any_of matched {hit}")

    none_of = applicability.get("repo_set_none_of")
    if none_of:
        hit = [r for r in none_of if r in repos]
        if hit:
            return False, []
        reasons.append(f"repo_set_none_of={none_of} absent")

    patterns = applicability.get("branch")
    if patterns:
        qualifying = (all_of or []) + (any_of or []) or list(branches)
        matched_repo = None
        for repo_name in qualifying:
            branch = branches.get(repo_name, "")
            if branch and any(fnmatch.fnmatch(branch, pat) for pat in patterns):
                matched_repo = (repo_name, branch)
                break
        if not matched_repo:
            return False, []
        reasons.append(f"branch({matched_repo[0]})={matched_repo[1]} matches {patterns}")

    today = date.today()
    valid_from = applicability.get("valid_from")
    if valid_from and today < date.fromisoformat(valid_from):
        return False, []
    valid_until = applicability.get("valid_until")
    if valid_until and today > date.fromisoformat(valid_until):
        return False, []
    if valid_from or valid_until:
        reasons.append(f"valid {valid_from or '…'}..{valid_until or '…'}")

    if not reasons:
        reasons.append(f"unconditional (anchored under workspace {signature.get('workspace')!r})")
    return True, reasons


def select_for_workspace(
    workspace_name: str,
    projects: list[dict[str, str]],
    *,
    limit: int = 20,
) -> list[dict]:
    """The Applicability Layer. Pure function of (accepted assertions x signature).

    Returns matched assertions with a bound, mechanical "why" trail attached
    as `justification_trail` — distinct from the author's own `justification`
    (why the assertion exists at all).

    After direct applicability matching, does one — and only one — bounded
    hop of relation traversal (RFC-0002): for each directly-matched item,
    pull in `accepted` relation targets, but only when the target's own
    project is itself mounted in this workspace (a relation cannot leak an
    assertion belonging to a project the workspace doesn't have). Related
    items never trigger a second hop and never push the total past `limit` —
    this is a small enrichment, not a graph walk.
    """
    signature = build_signature(workspace_name, projects)
    project_paths_present = {str(Path(p["path"]).resolve()) for p in projects if p.get("path")}
    selected: list[dict] = []
    for p in projects:
        path = p.get("path")
        if not path:
            continue
        project_path = Path(path)
        store_dir = project_store_dir(project_path, ensure=False)
        for oid, entry in _load_index(store_dir).items():
            if entry["status"] != "accepted":
                continue
            obj = _load_object(store_dir, oid)
            ok, reasons = matches(obj.get("applicability") or {}, signature)
            if not ok:
                continue
            obj = dict(obj)
            obj["justification_trail"] = reasons
            selected.append(obj)
    selected.sort(key=lambda o: o["updated_at"], reverse=True)
    if limit > 0:
        selected = selected[:limit]

    selected_ids = {o["id"] for o in selected}
    related: list[dict] = []
    budget = None if limit <= 0 else max(0, limit - len(selected))
    for obj in selected:
        for rel in obj.get("relations") or []:
            if budget is not None and budget <= 0:
                break
            target_id = rel.get("target_id")
            target_project = rel.get("target_project")
            if not target_id or target_id in selected_ids:
                continue
            if target_project not in project_paths_present:
                continue  # target's project isn't mounted here — nothing to pull in
            try:
                target = get_object(Path(target_project), target_id)
            except SystemExit:
                continue
            if target["status"] != "accepted":
                continue
            target = dict(target)
            target["justification_trail"] = [
                f"pulled in via {rel['type']} from {obj['id']} ({obj['title']!r})"
            ]
            related.append(target)
            selected_ids.add(target_id)
            if budget is not None:
                budget -= 1
    return selected + related


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _resolve_project(raw: str) -> Path:
    p = Path(raw)
    if not p.is_absolute():
        die("--project must be an absolute path")
    if not p.is_dir():
        die(f"not a directory: {p}")
    return p.resolve()


def _read_content(raw: str) -> str:
    if raw == "-":
        return sys.stdin.read()
    p = Path(raw)
    if not p.is_file():
        die(f"no such file: {p}")
    return p.read_text(encoding="utf-8")


def _parse_applicability_args(args: argparse.Namespace) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if args.workspace:
        out["workspace"] = args.workspace
    if args.repo_all_of:
        out["repo_set_all_of"] = args.repo_all_of
    if args.repo_any_of:
        out["repo_set_any_of"] = args.repo_any_of
    if args.repo_none_of:
        out["repo_set_none_of"] = args.repo_none_of
    if args.branch:
        out["branch"] = args.branch
    if args.valid_from:
        out["valid_from"] = args.valid_from
    if args.valid_until:
        out["valid_until"] = args.valid_until
    return out


def _add_applicability_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--workspace", action="append", default=[], help="Repeatable: applies only in this workspace")
    p.add_argument("--repo-all-of", action="append", default=[], help="Repeatable: all of these repo names must be present")
    p.add_argument("--repo-any-of", action="append", default=[], help="Repeatable: at least one of these repo names must be present")
    p.add_argument("--repo-none-of", action="append", default=[], help="Repeatable: none of these repo names may be present")
    p.add_argument("--branch", action="append", default=[], help="Repeatable glob, e.g. release/*")
    p.add_argument("--valid-from", default="", help="YYYY-MM-DD")
    p.add_argument("--valid-until", default="", help="YYYY-MM-DD")


def _add_rfc0002_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--epistemic-status", default="", help=f"One of {EPISTEMIC_STATUSES} (default: fact)")
    p.add_argument("--criticality", default="", help=f"One of {CRITICALITY_LEVELS} (default: normal)")
    p.add_argument(
        "--relation",
        action="append",
        default=[],
        metavar="TYPE:TARGET_ID:TARGET_PROJECT_PATH",
        help=f"Repeatable. TYPE one of {RELATION_TYPES}; TARGET_PROJECT_PATH is absolute",
    )


def _parse_relation_args(raw: list[str]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for spec in raw:
        parts = spec.split(":", 2)
        if len(parts) != 3:
            die(f"--relation must be TYPE:TARGET_ID:TARGET_PROJECT_PATH, got {spec!r}")
        rel_type, target_id, target_project = (p.strip() for p in parts)
        out.append({"type": rel_type, "target_id": target_id, "target_project": target_project})
    return out


def cmd_propose(args: argparse.Namespace) -> None:
    project_path = _resolve_project(args.project)
    content = _read_content(args.file) if args.file else args.text
    obj = propose(
        project_path,
        content=content,
        justification=args.justification,
        title=args.title,
        kind=args.kind,
        applicability=_parse_applicability_args(args),
        epistemic_status=args.epistemic_status,
        criticality=args.criticality,
        relations=_parse_relation_args(args.relation),
    )
    print(f"proposed: {obj['id']}  {obj['title']!r}  [{obj['kind']}]")
    print(f"  applicability: {obj['applicability'] or '(unconditional under this anchor)'}")
    print(f"  epistemic_status: {obj['epistemic_status']}  criticality: {obj['criticality']}")
    if obj["relations"]:
        print(f"  relations: {obj['relations']}")
    print(f"next: orcan context assert accept --project {project_path} {obj['id']}  (or reject)")


def cmd_list(args: argparse.Namespace) -> None:
    project_path = _resolve_project(args.project)
    items = list_objects(project_path, status=args.status)
    if not items:
        print("(no context assertions)")
        return
    for item in items:
        print(
            f"  {item['id']}  [{item['status']:9}] ({item['kind']:6}) "
            f"{item.get('epistemic_status', 'fact'):13} {item['title']}"
        )


def cmd_show(args: argparse.Namespace) -> None:
    project_path = _resolve_project(args.project)
    print(json.dumps(get_object(project_path, args.id), indent=2, sort_keys=True))


def cmd_accept(args: argparse.Namespace) -> None:
    project_path = _resolve_project(args.project)
    edited_content = _read_content(args.edit_content) if args.edit_content else ""
    applicability = _parse_applicability_args(args) if args.override_applicability else None
    relations = _parse_relation_args(args.relation) if args.relation else None
    obj = accept(
        project_path,
        args.id,
        edited_content=edited_content,
        edited_justification=args.edit_justification,
        edited_applicability=applicability,
        edited_epistemic_status=args.epistemic_status,
        edited_criticality=args.criticality,
        edited_relations=relations,
    )
    print(f"accepted: {obj['id']}  {obj['title']!r}")
    print(f"  applicability: {obj['applicability'] or '(unconditional under this anchor)'}")
    print(f"  epistemic_status: {obj['epistemic_status']}  criticality: {obj['criticality']}")


def cmd_reject(args: argparse.Namespace) -> None:
    project_path = _resolve_project(args.project)
    obj = reject(project_path, args.id)
    print(f"rejected: {obj['id']}  {obj['title']!r}")


def cmd_retire(args: argparse.Namespace) -> None:
    project_path = _resolve_project(args.project)
    obj = retire(project_path, args.id)
    print(f"retired: {obj['id']}  {obj['title']!r}")


def cmd_select(args: argparse.Namespace) -> None:
    projects = [{"name": Path(p).name, "path": p} for p in args.project]
    items = select_for_workspace(args.workspace, projects, limit=args.limit)
    if not items:
        print("(no accepted assertions match this signature)")
        return
    for item in items:
        print(f"  {item['id']}  {item['title']}  — {', '.join(item['justification_trail'])}")


def cmd_root(_args: argparse.Namespace) -> None:
    print(store_root(ensure=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_propose = sub.add_parser("propose", help="Reflection: draft a candidate assertion (status: proposed)")
    p_propose.add_argument("--project", required=True)
    p_propose.add_argument("--file", default="", help="Read content from a file ('-' for stdin)")
    p_propose.add_argument("--text", default="")
    p_propose.add_argument("--title", default="")
    p_propose.add_argument("--kind", default="fact", help="Presentational label only: rule|fact|hint|policy|…")
    p_propose.add_argument("--justification", required=True, help="What problem this solves — required")
    _add_applicability_args(p_propose)
    _add_rfc0002_args(p_propose)
    p_propose.set_defaults(func=cmd_propose)

    p_list = sub.add_parser("list", help="List assertions anchored to a project")
    p_list.add_argument("--project", required=True)
    p_list.add_argument("--status", default="", choices=("", *STATUSES))
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show")
    p_show.add_argument("--project", required=True)
    p_show.add_argument("id")
    p_show.set_defaults(func=cmd_show)

    p_accept = sub.add_parser("accept", help="Review Gate: proposed -> accepted (never automatic)")
    p_accept.add_argument("--project", required=True)
    p_accept.add_argument("id")
    p_accept.add_argument("--edit-content", default="", help="Path to replacement content ('-' for stdin)")
    p_accept.add_argument("--edit-justification", default="")
    p_accept.add_argument(
        "--override-applicability",
        action="store_true",
        help="Replace applicability with the atoms given below (omit to keep the proposed predicate)",
    )
    _add_applicability_args(p_accept)
    _add_rfc0002_args(p_accept)
    p_accept.set_defaults(func=cmd_accept)

    p_reject = sub.add_parser("reject", help="Review Gate: proposed -> rejected")
    p_reject.add_argument("--project", required=True)
    p_reject.add_argument("id")
    p_reject.set_defaults(func=cmd_reject)

    p_retire = sub.add_parser("retire", help="accepted -> retired")
    p_retire.add_argument("--project", required=True)
    p_retire.add_argument("id")
    p_retire.set_defaults(func=cmd_retire)

    p_select = sub.add_parser("select", help="Applicability Layer: preview what a workspace would compile")
    p_select.add_argument("--workspace", required=True)
    p_select.add_argument("--project", action="append", default=[], required=True, help="Repeatable absolute project path")
    p_select.add_argument("--limit", type=int, default=20)
    p_select.set_defaults(func=cmd_select)

    p_root = sub.add_parser("root", help="Print $ORCAN_DATA/context")
    p_root.set_defaults(func=cmd_root)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
