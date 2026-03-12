from __future__ import annotations

import unittest

from pynput import keyboard

from macro_app.input_codec import deserialize_key, serialize_key, virtual_key_from_char


ROUND_TRIP_SPECIAL_KEYS = [
    "f1",
    "f2",
    "f3",
    "f4",
    "f5",
    "f6",
    "f7",
    "f8",
    "f9",
    "f10",
    "f11",
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


class InputCodecTests(unittest.TestCase):
    def test_special_keys_round_trip_through_codec(self) -> None:
        for key_name in ROUND_TRIP_SPECIAL_KEYS:
            with self.subTest(key_name=key_name):
                key = keyboard.Key[key_name]
                payload = serialize_key(key)
                restored = deserialize_key(payload)

                self.assertEqual(payload, {"type": "special", "value": key_name})
                self.assertEqual(restored, key)

    def test_serialize_key_preserves_function_key(self) -> None:
        payload = serialize_key(keyboard.Key.f12)
        self.assertEqual(payload, {"type": "special", "value": "f12"})

    def test_serialize_key_preserves_modifier_key(self) -> None:
        payload = serialize_key(keyboard.Key.ctrl_l)
        self.assertEqual(payload, {"type": "special", "value": "ctrl_l"})

    def test_serialize_key_normalizes_ctrl_c_control_character(self) -> None:
        payload = serialize_key(keyboard.KeyCode.from_char("\x03"))
        self.assertEqual(payload, {"type": "char", "value": "c"})

    def test_serialize_key_normalizes_ctrl_v_control_character(self) -> None:
        payload = serialize_key(keyboard.KeyCode.from_char("\x16"))
        self.assertEqual(payload, {"type": "char", "value": "v"})

    def test_serialize_key_keeps_readable_char_for_shortcut_key(self) -> None:
        payload = serialize_key(keyboard.KeyCode(vk=86, char="V"), prefer_vk=True)
        self.assertEqual(payload, {"type": "char", "value": "V"})

    def test_serialize_ctrl_shortcut_control_character_as_readable_char(self) -> None:
        key = keyboard.KeyCode(vk=67, char="\x03")
        payload = serialize_key(key, prefer_vk=True)
        self.assertEqual(payload, {"type": "char", "value": "c"})

    def test_deserialize_key_restores_printable_char_keycode(self) -> None:
        key = deserialize_key({"type": "char", "value": "c"})
        self.assertIsInstance(key, keyboard.KeyCode)
        self.assertEqual(key.char, "c")

    def test_deserialize_key_restores_function_key(self) -> None:
        key = deserialize_key({"type": "special", "value": "f12"})
        self.assertEqual(key, keyboard.Key.f12)

    def test_deserialize_key_restores_modifier_key(self) -> None:
        key = deserialize_key({"type": "special", "value": "ctrl_l"})
        self.assertEqual(key, keyboard.Key.ctrl_l)

    def test_deserialize_key_normalizes_legacy_ctrl_c_control_character(self) -> None:
        key = deserialize_key({"type": "char", "value": "\x03"})
        self.assertIsInstance(key, keyboard.KeyCode)
        self.assertEqual(key.char, "c")

    def test_virtual_key_from_char_maps_uppercase_shortcut_key(self) -> None:
        self.assertEqual(virtual_key_from_char("V"), 86)


if __name__ == "__main__":
    unittest.main()
