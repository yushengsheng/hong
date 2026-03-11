from __future__ import annotations

import unittest

from pynput import keyboard

from macro_app.input_codec import deserialize_key, serialize_key


class InputCodecTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
