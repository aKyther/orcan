#!/usr/bin/env python3
"""Cockpit tmux nav chords — Ctrl/Alt+arrows focus; Ctrl+Shift+arrows split."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parents[2]
NAV_PATH = ROOT / "cockpit" / "src" / "orcan_cockpit" / "pty_tmux_nav.py"
KEYBINDINGS_PATH = ROOT / "docker" / "rootfs" / "etc" / "tmux" / "keybindings.conf"

_spec = importlib.util.spec_from_file_location("cockpit_pty_tmux_nav", NAV_PATH)
nav = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = nav
_spec.loader.exec_module(nav)


class NavActionTests(unittest.TestCase):
    def test_alt_arrows_focus_pane(self) -> None:
        for direction, flag in (
            ("left", "-L"),
            ("right", "-R"),
            ("up", "-U"),
            ("down", "-D"),
        ):
            self.assertEqual(nav.nav_action(f"alt+{direction}"), ("select-pane", flag))

    def test_ctrl_arrows_focus_pane(self) -> None:
        # Intentional cockpit mix: Alt often arrives as Ctrl, so both focus.
        for direction, flag in (
            ("left", "-L"),
            ("right", "-R"),
            ("up", "-U"),
            ("down", "-D"),
        ):
            self.assertEqual(nav.nav_action(f"ctrl+{direction}"), ("select-pane", flag))

    def test_ctrl_shift_arrows_split_pane(self) -> None:
        self.assertEqual(
            nav.nav_action("ctrl+shift+left"), ("split-window", "-h", "-b")
        )
        self.assertEqual(nav.nav_action("ctrl+shift+right"), ("split-window", "-h"))
        self.assertEqual(nav.nav_action("ctrl+shift+up"), ("split-window", "-v", "-b"))
        self.assertEqual(nav.nav_action("ctrl+shift+down"), ("split-window", "-v"))
        self.assertEqual(
            nav.nav_action("shift+ctrl+left"), ("split-window", "-h", "-b")
        )

    def test_non_nav_keys_untouched(self) -> None:
        self.assertIsNone(nav.nav_action("ctrl+space"))
        self.assertIsNone(nav.nav_action("alt+1"))
        self.assertIsNone(nav.nav_action("alt+ctrl+left"))
        self.assertIsNone(nav.nav_action("a"))

    def test_alt_focus_still_matches_keybindings_conf(self) -> None:
        """Alt focus matches conf; Ctrl/Ctrl+Shift diverge on purpose (cockpit mix)."""
        conf = KEYBINDINGS_PATH.read_text(encoding="utf-8")
        for direction, flag in (
            ("Left", "-L"),
            ("Right", "-R"),
            ("Up", "-U"),
            ("Down", "-D"),
        ):
            binding = f"bind -n M-{direction} select-pane {flag}"
            self.assertIn(binding, conf)
            self.assertEqual(
                nav.nav_action(f"alt+{direction.lower()}"),
                ("select-pane", flag),
            )
        # Conf still has Ctrl=split for raw --tmux; cockpit must NOT match that.
        self.assertIn("bind -n C-Left split-window -h -b", conf)
        self.assertNotEqual(
            nav.nav_action("ctrl+left"),
            ("split-window", "-h", "-b"),
        )


class EscFollowUpNavTests(unittest.TestCase):
    def test_bare_arrow_is_alt_arrow(self) -> None:
        self.assertEqual(nav.esc_follow_up_nav_key("left"), "alt+left")
        self.assertEqual(nav.esc_follow_up_nav_key("up"), "alt+up")

    def test_esc_ctrl_arrow_is_focus_not_split(self) -> None:
        self.assertEqual(nav.esc_follow_up_nav_key("ctrl+left"), "alt+left")
        self.assertEqual(nav.esc_follow_up_nav_key("ctrl+down"), "alt+down")

    def test_esc_ctrl_shift_not_nav_follow_up(self) -> None:
        self.assertIsNone(nav.esc_follow_up_nav_key("ctrl+shift+left"))

    def test_non_arrow_follow_ups_none(self) -> None:
        self.assertIsNone(nav.esc_follow_up_nav_key("c"))
        self.assertIsNone(nav.esc_follow_up_nav_key("3"))


class NavArgvTests(unittest.TestCase):
    def test_argv_targets_exact_session_active_pane(self) -> None:
        self.assertEqual(
            nav.nav_argv("orcan-dev", "alt+left"),
            ["tmux", "select-pane", "-L", "-t", "=orcan-dev:"],
        )
        self.assertEqual(
            nav.nav_argv("ws", "ctrl+down"),
            ["tmux", "select-pane", "-D", "-t", "=ws:"],
        )
        self.assertEqual(
            nav.nav_argv("ws", "ctrl+shift+down"),
            ["tmux", "split-window", "-v", "-t", "=ws:"],
        )


class RunNavTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_nav_invokes_tmux(self):
        process = SimpleNamespace(wait=mock.AsyncMock(return_value=0))
        with mock.patch.object(
            nav.asyncio,
            "create_subprocess_exec",
            new=mock.AsyncMock(return_value=process),
        ) as spawn:
            self.assertTrue(await nav.run_nav("orcan-dev", "alt+right"))
        spawn.assert_awaited_once_with(
            "tmux",
            "select-pane",
            "-R",
            "-t",
            "=orcan-dev:",
            stdout=nav.subprocess.DEVNULL,
            stderr=nav.subprocess.DEVNULL,
        )
        process.wait.assert_awaited_once()

    async def test_run_nav_skips_non_nav(self):
        with mock.patch.object(
            nav.asyncio, "create_subprocess_exec", new=mock.AsyncMock()
        ) as spawn:
            self.assertFalse(await nav.run_nav("orcan-dev", "ctrl+space"))
        spawn.assert_not_awaited()

    async def test_failed_command_is_reported(self):
        process = SimpleNamespace(wait=mock.AsyncMock(return_value=1))
        with mock.patch.object(
            nav.asyncio,
            "create_subprocess_exec",
            new=mock.AsyncMock(return_value=process),
        ):
            with self.assertRaises(nav.subprocess.CalledProcessError):
                await nav.run_nav("ws", "alt+left")

    def stalled_process(self):
        started = asyncio.Event()
        process = SimpleNamespace(returncode=None)

        async def wait():
            started.set()
            if process.returncode is None:
                await asyncio.Event().wait()
            return process.returncode

        process.wait = mock.AsyncMock(side_effect=wait)
        process.kill = mock.Mock(side_effect=lambda: setattr(process, "returncode", -9))
        return process, started

    async def test_timeout_kills_and_reaps_child(self):
        process, _ = self.stalled_process()
        with (
            mock.patch.object(
                nav.asyncio,
                "create_subprocess_exec",
                new=mock.AsyncMock(return_value=process),
            ),
            mock.patch.object(nav, "_NAV_TIMEOUT_S", 0.01),
        ):
            with self.assertRaises(TimeoutError):
                await nav.run_nav("ws", "alt+left")
        process.kill.assert_called_once()
        self.assertEqual(process.wait.await_count, 2)

    async def test_cancellation_kills_and_reaps_child(self):
        process, started = self.stalled_process()
        with mock.patch.object(
            nav.asyncio,
            "create_subprocess_exec",
            new=mock.AsyncMock(return_value=process),
        ):
            task = asyncio.create_task(nav.run_nav("ws", "alt+left"))
            await asyncio.wait_for(started.wait(), 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        process.kill.assert_called_once()
        self.assertEqual(process.wait.await_count, 2)


@pytest.mark.integration
class RealRunNavTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_and_cancel_reap_real_children(self):
        # Exercise process ownership without touching any real tmux session.
        real_spawn = asyncio.create_subprocess_exec
        for cancel in (False, True):
            with self.subTest(cancel=cancel):
                processes = []
                spawned = asyncio.Event()

                async def spawn(*args, **kwargs):
                    process = await real_spawn(*args, **kwargs)
                    processes.append(process)
                    spawned.set()
                    return process

                with (
                    mock.patch.object(
                        nav,
                        "nav_argv",
                        return_value=[
                            sys.executable,
                            "-c",
                            "import time; time.sleep(60)",
                        ],
                    ),
                    mock.patch.object(nav.asyncio, "create_subprocess_exec", new=spawn),
                    mock.patch.object(nav, "_NAV_TIMEOUT_S", 2 if cancel else 0.02),
                ):
                    task = asyncio.create_task(nav.run_nav("fixture", "alt+left"))
                    await asyncio.wait_for(spawned.wait(), 2)
                    if cancel:
                        task.cancel()
                    with self.assertRaises(
                        asyncio.CancelledError if cancel else TimeoutError
                    ):
                        await asyncio.wait_for(task, 3)
                self.assertIsNotNone(processes[0].returncode)
                self.assertNotEqual(processes[0].returncode, 0)


if __name__ == "__main__":
    unittest.main()
