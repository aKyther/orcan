#!/usr/bin/env python3
"""Anti-drift test for the shortcuts manifest (shortcuts.py): every tmux-layer
entry's tmux_tokens must be a literal substring of the real
docker/rootfs/etc/tmux/keybindings.conf — catches either file changing
without the other. shortcuts.py is stdlib-only (no Textual/orcan.* import),
loaded directly by file path exactly like actions.py.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHORTCUTS_PATH = ROOT / "cockpit" / "src" / "orcan_cockpit" / "shortcuts.py"
KEYBINDINGS_PATH = ROOT / "docker" / "rootfs" / "etc" / "tmux" / "keybindings.conf"

_spec = importlib.util.spec_from_file_location("cockpit_shortcuts", SHORTCUTS_PATH)
shortcuts = importlib.util.module_from_spec(_spec)
# dataclasses' own type-resolution machinery looks the module up via
# sys.modules[cls.__module__] — must be registered *before* exec_module,
# or @dataclass on Shortcut raises AttributeError on a None module.
sys.modules[_spec.name] = shortcuts
_spec.loader.exec_module(shortcuts)


class TmuxTokenDriftTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conf = KEYBINDINGS_PATH.read_text(encoding="utf-8")

    def test_every_tmux_token_is_a_literal_substring_of_keybindings_conf(self) -> None:
        for shortcut in shortcuts.SHORTCUTS:
            if shortcut.layer != "tmux":
                continue
            for token in shortcut.tmux_tokens:
                self.assertIn(
                    token, self.conf,
                    f"{shortcut.keys!r} ({shortcut.description!r}) token {token!r} "
                    "not found in keybindings.conf — manifest and config have drifted",
                )

    def test_every_tmux_entry_has_at_least_one_token(self) -> None:
        for shortcut in shortcuts.SHORTCUTS:
            if shortcut.layer == "tmux":
                self.assertTrue(shortcut.tmux_tokens, f"{shortcut.keys!r} has no tmux_tokens to verify")


class ManifestSanityTests(unittest.TestCase):
    def test_every_context_used_is_a_valid_literal(self) -> None:
        for shortcut in shortcuts.SHORTCUTS:
            for context in shortcut.contexts:
                self.assertIn(context, shortcuts.VALID_CONTEXTS, f"{shortcut.keys!r} has invalid context {context!r}")

    def test_every_layer_is_tmux_or_app(self) -> None:
        for shortcut in shortcuts.SHORTCUTS:
            self.assertIn(shortcut.layer, ("tmux", "app"))

    def test_no_duplicate_keys_within_a_layer(self) -> None:
        seen: dict[str, set[str]] = {"tmux": set(), "app": set()}
        for shortcut in shortcuts.SHORTCUTS:
            self.assertNotIn(
                shortcut.keys, seen[shortcut.layer],
                f"duplicate {shortcut.layer} entry for {shortcut.keys!r}",
            )
            seen[shortcut.layer].add(shortcut.keys)


class EmbedDisclaimerTests(unittest.TestCase):
    def test_product_metadata_and_docs_url_are_public(self) -> None:
        self.assertEqual(shortcuts.PRODUCT_NAME, "orcan cockpit")
        self.assertTrue(shortcuts.DOCS_URL.startswith("https://"))

    def test_disclaimer_is_non_empty(self) -> None:
        self.assertIn("native attach", shortcuts.EMBED_DISCLAIMER)
        self.assertIn("Alt+", shortcuts.BROWSER_KEY_LIMIT)
        self.assertIn("ttyd", shortcuts.BROWSER_KEY_LIMIT)

    def test_cli_render_includes_disclaimer(self) -> None:
        cli_path = ROOT / "cockpit" / "src" / "orcan_cockpit" / "shortcuts_cli.py"
        # Load the package dependency explicitly; unittest discovery must not
        # rely on another test having already imported orcan_cockpit.
        cockpit_src = str(ROOT / "cockpit" / "src")
        if cockpit_src not in sys.path:
            sys.path.insert(0, cockpit_src)
        spec = importlib.util.spec_from_file_location("cockpit_shortcuts_cli", cli_path)
        cli = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cli
        spec.loader.exec_module(cli)
        rendered = cli.render_plaintext()
        self.assertIn(shortcuts.EMBED_DISCLAIMER, rendered)
        self.assertIn(shortcuts.BROWSER_KEY_LIMIT, rendered)
        self.assertIn(shortcuts.PRODUCT_NAME, rendered)
        self.assertIn(shortcuts.DOCS_URL, rendered)


if __name__ == "__main__":
    unittest.main()
