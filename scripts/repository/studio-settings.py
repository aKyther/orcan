#!/usr/bin/env python3
"""Read-only settings snapshot and plan endpoint for Orcan Studio."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "mode",
        choices=(
            "plan",
            "project-add-plan",
            "project-add-apply",
            "project-detach-plan",
            "project-detach-apply",
        ),
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
        detach = args.mode.startswith("project-detach")
        if not detach and (not project.is_dir() or not (project / ".git").exists()):
            blockers.append("project is not a Git repository")
        attached = workspace and any(
            Path(item.get("path", "")).resolve() == project
            for item in workspace.get("projects") or []
        )
        if not detach and attached:
            blockers.append("project is already attached")
        if detach and not attached:
            blockers.append("project is not attached to this workspace")
        plan = {
            "operation": "project_detach" if detach else "project_add",
            "workspace": args.workspace,
            "project": str(project),
            "changes": [
                f"{'detach' if detach else 'attach'} {project} {'from' if detach else 'to'} {args.workspace}",
                "run orcan sync",
            ],
            "blockers": blockers,
            "ready": not blockers,
        }
        if args.mode.endswith("-plan"):
            print(json.dumps({"ok": True, "plan": plan}, separators=(",", ":")))
            return
        if not args.yes or not plan["ready"]:
            print(
                json.dumps(
                    {"ok": False, "error": "apply requires --yes and a ready plan"}
                )
            )
            raise SystemExit(2)
        if detach:
            workspace["projects"] = [
                item
                for item in workspace.get("projects") or []
                if Path(item.get("path", "")).resolve() != project
            ]
            temporary = path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
            temporary.replace(path)
            print(json.dumps({"ok": True, "result": plan}, separators=(",", ":")))
            return

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
