from __future__ import annotations

import unittest

from macro_app.ui_theme import build_ui_fonts, choose_ui_font_family


class UiThemeTests(unittest.TestCase):
    def test_choose_ui_font_family_prefers_windows_cjk_fonts(self) -> None:
        family = choose_ui_font_family(
            {"Segoe UI", "Microsoft YaHei UI"},
            platform="win32",
        )
        self.assertEqual(family, "Microsoft YaHei UI")

    def test_choose_ui_font_family_falls_back_to_segoe_ui_on_windows(self) -> None:
        family = choose_ui_font_family(
            {"Segoe UI"},
            platform="win32",
        )
        self.assertEqual(family, "Segoe UI")

    def test_choose_ui_font_family_returns_default_font_elsewhere(self) -> None:
        family = choose_ui_font_family(
            {"Segoe UI", "Microsoft YaHei UI"},
            platform="linux",
        )
        self.assertEqual(family, "TkDefaultFont")

    def test_build_ui_fonts_uses_larger_windows_sizes(self) -> None:
        fonts = build_ui_fonts({"Microsoft YaHei UI"}, platform="win32")
        self.assertEqual(fonts.family, "Microsoft YaHei UI")
        self.assertEqual(fonts.body, ("Microsoft YaHei UI", 10))
        self.assertEqual(fonts.small, ("Microsoft YaHei UI", 9))
        self.assertEqual(fonts.title, ("Microsoft YaHei UI", 11, "bold"))
        self.assertEqual(fonts.stage, ("Microsoft YaHei UI", 18, "bold"))


if __name__ == "__main__":
    unittest.main()
