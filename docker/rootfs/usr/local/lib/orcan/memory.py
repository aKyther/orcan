"""Small explicit project/workspace knowledge, selective retrieval and handoff recaps.

Only content deliberately supplied to this command is indexed. No chat transcripts,
repository scan, external model or background agent is involved.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import subprocess
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from orcan import compact

MAX_NOTES = 200
MAX_TEXT = 8000


@contextmanager
def database(root: Path):
    directory = root / ".orcan/memory"
    if (root / ".orcan").is_symlink() or directory.is_symlink():
        raise ValueError("Refusing a symlinked memory directory")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / "notes.sqlite"
    if path.is_symlink():
        raise ValueError("Refusing a symlinked memory database")
    db = sqlite3.connect(path, timeout=3)
    db.row_factory = sqlite3.Row
    try:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY,title TEXT NOT NULL,text TEXT NOT NULL,tags TEXT NOT NULL,sources TEXT NOT NULL,updated TEXT NOT NULL,sha256 TEXT NOT NULL);
        CREATE VIRTUAL TABLE IF NOT EXISTS note_search USING fts5(id UNINDEXED,title,tags,text,tokenize='unicode61 remove_diacritics 2');
        """)
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def remember(
    root: Path,
    identifier: str,
    title: str,
    text: str,
    tags: list[str],
    sources: list[str],
    expected: str | None = None,
) -> dict:
    if (
        not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", identifier)
        or not 1 <= len(title) <= 160
        or not text.strip()
        or len(text.encode()) > MAX_TEXT
    ):
        raise ValueError(
            "Use an id, title <=160 characters and nonempty text <=8000 UTF-8 bytes"
        )
    if (
        len(tags) > 10
        or any(len(tag) > 32 for tag in tags)
        or len(sources) > 5
        or any(len(source) > 300 for source in sources)
    ):
        raise ValueError("Too many or oversized tags/sources")
    payload = {"title": title, "text": text, "tags": tags, "sources": sources}
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    with database(root) as db:
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute(
            "SELECT sha256 FROM notes WHERE id=?", (identifier,)
        ).fetchone()
        if previous and previous["sha256"] != expected:
            raise ValueError(
                "Note exists or changed; show it and pass --expected-sha256 to update"
            )
        if not previous and expected:
            raise ValueError("Expected note is missing")
        if (
            not previous
            and db.execute("SELECT COUNT(*) FROM notes").fetchone()[0] >= MAX_NOTES
        ):
            raise ValueError(
                "Memory note limit reached (200); consolidate existing notes"
            )
        db.execute(
            "INSERT OR REPLACE INTO notes VALUES(?,?,?,?,?,?,?)",
            (
                identifier,
                title,
                text,
                json.dumps(tags),
                json.dumps(sources),
                datetime.now(UTC).isoformat(),
                digest,
            ),
        )
        db.execute("DELETE FROM note_search WHERE id=?", (identifier,))
        db.execute(
            "INSERT INTO note_search VALUES(?,?,?,?)",
            (identifier, title, " ".join([*tags, *sources]), text),
        )
    return {"id": identifier, "sha256": digest, "bytes": len(text.encode())}


def show(root: Path, identifier: str) -> dict:
    with database(root) as db:
        row = db.execute("SELECT * FROM notes WHERE id=?", (identifier,)).fetchone()
    if row is None:
        raise ValueError("Unknown note")
    result = dict(row)
    result["tags"] = json.loads(result["tags"])
    result["sources"] = json.loads(result["sources"])
    return result


def search(root: Path, query: str, limit: int = 3, budget: int = 3000) -> dict:
    if not 1 <= limit <= 10 or not 512 <= budget <= 12000 or len(query) > 500:
        raise ValueError(
            "Use limit 1..10, budget 512..12000 bytes and query <=500 characters"
        )
    tokens = re.findall(r"\w+", query.lower())[:20]
    if not tokens:
        return {"matches": [], "truncated": False}
    expression = " OR ".join('"' + token + '"*' for token in tokens)
    with database(root) as db:
        rows = db.execute(
            """SELECT n.id,n.title,n.sources,n.sha256,n.updated,snippet(note_search,3,'','',' … ',48) AS excerpt,bm25(note_search,0,4,3,1) AS rank
        FROM note_search JOIN notes n ON n.id=note_search.id WHERE note_search MATCH ? ORDER BY rank,n.id LIMIT ?""",
            (expression, limit + 1),
        ).fetchall()
    result = {"matches": [], "truncated": len(rows) > limit}
    for row in rows[:limit]:
        value = dict(row)
        value.pop("rank")
        value["sources"] = json.loads(value["sources"])
        value["excerpt"] = value["excerpt"][:800]
        candidate = {**result, "matches": result["matches"] + [value]}
        if len(json.dumps(candidate, ensure_ascii=False).encode()) > budget - 30:
            result["truncated"] = True
            break
        result["matches"].append(value)
    return result


def project_store(project: Path) -> Path:
    """Git-common storage survives task-branch/worktree removal."""
    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(project),
                "rev-parse",
                "--path-format=absolute",
                "--git-common-dir",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return project
    return Path(result.stdout.strip()).resolve() if result.returncode == 0 else project


def forget(root: Path, identifier: str, expected: str) -> dict:
    with database(root) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT sha256 FROM notes WHERE id=?", (identifier,)
        ).fetchone()
        if row is None or row["sha256"] != expected:
            raise ValueError(
                "Note missing or changed; inspect its current SHA before removal"
            )
        db.execute("DELETE FROM notes WHERE id=?", (identifier,))
        db.execute("DELETE FROM note_search WHERE id=?", (identifier,))
    return {"removed": identifier}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace", help="Workspace root; defaults to nearest manifest"
    )
    parser.add_argument(
        "--project", type=Path, help="Explicit project scope instead of workspace"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    put = commands.add_parser(
        "remember", help="Save explicit durable knowledge; no filesystem crawling"
    )
    put.add_argument("id")
    put.add_argument("--title", required=True)
    put.add_argument("--text", required=True)
    put.add_argument("--tag", action="append", default=[])
    put.add_argument("--source", action="append", default=[])
    put.add_argument("--expected-sha256")
    find = commands.add_parser(
        "search", help="Return only relevant, bounded excerpts and sources"
    )
    find.add_argument("query")
    find.add_argument("--limit", type=int, default=3)
    find.add_argument("--budget", type=int, default=3000)
    get = commands.add_parser(
        "show", help="Read one explicitly selected note, <=8000 text bytes"
    )
    get.add_argument("id")
    recap = commands.add_parser(
        "recap", help="Install agent-written handoff using the existing brief/archive"
    )
    recap.add_argument("--file", type=Path, required=True)
    recap.add_argument("--expected-sha256")
    remove = commands.add_parser(
        "forget", help="Remove one explicitly identified note and its search entry"
    )
    remove.add_argument("id")
    remove.add_argument("--expected-sha256", required=True)
    commands.add_parser(
        "status", help="Report bounded store size/count, without loading notes"
    )
    args = parser.parse_args(argv)
    try:
        if args.project and args.workspace:
            raise ValueError("Choose a project or a workspace")
        root = (
            args.project.resolve()
            if args.project
            else compact.workspace_root(args.workspace)
        )
        if not root.is_dir():
            raise ValueError("Scope directory is missing")
        if args.project:
            if args.command == "recap":
                raise ValueError(
                    "Recaps belong to workspace scope; project memory stores durable knowledge"
                )
            root = project_store(root)
        if args.command == "status":
            with database(root) as db:
                row = db.execute(
                    "SELECT COUNT(*),COALESCE(SUM(length(CAST(text AS BLOB))),0) FROM notes"
                ).fetchone()
            result = {
                "notes": row[0],
                "text_bytes": row[1],
                "limit": MAX_NOTES,
                "store": str(root / ".orcan/memory"),
            }
        elif args.command == "forget":
            result = forget(root, args.id, args.expected_sha256)
        elif args.command == "remember":
            result = remember(
                root,
                args.id,
                args.title,
                args.text,
                args.tag,
                args.source,
                args.expected_sha256,
            )
        elif args.command == "search":
            result = search(root, args.query, args.limit, args.budget)
        elif args.command == "show":
            result = show(root, args.id)
        else:
            current = compact.check(root)
            if current.get("exists") and not args.expected_sha256:
                raise ValueError(
                    "Existing brief: inspect orcan compact --check and pass --expected-sha256"
                )
            compact.brief_path(root).parent.mkdir(exist_ok=True, mode=0o700)
            expected = args.expected_sha256 or hashlib.sha256(b"").hexdigest()
            result = compact.apply(root, args.file, expected, require_smaller=False)
    except (ValueError, OSError, sqlite3.Error) as error:
        print(json.dumps({"error": type(error).__name__, "message": str(error)[:300]}))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0
