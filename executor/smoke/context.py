"""Isolated agent-context matrix and real conditional-layer checks (small fixtures)."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / ".orcan-test.agent-context"
PROGRAM = r"""
import json, os, subprocess, sys
from pathlib import Path
sys.path.insert(0, '/usr/local/lib')
from orcan.reconcile import apply_workspaces
root = Path('/tmp/agent-context')
root.mkdir()
home = root / 'home'
home.mkdir()
os.environ['HOME'] = str(home)
selected = os.environ['SELECTED'].split('+')
manifest = root / 'agents.json'
manifest.write_text(json.dumps({'agents': {name: 1 for name in selected}}))
os.environ['ORCAN_AGENTS_FILE'] = str(manifest)
for command in ['init-cursor-home', 'init-claude-home', 'init-ai-statusline']:
    subprocess.run([command], check=True, stdout=subprocess.DEVNULL)
subprocess.run(['bash', '-c', 'source /usr/local/bin/docker-entrypoint; persist_claude_config; run_init; run_init_claude_home; run_init_ai_statusline; ensure_orcan_home_map'], check=True, stdout=subprocess.DEVNULL)
links = {path.name for path in (home / 'orcan-map/agents').iterdir()}
expected = set(selected) | ({'cursor-app'} if 'cursor' in selected else set())
assert links == expected
project = root / 'project' 
project.mkdir()
subprocess.run(['orcan-init-project', str(project)], check=True, stdout=subprocess.DEVNULL)
workspace = root / 'workspaces/demo'
apply_workspaces({'workspaces':[{'name':'demo','root':str(workspace),'projects':[]}]}, workspaces_parent=root / 'workspaces')
for path in [project, workspace]:
    assert (path / 'AGENTS.md').is_file()
    assert (path / 'CLAUDE.md').is_file() == ('claude' in selected)
    assert (path / '.claudeignore').is_file() == ('claude' in selected)
    assert (path / '.cursorignore').is_file() == ('cursor' in selected)
assert (home / '.claude/settings.json').exists() == ('claude' in selected)
assert (home / '.cursor').exists() == ('cursor' in selected)
print(json.dumps({'agents':selected,'status':'passed'}))
"""


def run(argv, **kwargs):
    return subprocess.run(argv, check=True, text=True, **kwargs)


def main():
    STATE.mkdir(exist_ok=True)
    context_image = "orcan:agent-context-smoke"
    images = [context_image, "orcan:tool-profile-on-smoke", "orcan:tool-profile-off-smoke"]
    for image in images:
        if (
            subprocess.run(
                ["docker", "image", "inspect", image], check=False, capture_output=True
            ).returncode
            == 0
        ):
            raise RuntimeError("Refusing to replace an existing fixture image: " + image)
    try:
        with (STATE / "build.log").open("w") as log:
            run(
                [
                    "docker",
                    "build",
                    "-t",
                    context_image,
                    "-f",
                    "executor/smoke/context.Dockerfile",
                    ".",
                ],
                cwd=ROOT,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        for selected in ["codex", "claude", "cursor", "cursor+claude", "gemini+copilot"]:
            result = run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-i",
                    "--network",
                    "none",
                    "-e",
                    "SELECTED=" + selected,
                    context_image,
                    "python3",
                    "-",
                ],
                input=PROGRAM,
                capture_output=True,
            )
            assert json.loads(result.stdout)["status"] == "passed"
        # Use the exact production conditional RUN block with small fake stage
        # contents, so the test checks layers without downloading full toolchains.
        context = STATE / "tools-context"
        for name in ["go", "cargo", "rustup"]:
            (context / name).mkdir(parents=True, exist_ok=True)
            (context / name / "tool-fixture").write_bytes(b"fixture\n" * (512 * 1024))
        source = (ROOT / "Dockerfile").read_text()
        block = source.split("ARG INSTALL_GO=1", 1)[1].split("COPY --from=uv-tools", 1)[0]
        dockerfile = (
            "# syntax=docker/dockerfile:1.7\nFROM scratch AS go-tools\nCOPY go/ /usr/local/go/\nFROM scratch AS rust-tools\nCOPY cargo/ /usr/local/cargo/\nCOPY rustup/ /usr/local/rustup/\nFROM debian:bookworm-slim\nARG INSTALL_GO=1"
            + block
        )
        (context / "Dockerfile").write_text(dockerfile)
        sizes = {}
        with (STATE / "tool-build.log").open("w") as log:
            for flag, tag in [("1", images[1]), ("0", images[2])]:
                run(
                    [
                        "docker",
                        "build",
                        "--build-arg",
                        "INSTALL_GO=" + flag,
                        "--build-arg",
                        "INSTALL_RUST=" + flag,
                        "-t",
                        tag,
                        str(context),
                    ],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                comparison = "-f" if flag == "1" else "! -e"
                script = f"test {comparison} /usr/local/go/tool-fixture && test {comparison} /usr/local/cargo/tool-fixture && test {comparison} /usr/local/rustup/tool-fixture"
                run(
                    ["docker", "run", "--rm", "--network", "none", tag, "sh", "-c", script],
                    capture_output=True,
                )
                sizes[flag] = int(
                    run(
                        ["docker", "image", "inspect", "--format", "{{.Size}}", tag],
                        capture_output=True,
                    ).stdout
                )
        assert sizes["1"] > sizes["0"] + 10_000_000
        report = {
            "status": "passed",
            "agent_combinations": 5,
            "global_settings_and_project_seeds": True,
            "disabled_tool_files_absent": True,
            "fixture_layer_bytes_avoided": sizes["1"] - sizes["0"],
            "actual_toolchain_size_not_measured": True,
        }
        (STATE / "report.json").write_text(json.dumps(report, indent=2))
        print(json.dumps(report))
    finally:
        for image in images:
            subprocess.run(["docker", "image", "rm", image], check=False, capture_output=True)


if __name__ == "__main__":
    main()
