"""Keep EN/PL documentation paths and relative links release-ready."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
LOCALES = ("en", "pl")
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^]]*\]\((?P<href>[^ )]+)")


def markdown_paths(locale: str) -> set[Path]:
    root = DOCS / locale
    return {path.relative_to(root) for path in root.rglob("*.md")}


class DocsLocaleLinksTests(unittest.TestCase):
    def test_locales_have_the_same_page_map(self) -> None:
        self.assertSetEqual(markdown_paths("en"), markdown_paths("pl"))

    def test_relative_links_resolve_inside_each_locale(self) -> None:
        for locale in LOCALES:
            locale_root = (DOCS / locale).resolve()
            for source_relative in markdown_paths(locale):
                source = locale_root / source_relative
                content = source.read_text(encoding="utf-8")
                for match in MARKDOWN_LINK.finditer(content):
                    href = match.group("href").strip("<>")
                    target = href.split("#", maxsplit=1)[0]
                    if not target or ":" in target or target.startswith("/"):
                        continue
                    resolved = (source.parent / target).resolve()
                    with self.subTest(locale=locale, source=source_relative, href=href):
                        self.assertTrue(resolved.is_relative_to(locale_root))
                        self.assertTrue(resolved.is_file(), f"missing target: {resolved}")
