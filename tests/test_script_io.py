from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from macro_app.models import MacroEvent, MacroScript
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

    def test_text_round_trip_preserves_modifier_function_key_sequence(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "combo.txt"
            script = MacroScript(
                name="combo",
                created_at="2026-03-11T10:00:00+00:00",
                screen_size=(1920, 1080),
                events=[
                    MacroEvent(0.0, "key_press", {"key": {"type": "special", "value": "ctrl_l"}}),
                    MacroEvent(0.05, "key_press", {"key": {"type": "special", "value": "f5"}}),
                    MacroEvent(0.10, "key_release", {"key": {"type": "special", "value": "f5"}}),
                    MacroEvent(0.15, "key_release", {"key": {"type": "special", "value": "ctrl_l"}}),
                ],
            )

            save_script(path, script)
            loaded = load_script(path)

            self.assertEqual(
                [event.payload["key"] for event in loaded.events],
                [
                    {"type": "special", "value": "ctrl_l"},
                    {"type": "special", "value": "f5"},
                    {"type": "special", "value": "f5"},
                    {"type": "special", "value": "ctrl_l"},
                ],
            )
            self.assertEqual(
                [event.kind for event in loaded.events],
                ["key_press", "key_press", "key_release", "key_release"],
            )


if __name__ == "__main__":
    unittest.main()
