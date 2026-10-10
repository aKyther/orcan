"""Read-only server inventory for explicit Studio removal actions."""

import json
import shutil
import subprocess


def run(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ValueError(result.stderr.strip() or "Server command failed")
    return result.stdout.strip()


def inventory():
    path = shutil.which("orcan")
    cli = {
        "path": path,
        "version": None,
        "removable": False,
        "reason": "Orcan CLI is not installed for this user.",
    }
    if path:
        try:
            cli["version"] = run([path, "version"])
            cli["removable"] = "--cli-only" in run([path, "uninstall", "--help"])
            cli["reason"] = (
                ""
                if cli["removable"]
                else "Update this CLI first: safe CLI-only removal is not supported by this version."
            )
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            cli["reason"] = str(error)
    images = []
    docker_error = None
    try:
        tags = run(
            [
                "docker",
                "image",
                "ls",
                "--filter",
                "label=org.opencontainers.image.title=Orcan",
                "--format",
                "{{.Repository}}:{{.Tag}}",
            ]
        )
        for tag in sorted(set(tags.splitlines())):
            if "<none>" in tag:
                continue
            image = json.loads(run(["docker", "image", "inspect", tag]))[0]
            users = run(
                [
                    "docker",
                    "container",
                    "ls",
                    "-a",
                    "--filter",
                    "ancestor=" + image["Id"],
                    "--format",
                    "{{.Names}}",
                ]
            )
            images.append(
                {
                    "image": tag,
                    "id": image["Id"],
                    "size": image["Size"],
                    "containers": users.splitlines(),
                }
            )
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        docker_error = str(error)
    return {"cli": cli, "images": images, "dockerError": docker_error}


if __name__ == "__main__":
    print(json.dumps(inventory()))
