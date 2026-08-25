import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PREVIEW = ROOT / "scripts" / "dev" / "orcan-preview"


class OrcanPreviewTests(unittest.TestCase):
    def fake_docker_env(
        self, tmp: str, *, project: str = "orcan-dev-ux", container_exists: bool = True,
    ) -> tuple[dict[str, str], Path]:
        fake_bin = Path(tmp) / "bin"
        fake_bin.mkdir()
        log = Path(tmp) / "docker.log"
        docker = fake_bin / "docker"
        docker.write_text(
            f"""#!/usr/bin/env bash
set -eu
printf '%s\\n' "$*" >>"{log}"
if [[ "${{1:-}}" == image && "${{2:-}}" == inspect ]]; then exit 0; fi
if [[ "${{1:-}}" == inspect && "${{2:-}}" == --format ]]; then
    if [[ "$3" == *com.docker.compose.project* ]]; then printf '%s\\n' "{project}";
    else printf 'healthy\\n'; fi
    exit 0
fi
if [[ "${{1:-}}" == inspect ]]; then exit {0 if container_exists else 1}; fi
exit 0
""",
            encoding="utf-8",
        )
        docker.chmod(0o755)
        env = {
            **os.environ,
            "PATH": f"{fake_bin}:{os.environ['PATH']}",
            "ORCAN_PREVIEW_DOCKER": str(docker),
            "ORCAN_PREVIEW_ROOT": str(Path(tmp) / "state"),
        }
        return env, log

    def run_preview(self, *args: str, **overrides: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            env = {**os.environ, "ORCAN_PREVIEW_ROOT": tmp, **overrides}
            return subprocess.run(
                [str(PREVIEW), *args], cwd=ROOT, env=env, check=False,
                text=True, capture_output=True, timeout=10,
            )

    def test_check_generates_an_isolated_preview_profile(self) -> None:
        result = self.run_preview("check")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("developer UX isolation check OK", result.stdout)

    def test_refuses_production_identifiers(self) -> None:
        cases = (
            {"ORCAN_PREVIEW_PROJECT": "orcan"},
            {"ORCAN_PREVIEW_INSTANCE": "1"},
            {"ORCAN_PREVIEW_IMAGE": "orcan:latest"},
            {"ORCAN_PREVIEW_PORT": "7681"},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                result = self.run_preview("check", **overrides)
                self.assertNotEqual(result.returncode, 0)

    def test_url_uses_the_configured_port(self) -> None:
        result = self.run_preview("url", ORCAN_PREVIEW_PORT="19001")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "http://127.0.0.1:19001")

    def test_check_accepts_isolated_custom_identifiers(self) -> None:
        result = self.run_preview(
            "check",
            ORCAN_PREVIEW_PROJECT="orcan-review-a",
            ORCAN_PREVIEW_INSTANCE="review-a",
            ORCAN_PREVIEW_IMAGE="orcan:review-a",
            ORCAN_PREVIEW_PORT="19001",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_help_documents_lifecycle_commands(self) -> None:
        result = self.run_preview("--help")
        self.assertEqual(result.returncode, 0, result.stderr)
        for command in (
            "start", "restart", "rebuild", "stop", "status", "url", "logs",
            "enter", "shell", "checklist", "doctor", "smoke", "reset", "check",
        ):
            self.assertIn(command, result.stdout)

    def test_checklist_covers_the_core_manual_flow(self) -> None:
        result = self.run_preview("checklist")
        self.assertEqual(result.returncode, 0, result.stderr)
        for expected in (
            "workspace list", "F2", "F4", "F1", "Ctrl+Space", "Alt+1", "resizing",
            "o turns automation", "browser refresh", "480x320", "make dev-a11y", "make dev-test",
        ):
            self.assertIn(expected, result.stdout)

    def test_settings_file_is_data_not_shell_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state"
            state.mkdir()
            marker = Path(tmp) / "executed"
            (state / "settings.env").write_text(
                f"ORCAN_PREVIEW_PORT=$(touch {marker})\nORCAN_PREVIEW_BIND=0.0.0.0\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [str(PREVIEW), "url"], cwd=ROOT,
                env={**os.environ, "ORCAN_PREVIEW_ROOT": str(state)},
                check=False, text=True, capture_output=True, timeout=10,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(marker.exists())

    def test_start_uses_only_the_developer_compose_project(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT, prefix=".dev-ux-test-") as tmp:
            env, log = self.fake_docker_env(tmp)
            result = subprocess.run(
                [str(PREVIEW), "start"], cwd=ROOT, env=env, check=False,
                text=True, capture_output=True, timeout=15,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = log.read_text(encoding="utf-8")
            self.assertIn("compose --project-name orcan-dev-ux", calls)
            self.assertNotIn("--project-name orcan ", calls)
            self.assertNotIn("build --tag", calls)

    def test_stop_falls_back_to_exact_verified_container(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT, prefix=".dev-ux-test-") as tmp:
            env, log = self.fake_docker_env(tmp)
            result = subprocess.run(
                [str(PREVIEW), "stop"], cwd=ROOT, env=env, check=False,
                text=True, capture_output=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = log.read_text(encoding="utf-8")
            self.assertIn("stop orcan-dev-ux", calls)
            self.assertIn("rm orcan-dev-ux", calls)
            self.assertNotIn("orcan-1", calls)

    def test_status_refuses_same_name_from_another_project(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT, prefix=".dev-ux-test-") as tmp:
            env, _ = self.fake_docker_env(tmp, project="foreign-project")
            result = subprocess.run(
                [str(PREVIEW), "status"], cwd=ROOT, env=env, check=False,
                text=True, capture_output=True, timeout=10,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("refusing to touch", result.stderr)

    def test_fixture_scenarios_are_validated_and_persisted(self) -> None:
        for scenario in ("empty", "busy", "errors", "long-names"):
            with self.subTest(scenario=scenario):
                result = self.run_preview("check", ORCAN_PREVIEW_SCENARIO=scenario)
                self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_preview("check", ORCAN_PREVIEW_SCENARIO="production")
        self.assertNotEqual(result.returncode, 0)

    def test_mutating_command_refuses_an_existing_operation_lock(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT, prefix=".dev-ux-test-") as tmp:
            env, _ = self.fake_docker_env(tmp)
            lock = Path(env["ORCAN_PREVIEW_ROOT"]) / "operation.lock"
            lock.mkdir(parents=True)
            (lock / "owner").write_text(f"{os.getpid()} restart\n", encoding="utf-8")
            result = subprocess.run(
                [str(PREVIEW), "start"], cwd=ROOT, env=env, check=False,
                text=True, capture_output=True, timeout=10,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("another preview operation", result.stderr)

    def test_start_automatically_chooses_a_free_default_port(self) -> None:
        import socket

        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            port = occupied.getsockname()[1]
            with tempfile.TemporaryDirectory(dir=ROOT, prefix=".dev-ux-test-") as tmp:
                env, _ = self.fake_docker_env(tmp, container_exists=False)
                state = Path(env["ORCAN_PREVIEW_ROOT"])
                state.mkdir()
                (state / "settings.env").write_text(
                    f"ORCAN_PREVIEW_PORT={port}\nORCAN_PREVIEW_BIND=127.0.0.1\n"
                    "ORCAN_PREVIEW_SCENARIO=busy\n",
                    encoding="utf-8",
                )
                result = subprocess.run(
                    [str(PREVIEW), "start"], cwd=ROOT, env=env, check=False,
                    text=True, capture_output=True, timeout=15,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"Port {port} is busy; selected", result.stdout)


if __name__ == "__main__":
    unittest.main()
