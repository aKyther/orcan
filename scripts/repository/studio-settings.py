#!/usr/bin/env python3
"""Read-only settings snapshot and plan endpoint for Orcan Studio."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode", choices=("plan", "project-add-plan", "project-add-apply")
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--workspace")
    parser.add_argument("--project")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    path = Path(args.config).resolve()
    if not path.is_file():
        print(json.dumps({"ok": False, "error": "Orcan configuration does not exist"}))
        raise SystemExit(2)
    data = json.loads(path.read_text(encoding="utf-8"))
    workspaces = data.get("workspaces") or []
    if args.mode != "plan":
        if not args.workspace or not args.project:
            parser.error("--workspace and --project are required")
        project = Path(args.project).resolve()
        workspace = next(
            (item for item in workspaces if item.get("name") == args.workspace), None
        )
        blockers = []
        if workspace is None:
            blockers.append("workspace does not exist")
        if not project.is_dir() or not (project / ".git").exists():
            blockers.append("project is not a Git repository")
        if workspace and any(
            Path(item.get("path", "")).resolve() == project
            for item in workspace.get("projects") or []
        ):
            blockers.append("project is already attached")
        plan = {
            "operation": "project_add",
            "workspace": args.workspace,
            "project": str(project),
            "changes": [f"attach {project} to {args.workspace}", "run orcan sync"],
            "blockers": blockers,
            "ready": not blockers,
        }
        if args.mode == "project-add-plan":
            print(json.dumps({"ok": True, "plan": plan}, separators=(",", ":")))
            return
        if not args.yes or not plan["ready"]:
            print(
                json.dumps(
                    {"ok": False, "error": "apply requires --yes and a ready plan"}
                )
            )
            raise SystemExit(2)
        import subprocess

        result = subprocess.run(
            ["orcan", "context", "add", str(project), "--workspace", args.workspace],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": result.stderr.strip() or "context add failed",
                    }
                )
            )
            raise SystemExit(result.returncode)
        print(json.dumps({"ok": True, "result": plan}, separators=(",", ":")))
        return
    print(
        json.dumps(
            {
                "ok": True,
                "plan": {
                    "operation": "settings_snapshot",
                    "config": str(path),
                    "workspaces": workspaces,
                    "changes": [],
                    "blockers": [],
                    "ready": True,
                },
            },
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
