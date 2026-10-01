#!/usr/bin/env python3
"""Read-only settings snapshot and plan endpoint for Orcan Studio."""

from __future__ import annotations

import argparse
import json
import re
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
            "workspace-rename-plan",
            "workspace-rename-apply",
            "workspace-remove-plan",
            "workspace-remove-apply",
        ),
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--workspace")
    parser.add_argument("--project")
    parser.add_argument("--project-mode", choices=("git", "mount"), default="git")
    parser.add_argument("--new-name")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()
    path = Path(args.config).resolve()
    if not path.is_file():
        print(json.dumps({"ok": False, "error": "Orcan configuration does not exist"}))
        raise SystemExit(2)
    data = json.loads(path.read_text(encoding="utf-8"))
    workspaces = data.get("workspaces") or []
    if args.mode.startswith("workspace-"):
        if not args.workspace:
            parser.error("--workspace is required")
        workspace = next(
            (item for item in workspaces if item.get("name") == args.workspace), None
        )
        rename = args.mode.startswith("workspace-rename")
        new_name = (args.new_name or "").strip()
        blockers = []
        if workspace is None:
            blockers.append("workspace does not exist")
        if rename and not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", new_name):
            blockers.append(
                "new workspace name must use letters, digits, dots, hyphens, or underscores"
            )
        if rename and any(item.get("name") == new_name for item in workspaces):
            blockers.append("a workspace already has that name")
        if not rename and workspace and workspace.get("projects"):
            blockers.append("detach every project before removing this workspace")
        plan = {
            "operation": "workspace_rename" if rename else "workspace_remove",
            "workspace": args.workspace,
            "changes": [
                f"{'rename ' + args.workspace + ' to ' + new_name if rename else 'remove empty workspace ' + args.workspace}",
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
        if rename:
            workspace["name"] = new_name
        else:
            workspaces.remove(workspace)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
        print(json.dumps({"ok": True, "result": plan}, separators=(",", ":")))
        return
    if args.mode != "plan":
        if not args.workspace or not args.project:
            parser.error("--workspace and --project are required")
        project = Path(args.project).resolve()
        workspace = next(
            (item for item in workspaces if item.get("name") == args.workspace), None
        )
        blockers = []
        detach = args.mode.startswith("project-detach")
        # `orcan context add` creates a missing workspace, so only detach needs one.
        if workspace is None and detach:
            blockers.append("workspace does not exist")
        if not detach and not project.is_dir():
            blockers.append("project directory does not exist")
        if (
            not detach
            and args.project_mode == "git"
            and not (project / ".git").exists()
        ):
            blockers.append("project is not a Git repository; choose mount as-is")
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
            "project_mode": args.project_mode,
            "creates_workspace": workspace is None and not detach,
            "changes": (
                [f"create workspace {args.workspace}"]
                if workspace is None and not detach
                else []
            )
            + [
                f"{'detach' if detach else 'attach'} {project} {'from' if detach else 'to'} {args.workspace}",
                *(
                    []
                    if detach
                    else [
                        "use Git directory"
                        if args.project_mode == "git"
                        else "mount directory as-is"
                    ]
                ),
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
