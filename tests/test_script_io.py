from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from macro_app.models import MacroEvent, MacroScript
from macro_app.script_io import load_script, save_script


ROUND_TRIP_SPECIAL_KEYS = [
    "f1",
    "f12",
    "ctrl",
    "ctrl_l",
    "ctrl_r",
    "alt",
    "alt_l",
    "alt_r",
    "shift",
    "shift_r",
    "cmd",
    "cmd_r",
    "tab",
    "enter",
    "esc",
    "space",
    "backspace",
    "delete",
    "insert",
    "home",
    "end",
    "page_up",
    "page_down",
    "up",
    "down",
    "left",
    "right",
]


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

    def test_text_round_trip_preserves_legacy_char_shortcut_sequence(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "legacy-shortcut.txt"
            script = MacroScript(
                name="legacy-shortcut",
                created_at="2026-03-11T10:00:00+00:00",
                screen_size=(1920, 1080),
                events=[
                    MacroEvent(0.0, "key_press", {"key": {"type": "special", "value": "ctrl_l"}}),
                    MacroEvent(0.05, "key_press", {"key": {"type": "char", "value": "v"}}),
                    MacroEvent(0.10, "key_release", {"key": {"type": "special", "value": "ctrl_l"}}),
                    MacroEvent(0.15, "key_release", {"key": {"type": "char", "value": "v"}}),
                ],
            )

            save_script(path, script)
            loaded = load_script(path)

            self.assertEqual(
                [event.payload["key"] for event in loaded.events],
                [
                    {"type": "special", "value": "ctrl_l"},
                    {"type": "char", "value": "v"},
                    {"type": "special", "value": "ctrl_l"},
                    {"type": "char", "value": "v"},
                ],
            )
            self.assertEqual(
                [event.kind for event in loaded.events],
                ["key_press", "key_press", "key_release", "key_release"],
            )

    def test_json_round_trip_preserves_legacy_char_shortcut_sequence(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "legacy-shortcut.json"
            script = MacroScript(
                name="legacy-shortcut",
                created_at="2026-03-11T10:00:00+00:00",
                screen_size=(1920, 1080),
                events=[
                    MacroEvent(0.0, "key_press", {"key": {"type": "special", "value": "ctrl_l"}}),
                    MacroEvent(0.05, "key_press", {"key": {"type": "char", "value": "V"}}),
                    MacroEvent(0.10, "key_release", {"key": {"type": "special", "value": "ctrl_l"}}),
                    MacroEvent(0.15, "key_release", {"key": {"type": "char", "value": "V"}}),
                ],
            )

            save_script(path, script)
            loaded = load_script(path)

            self.assertEqual(
                [event.payload["key"] for event in loaded.events],
                [
                    {"type": "special", "value": "ctrl_l"},
                    {"type": "char", "value": "V"},
                    {"type": "special", "value": "ctrl_l"},
                    {"type": "char", "value": "V"},
                ],
            )
            self.assertEqual(
                [event.kind for event in loaded.events],
                ["key_press", "key_press", "key_release", "key_release"],
            )

    def test_text_round_trip_preserves_supported_special_keys(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "special-keys.txt"
            events = []
            time_offset = 0.0
            for key_name in ROUND_TRIP_SPECIAL_KEYS:
                events.append(MacroEvent(time_offset, "key_press", {"key": {"type": "special", "value": key_name}}))
                time_offset += 0.01
                events.append(MacroEvent(time_offset, "key_release", {"key": {"type": "special", "value": key_name}}))
                time_offset += 0.01

            script = MacroScript(
                name="special-keys",
                created_at="2026-03-11T10:00:00+00:00",
                screen_size=(1920, 1080),
                events=events,
            )

            save_script(path, script)
            loaded = load_script(path)

            self.assertEqual(
                [event.payload["key"] for event in loaded.events],
                [event.payload["key"] for event in events],
            )
            self.assertEqual(
                [event.kind for event in loaded.events],
                [event.kind for event in events],
            )

    def test_text_loads_legacy_virtual_key_lines(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "legacy-vk.txt"
            path.write_text(
                "\n".join(
                    [
                        "# 宏脚本文本格式 v4",
                        "名称: legacy-vk",
                        "创建时间: 2026-03-11T10:00:00+00:00",
                        "版本: 4",
                        "屏幕尺寸: 1920,1080",
                        "屏幕原点: 0,0",
                        "默认循环次数: 1",
                        "默认播放速度: 1.0",
                        "全局快捷键: ",
                        "自定义排序: ",
                        "事件数: 2",
                        "",
                        "事件:",
                        "间隔=0.000000 | 键盘按下 | 按键=虚拟键:67",
                        "间隔=0.020000 | 键盘松开 | 按键=虚拟键:67",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            loaded = load_script(path)

            self.assertEqual(
                [event.payload["key"] for event in loaded.events],
                [
                    {"type": "vk", "value": 67},
                    {"type": "vk", "value": 67},
                ],
            )

    def test_text_save_preserves_event_comments_when_rewriting_metadata(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "commented.txt"
            path.write_text(
                "\n".join(
                    [
                        "# 宏脚本文本格式 v4",
                        "# 头部注释",
                        "名称: commented",
                        "创建时间: 2026-03-11T10:00:00+00:00",
                        "版本: 4",
                        "屏幕尺寸: 1920,1080",
                        "屏幕原点: 0,0",
                        "默认循环次数: 1",
                        "默认播放速度: 1.0",
                        "全局快捷键: ",
                        "自定义排序: ",
                        "事件数: 4",
                        "",
                        "事件:",
                        "### 第一段",
                        "间隔=0.000000 | 键盘按下 | 按键=特殊:ctrl_l",
                        "间隔=0.010000 | 键盘按下 | 按键=虚拟键:67",
                        "",
                        "### 第二段",
                        "间隔=0.020000 | 键盘松开 | 按键=虚拟键:67",
                        "间隔=0.030000 | 键盘松开 | 按键=特殊:ctrl_l",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            script = load_script(path)
            script.custom_order = 5
            save_script(path, script, preserve_text_from=path)

            rewritten = path.read_text(encoding="utf-8")
            self.assertIn("### 第一段", rewritten)
            self.assertIn("### 第二段", rewritten)
            self.assertIn("按键=虚拟键:67", rewritten)
            self.assertIn("自定义排序: 5", rewritten)


if __name__ == "__main__":
    unittest.main()
