#!/usr/bin/env python3
"""OSC 8 / plain URL helpers for the embedded cockpit terminal."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
LINKS_PATH = ROOT / "cockpit" / "src" / "orcan_cockpit" / "pty_links.py"

_spec = importlib.util.spec_from_file_location("cockpit_pty_links", LINKS_PATH)
links = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = links
_spec.loader.exec_module(links)


class SplitOsc8Tests(unittest.TestCase):
    def test_plain_text_unchanged(self) -> None:
        self.assertEqual(links.split_osc8("hello"), [("hello", None)])

    def test_strips_osc8_and_reports_href(self) -> None:
        text = "see \x1b]8;;https://ex.com\x1b\\docs\x1b]8;;\x1b\\ now"
        parts = links.split_osc8(text)
        self.assertEqual(
            parts,
            [
                ("see ", None),
                ("", "https://ex.com"),
                ("docs", None),
                ("", ""),
                (" now", None),
            ],
        )

    def test_bel_terminated_osc8_is_supported(self) -> None:
        self.assertEqual(
            links.split_osc8("\x1b]8;;https://ex.com\x07docs\x1b]8;;\x07"),
            [("", "https://ex.com"), ("docs", None), ("", "")],
        )


class PlainUrlAtTests(unittest.TestCase):
    def test_finds_url_under_column(self) -> None:
        line = "go https://example.com/a and back"
        self.assertEqual(links.plain_url_at(line, 1), None)
        self.assertEqual(links.plain_url_at(line, 10), "https://example.com/a")
        self.assertEqual(links.plain_url_at(line, 23), "https://example.com/a")

    def test_trims_trailing_punctuation(self) -> None:
        line = "see https://example.com)."
        self.assertEqual(links.plain_url_at(line, 10), "https://example.com")

    def test_allows_click_on_url_at_end_of_line(self) -> None:
        line = "https://example.com"
        self.assertEqual(links.plain_url_at(line, len(line)), line)
        self.assertIsNone(links.plain_url_at(line, len(line) + 1))

    def test_annotates_only_empty_cells(self) -> None:
        line = "go https://example.com now"
        hrefs = ["existing" if index == 3 else None for index in range(len(line))]
        links.annotate_plain_urls(hrefs, line)
        self.assertEqual(hrefs[3], "existing")
        self.assertEqual(hrefs[4], "https://example.com")


class OpenUrlTests(unittest.TestCase):
    def test_rejects_non_http(self) -> None:
        self.assertFalse(links.open_url("javascript:alert(1)"))
        self.assertFalse(links.open_url("file:///etc/passwd"))

    def test_opens_https(self) -> None:
        with mock.patch.object(links.webbrowser, "open", return_value=True) as open_:
            self.assertTrue(links.open_url("https://example.com"))
            open_.assert_called_once_with("https://example.com")

    def test_falls_back_to_xdg_open(self) -> None:
        with mock.patch.object(links.webbrowser, "open", return_value=False):
            with mock.patch("subprocess.run") as run:
                run.return_value = mock.Mock(returncode=0)
                self.assertTrue(links.open_url("https://example.com"))
        run.assert_called_once_with(
            ("xdg-open", "https://example.com"),
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )

    def test_all_openers_failing_returns_false(self) -> None:
        with mock.patch.object(links.webbrowser, "open", return_value=False):
            with mock.patch("subprocess.run", side_effect=OSError("not installed")):
                self.assertFalse(links.open_url("https://example.com"))


class HyperlinkScreenTests(unittest.TestCase):
    def test_osc8_stamps_cells_and_clears(self) -> None:
        try:
            HyperlinkScreen, Stream = links.attach_hyperlink_screen()
        except ImportError:
            self.skipTest("pyte not installed on host")
        screen = HyperlinkScreen(40, 5)
        stream = Stream(screen)
        links.feed_with_osc8(
            stream,
            screen,
            "\x1b]8;;https://ex.com/x\x1b\\LINK\x1b]8;;\x1b\\!",
        )
        self.assertEqual(screen.link_at(0, 0), "https://ex.com/x")
        self.assertEqual(screen.link_at(3, 0), "https://ex.com/x")
        self.assertIsNone(screen.link_at(4, 0))  # "!" after close
        self.assertEqual(links.url_at_screen(screen, 1, 0), "https://ex.com/x")


if __name__ == "__main__":
    unittest.main()
