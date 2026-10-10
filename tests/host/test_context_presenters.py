"""Pure context presentation contracts; no Git subprocess fixtures."""

import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import context_presenters as _mod
import context_selection as _selection


class EllipsizeTests(unittest.TestCase):
    def test_short_text_unchanged(self) -> None:
        self.assertEqual(_mod._ellipsize("hello", 10), "hello")

    def test_exact_width_unchanged(self) -> None:
        self.assertEqual(_mod._ellipsize("hello", 5), "hello")

    def test_long_text_truncated_with_ellipsis(self) -> None:
        result = _mod._ellipsize("a very long path name", 10)
        self.assertEqual(result, "a very lo…")
        self.assertEqual(len(result), 10)

    def test_width_zero_is_empty(self) -> None:
        self.assertEqual(_mod._ellipsize("hello", 0), "")

    def test_width_one_is_just_ellipsis(self) -> None:
        self.assertEqual(_mod._ellipsize("hello", 1), "…")


class SelectionOutsideScanTests(unittest.TestCase):
    def test_lists_picks_not_in_current_scan_preserving_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a"
            b = root / "b"
            c = root / "c"
            a.mkdir()
            b.mkdir()
            c.mkdir()
            selected = [b, a]
            repos = [(c, False)]
            outside = _mod.selection_outside_scan(selected, repos)
            self.assertEqual([p.name for p in outside], ["b", "a"])

    def test_empty_when_all_visible(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a"
            a.mkdir()
            self.assertEqual(_mod.selection_outside_scan([a], [(a, True)]), [])


class FormatWillAddLinesTests(unittest.TestCase):
    def setUp(self):
        # Formatting can ask about picks outside the scanned directory.
        # The pure contract supplies that Git boundary instead of executing it.
        boundary = patch.object(_selection, "is_git_repo", return_value=False)
        boundary.start()
        self.addCleanup(boundary.stop)

    def test_empty_shows_hint(self) -> None:
        lines = _selection.format_will_add_lines([], [], width=40, max_lines=5)
        self.assertEqual(lines, ["(empty — Space to pick)"])

    def test_pick_order_and_elsewhere_tag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            api = root / "api"
            web = root / "web"
            api.mkdir()
            web.mkdir()
            selected = [web, api]
            repos = [(api, True)]
            lines = _selection.format_will_add_lines(
                selected, repos, width=40, max_lines=5
            )
            self.assertEqual(lines[0], "+ web  (mount · elsewhere)")
            self.assertEqual(lines[1], "+ api")

    def test_omits_overflow_with_more_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = []
            for name in ("a", "b", "c", "d"):
                p = root / name
                p.mkdir()
                paths.append(p)
            lines = _selection.format_will_add_lines(
                paths, [(paths[0], False)], width=40, max_lines=3
            )
            self.assertEqual(len(lines), 3)
            self.assertTrue(lines[-1].startswith("… +"))
            self.assertIn("2 more", lines[-1])

    def test_in_ws_and_other_ws_tags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            api = root / "api"
            web = root / "web"
            api.mkdir()
            web.mkdir()
            lines = _selection.format_will_add_lines(
                [api, web],
                [(api, True), (web, True)],
                width=60,
                max_lines=5,
                names_in_ws={"api"},
                paths_in_ws={str(api.resolve())},
                path_ws={str(web.resolve()): "other"},
                workspace="acme",
            )
            self.assertEqual(lines[0], "+ api  (in ws)")
            self.assertEqual(lines[1], "+ web  (other ws)")


class StackApplySummaryTests(unittest.TestCase):
    def test_counts_new_vs_already(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a"
            b = root / "b"
            a.mkdir()
            b.mkdir()
            new_n, already = _mod.stack_apply_summary(
                [a, b], paths_in_ws={str(a.resolve())}
            )
            self.assertEqual((new_n, already), (1, 1))


class ReviewOutcomeTests(unittest.TestCase):
    def test_explains_effect_in_plain_language(self) -> None:
        self.assertEqual(_mod.review_outcome([]), "new project")
        self.assertEqual(
            _mod.review_outcome(["in ws", "other ws"]),
            "already connected — no change · also used in another workspace",
        )


class CollapsedManageRowsTests(unittest.TestCase):
    def test_hides_only_projects_of_collapsed_workspace(self) -> None:
        workspaces = [
            {"name": "one", "projects": [{"name": "api"}]},
            {"name": "two", "projects": [{"name": "web"}]},
        ]
        self.assertEqual(
            _mod.manage_rows(workspaces, {0}),
            [("ws", 0, None), ("ws", 1, None), ("proj", 1, 0)],
        )


class HumanizeTests(unittest.TestCase):
    def test_seconds_minutes_hours_days(self) -> None:
        self.assertEqual(_mod._humanize(30), "30s")
        self.assertEqual(_mod._humanize(90), "1m")
        self.assertEqual(_mod._humanize(3600), "1h")
        self.assertEqual(_mod._humanize(2 * 86400), "2d")

    def test_negative_clamps_to_zero(self) -> None:
        self.assertEqual(_mod._humanize(-5), "0s")


class UpdatePickHistoryTests(unittest.TestCase):
    def test_last_path_becomes_newest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = root / "a"
            b = root / "b"
            a.mkdir()
            b.mkdir()
            hist = _selection.update_pick_history([], [a, b], now=100.0)
            self.assertEqual([h["path"] for h in hist], [str(b), str(a)])
