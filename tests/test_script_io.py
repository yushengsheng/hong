from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from macro_app.models import MacroScript
from macro_app.script_io import load_script, save_script


class ScriptIoTests(unittest.TestCase):
    def test_text_round_trip_preserves_hotkey_and_custom_order(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "macro.txt"
            script = MacroScript(
                name="demo",
                created_at="2026-03-11T10:00:00+00:00",
                screen_size=(1920, 1080),
                default_loops=2,
                default_speed=1.5,
                global_hotkey="Ctrl+Alt+1",
                custom_order=3,
            )

            save_script(path, script)
            loaded = load_script(path)

            self.assertEqual(loaded.name, "demo")
            self.assertEqual(loaded.global_hotkey, "Ctrl+Alt+1")
            self.assertEqual(loaded.custom_order, 3)
            self.assertEqual(loaded.default_loops, 2)
            self.assertEqual(loaded.default_speed, 1.5)

    def test_json_like_script_missing_created_at_still_loads(self) -> None:
        payload = {
            "name": "legacy",
            "screen_size": [1280, 720],
            "screen_origin": [0, 0],
            "default_loops": 1,
            "default_speed": 1.0,
            "events": [],
            "version": 4,
        }
        script = MacroScript.from_dict(payload)
        self.assertTrue(script.created_at)
        self.assertEqual(script.name, "legacy")


if __name__ == "__main__":
    unittest.main()
