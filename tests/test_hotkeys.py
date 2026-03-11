from __future__ import annotations

import unittest

from macro_app.hotkeys import HotkeyParseError, hotkey_from_tk_event, normalize_hotkey


class HotkeyTests(unittest.TestCase):
    def test_normalize_hotkey_accepts_combo(self) -> None:
        canonical, display = normalize_hotkey("Ctrl+Alt+1")
        self.assertEqual(canonical, "<ctrl>+<alt>+1")
        self.assertEqual(display, "Ctrl+Alt+1")

    def test_normalize_hotkey_rejects_multiple_primary_keys(self) -> None:
        with self.assertRaises(HotkeyParseError):
            normalize_hotkey("Ctrl+Alt+1+2")

    def test_hotkey_from_tk_event_builds_combo(self) -> None:
        canonical, display = hotkey_from_tk_event("F2", 0x0005)
        self.assertEqual(canonical, "<ctrl>+<shift>+<f2>")
        self.assertEqual(display, "Ctrl+Shift+F2")

    def test_hotkey_from_tk_event_requires_modifier(self) -> None:
        with self.assertRaises(HotkeyParseError):
            hotkey_from_tk_event("1", 0)


if __name__ == "__main__":
    unittest.main()
