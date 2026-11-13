#!/usr/bin/env python3
"""OSC 8 / plain URL helpers for the embedded cockpit terminal."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import pytest

pytestmark = pytest.mark.integration

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


class OscFramingTests(unittest.TestCase):
    def fixture(self):
        from types import SimpleNamespace

        return SimpleNamespace(feed=mock.Mock()), SimpleNamespace(active_href=None)

    def test_every_split_preserves_link_and_clipboard_in_order(self):
        payload = "before\x1b]8;;https://ex.com\x1b\\LINK\x1b]8;;\x07after\x1b]52;c;aGk=\x1b\\end"
        for split in range(len(payload) + 1):
            with self.subTest(split=split):
                stream, screen = self.fixture()
                seen = []
                stream.feed.side_effect = lambda text: seen.append(
                    (text, screen.active_href)
                )
                clips = []
                links.feed_with_osc8(stream, screen, payload[:split], clips.append)
                links.feed_with_osc8(stream, screen, payload[split:], clips.append)
                self.assertEqual(
                    "".join(text for text, _ in seen), "beforeLINKafterend"
                )
                self.assertEqual("".join(text for text, href in seen if href), "LINK")
                self.assertIsNone(screen.active_href)
                self.assertEqual(clips, ["hi"])

    def test_bytewise_sequences_and_other_escape_codes(self):
        stream, screen = self.fixture()
        seen = []
        stream.feed.side_effect = seen.append
        clips = []
        payload = "\x1b[31mA\x1b]0;title\x07B\x1b]52;c;aGk=\x07C"
        for char in payload:
            links.feed_with_osc8(stream, screen, char, clips.append)
        self.assertEqual("".join(seen), "\x1b[31mA\x1b]0;title\x07BC")
        self.assertEqual(clips, ["hi"])

    def test_oversized_osc_is_bounded_and_recovers_after_terminator(self):
        stream, screen = self.fixture()
        clips = []
        with mock.patch.object(links, "_OSC_MAX_CHARS", 64):
            links.feed_with_osc8(stream, screen, "\x1b]52;c;", clips.append)
            for _ in range(20):
                links.feed_with_osc8(stream, screen, "x" * 64, clips.append)
                self.assertLessEqual(sum(map(len, stream._orcan_osc_filter._parts)), 64)
            links.feed_with_osc8(stream, screen, "\x1b", clips.append)
            links.feed_with_osc8(stream, screen, "\\OK\x1b]52;c;aGk=\x07", clips.append)
        self.assertEqual(clips, ["hi"])
        self.assertEqual(
            "".join(call.args[0] for call in stream.feed.call_args_list), "OK"
        )

    def test_maximum_clipboard_payload_is_accepted_but_larger_is_dropped(self):
        import base64

        stream, screen = self.fixture()
        clips = []
        payload = base64.b64encode(b"x" * links._OSC52_MAX_DECODED).decode()
        sequence = "\x1b]52;c;" + payload + "\x07"
        for start in range(0, len(sequence), 4096):
            links.feed_with_osc8(
                stream, screen, sequence[start : start + 4096], clips.append
            )
        self.assertEqual(len(clips), 1)
        self.assertEqual(len(clips[0]), links._OSC52_MAX_DECODED)
        payload = base64.b64encode(b"x" * (links._OSC52_MAX_DECODED + 1)).decode()
        links.feed_with_osc8(
            stream, screen, "\x1b]52;c;" + payload + "\x07", clips.append
        )
        self.assertEqual(len(clips), 1)

    def test_cancelled_sequences_do_not_change_link_or_clipboard(self):
        for cancel in ("\x18", "\x1a"):
            stream, screen = self.fixture()
            clips = []
            links.feed_with_osc8(
                stream,
                screen,
                "\x1b]8;;https://bad.example" + cancel + "OK",
                clips.append,
            )
            self.assertIsNone(screen.active_href)
            stream.feed.assert_called_once_with("OK")
            self.assertEqual(clips, [])

    def test_c1_osc_and_st_are_supported(self):
        stream, screen = self.fixture()
        links.feed_with_osc8(stream, screen, "\x9d8;;https://ex.com\x9cX")
        self.assertEqual(screen.active_href, "https://ex.com")
        stream.feed.assert_called_once_with("X")

    def test_failed_clipboard_callback_does_not_trap_later_output(self):
        stream, screen = self.fixture()
        with self.assertRaises(RuntimeError):
            links.feed_with_osc8(
                stream,
                screen,
                "\x1b]52;c;aGk=\x07",
                mock.Mock(side_effect=RuntimeError),
            )
        links.feed_with_osc8(stream, screen, "next")
        stream.feed.assert_called_once_with("next")

    def test_streams_do_not_share_pending_sequences(self):
        stream, screen = self.fixture()
        other, other_screen = self.fixture()
        links.feed_with_osc8(stream, screen, "\x1b]8;;https://ex.com")
        links.feed_with_osc8(other, other_screen, "plain")
        other.feed.assert_called_once_with("plain")
        self.assertIsNone(other_screen.active_href)


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


class ScreenLookupTests(unittest.TestCase):
    class _Cell:
        def __init__(self, data: str) -> None:
            self.data = data

    class _Screen:
        lines = 2
        columns = 24

        def __init__(self, text: str, href: str | None = None) -> None:
            padded = text.ljust(self.columns)
            self.buffer = {
                0: [ScreenLookupTests._Cell(char) for char in padded],
                1: [ScreenLookupTests._Cell(" ") for _ in range(self.columns)],
            }
            self.href = href

        def link_at(self, column: int, row: int) -> str | None:
            return self.href if row == 0 and column == 5 else None

    def test_line_from_screen_is_safe_outside_visible_rows(self) -> None:
        screen = self._Screen("hello")
        self.assertEqual(links.line_from_screen(screen, -1), "")
        self.assertEqual(links.line_from_screen(screen, 2), "")
        self.assertTrue(links.line_from_screen(screen, 0).startswith("hello"))

    def test_osc8_link_wins_over_plain_url_fallback(self) -> None:
        screen = self._Screen("go https://plain.example", "https://osc.example")
        self.assertEqual(links.url_at_screen(screen, 5, 0), "https://osc.example")

    def test_plain_url_lookup_uses_screen_text_when_no_osc8_link(self) -> None:
        screen = self._Screen("go https://plain.example")
        self.assertEqual(
            links.url_at_screen(screen, 8, 0),
            "https://plain.example",
        )
        self.assertIsNone(links.url_at_screen(screen, 0, 1))


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


class HyperlinkMutationTests(unittest.TestCase):
    def setUp(self):
        try:
            Screen, Stream = links.attach_hyperlink_screen()
        except ImportError:
            self.skipTest("pyte not installed on host")
        self.screen = Screen(12, 4)
        self.stream = Stream(self.screen)

    def feed(self, text):
        links.feed_with_osc8(self.stream, self.screen, text)

    def linked(self, text, href="https://ex.com"):
        self.feed("\x1b]8;;" + href + "\x1b\\" + text + "\x1b]8;;\x1b\\")

    def test_plain_overwrite_clears_link(self):
        self.linked("old")
        self.feed("\rnew")
        self.assertEqual(self.screen.display[0].rstrip(), "new")
        self.assertIsNone(links.url_at_screen(self.screen, 0, 0))

    def test_link_wraps_with_wide_glyph_and_keeps_cursor_attrs_clean(self):
        self.feed("123456789012")
        self.linked("界x")
        self.assertEqual(self.screen.display[1].rstrip(), "界x")
        for column in range(3):
            self.assertEqual(self.screen.link_at(column, 1), "https://ex.com")
        self.assertIsNone(getattr(self.screen.cursor.attrs, "href", None))

    def test_link_keeps_graphic_attributes_across_sgr_resets(self):
        self.feed("\x1b]8;;https://ex.com\x07\x1b[31;1mA\x1b[0mB\x1b]8;;\x07C")
        self.assertEqual(self.screen.buffer[0][0].fg, "red")
        self.assertTrue(self.screen.buffer[0][0].bold)
        self.assertEqual(self.screen.buffer[0][1].fg, "default")
        self.assertEqual(self.screen.link_at(0, 0), "https://ex.com")
        self.assertEqual(self.screen.link_at(1, 0), "https://ex.com")
        self.assertIsNone(self.screen.link_at(2, 0))

    def test_insert_delete_and_erase_characters_move_links_with_text(self):
        self.linked("ABC")
        self.feed("\r\x1b[@")
        self.assertIsNone(self.screen.link_at(0, 0))
        self.assertEqual(self.screen.link_at(1, 0), "https://ex.com")
        self.feed("\x1b[P")
        self.assertEqual(self.screen.display[0].rstrip(), "ABC")
        self.assertEqual(self.screen.link_at(0, 0), "https://ex.com")
        self.feed("\x1b[X")
        self.assertIsNone(self.screen.link_at(0, 0))
        self.assertEqual(self.screen.link_at(1, 0), "https://ex.com")

    def test_partial_scroll_region_ind_and_reverse_index(self):
        self.feed("\x1b[1;1H")
        self.linked("TOP", "https://top.example")
        self.feed("\x1b[2;1H")
        self.linked("AAA", "https://a.example")
        self.feed("\x1b[3;1H")
        self.linked("BBB", "https://b.example")
        self.feed("\x1b[4;1H")
        self.linked("BOTTOM", "https://bottom.example")
        self.feed("\x1b[2;3r\x1b[3;1H\n")
        self.assertEqual(self.screen.display[1].rstrip(), "BBB")
        self.assertEqual(self.screen.link_at(0, 1), "https://b.example")
        self.assertIsNone(self.screen.link_at(0, 2))
        self.feed("\x1b[2;1H\x1bM")
        self.assertIsNone(self.screen.link_at(0, 1))
        self.assertEqual(self.screen.display[2].rstrip(), "BBB")
        self.assertEqual(self.screen.link_at(0, 2), "https://b.example")
        self.assertEqual(self.screen.link_at(0, 0), "https://top.example")
        self.assertEqual(self.screen.link_at(0, 3), "https://bottom.example")

    def test_scroll_commands_and_resize_preserve_surviving_links(self):
        self.linked("AAA", "https://a.example")
        self.feed("\r\n")
        self.linked("BBB", "https://b.example")
        self.feed("\x1b[S")
        self.assertEqual(self.screen.display[0].rstrip(), "BBB")
        self.assertEqual(self.screen.link_at(0, 0), "https://b.example")
        self.feed("\x1b[T")
        self.assertEqual(self.screen.link_at(0, 1), "https://b.example")
        self.assertIsNone(self.screen.link_at(0, 0))
        self.screen.resize(5, 10)
        self.assertEqual(self.screen.link_at(0, 1), "https://b.example")
        self.feed("\x1b[2J")
        self.assertIsNone(self.screen.link_at(0, 1))

    def test_insert_delete_lines_keep_links_with_text(self):
        self.linked("AAA")
        self.feed("\x1b[H\x1b[L")
        self.assertIsNone(self.screen.link_at(0, 0))
        self.assertEqual(self.screen.link_at(0, 1), "https://ex.com")
        self.feed("\x1b[M")
        self.assertEqual(self.screen.link_at(0, 0), "https://ex.com")
        self.assertIsNone(self.screen.link_at(0, 1))


if __name__ == "__main__":
    unittest.main()
