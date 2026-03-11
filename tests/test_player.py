from __future__ import annotations

import unittest

from macro_app.display import ScreenBounds
from macro_app.models import MacroEvent
from macro_app.player import MacroPlayer


class FakeKeyboard:
    def __init__(self) -> None:
        self.actions: list[tuple[str, str]] = []

    def press(self, key: object) -> None:
        self.actions.append(("press", _key_name(key)))

    def release(self, key: object) -> None:
        self.actions.append(("release", _key_name(key)))


class FakeMouse:
    def __init__(self) -> None:
        self.position = (0, 0)

    def press(self, _button: object) -> None:
        return None

    def release(self, _button: object) -> None:
        return None

    def scroll(self, _dx: int, _dy: int) -> None:
        return None


class MacroPlayerTests(unittest.TestCase):
    def test_apply_event_preserves_modifier_function_key_order(self) -> None:
        player = MacroPlayer()
        player._keyboard = FakeKeyboard()
        player._mouse = FakeMouse()

        recorded_bounds = ScreenBounds(left=0, top=0, width=1920, height=1080)
        current_bounds = ScreenBounds(left=0, top=0, width=1920, height=1080)
        events = [
            MacroEvent(0.0, "key_press", {"key": {"type": "special", "value": "ctrl_l"}}),
            MacroEvent(0.05, "key_press", {"key": {"type": "special", "value": "f5"}}),
            MacroEvent(0.10, "key_release", {"key": {"type": "special", "value": "f5"}}),
            MacroEvent(0.15, "key_release", {"key": {"type": "special", "value": "ctrl_l"}}),
        ]

        for event in events:
            player._apply_event(
                event,
                recorded_bounds=recorded_bounds,
                current_bounds=current_bounds,
            )

        self.assertEqual(
            player._keyboard.actions,
            [
                ("press", "ctrl_l"),
                ("press", "f5"),
                ("release", "f5"),
                ("release", "ctrl_l"),
            ],
        )

    def test_apply_event_preserves_multiple_modifier_shortcut_order(self) -> None:
        player = MacroPlayer()
        player._keyboard = FakeKeyboard()
        player._mouse = FakeMouse()

        recorded_bounds = ScreenBounds(left=0, top=0, width=1920, height=1080)
        current_bounds = ScreenBounds(left=0, top=0, width=1920, height=1080)
        events = [
            MacroEvent(0.0, "key_press", {"key": {"type": "special", "value": "ctrl_r"}}),
            MacroEvent(0.01, "key_press", {"key": {"type": "special", "value": "shift_r"}}),
            MacroEvent(0.02, "key_press", {"key": {"type": "special", "value": "f12"}}),
            MacroEvent(0.03, "key_release", {"key": {"type": "special", "value": "f12"}}),
            MacroEvent(0.04, "key_release", {"key": {"type": "special", "value": "shift_r"}}),
            MacroEvent(0.05, "key_release", {"key": {"type": "special", "value": "ctrl_r"}}),
        ]

        for event in events:
            player._apply_event(
                event,
                recorded_bounds=recorded_bounds,
                current_bounds=current_bounds,
            )

        self.assertEqual(
            player._keyboard.actions,
            [
                ("press", "ctrl_r"),
                ("press", "shift_r"),
                ("press", "f12"),
                ("release", "f12"),
                ("release", "shift_r"),
                ("release", "ctrl_r"),
            ],
        )

    def test_apply_event_replays_legacy_char_shortcut_as_virtual_key(self) -> None:
        player = MacroPlayer()
        player._keyboard = FakeKeyboard()
        player._mouse = FakeMouse()

        recorded_bounds = ScreenBounds(left=0, top=0, width=1920, height=1080)
        current_bounds = ScreenBounds(left=0, top=0, width=1920, height=1080)
        events = [
            MacroEvent(0.0, "key_press", {"key": {"type": "special", "value": "ctrl_l"}}),
            MacroEvent(0.01, "key_press", {"key": {"type": "special", "value": "shift_r"}}),
            MacroEvent(0.02, "key_press", {"key": {"type": "char", "value": "V"}}),
            MacroEvent(0.03, "key_release", {"key": {"type": "char", "value": "V"}}),
            MacroEvent(0.04, "key_release", {"key": {"type": "special", "value": "shift_r"}}),
            MacroEvent(0.05, "key_release", {"key": {"type": "special", "value": "ctrl_l"}}),
        ]

        for event in events:
            player._apply_event(
                event,
                recorded_bounds=recorded_bounds,
                current_bounds=current_bounds,
            )

        self.assertEqual(
            player._keyboard.actions,
            [
                ("press", "ctrl_l"),
                ("press", "shift_r"),
                ("press", "vk:86"),
                ("release", "vk:86"),
                ("release", "shift_r"),
                ("release", "ctrl_l"),
            ],
        )

    def test_apply_event_replays_legacy_char_shortcut_even_if_modifier_releases_first(self) -> None:
        player = MacroPlayer()
        player._keyboard = FakeKeyboard()
        player._mouse = FakeMouse()

        recorded_bounds = ScreenBounds(left=0, top=0, width=1920, height=1080)
        current_bounds = ScreenBounds(left=0, top=0, width=1920, height=1080)
        events = [
            MacroEvent(0.0, "key_press", {"key": {"type": "special", "value": "ctrl_l"}}),
            MacroEvent(0.01, "key_press", {"key": {"type": "char", "value": "v"}}),
            MacroEvent(0.02, "key_release", {"key": {"type": "special", "value": "ctrl_l"}}),
            MacroEvent(0.03, "key_release", {"key": {"type": "char", "value": "v"}}),
        ]

        for event in events:
            player._apply_event(
                event,
                recorded_bounds=recorded_bounds,
                current_bounds=current_bounds,
            )

        self.assertEqual(
            player._keyboard.actions,
            [
                ("press", "ctrl_l"),
                ("press", "vk:86"),
                ("release", "ctrl_l"),
                ("release", "vk:86"),
            ],
        )


def _key_name(key: object) -> str:
    name = getattr(key, "name", None)
    if name is not None:
        return str(name)

    char = getattr(key, "char", None)
    if char is not None:
        return str(char)

    vk = getattr(key, "vk", None)
    if vk is not None:
        return f"vk:{vk}"

    return str(key)


if __name__ == "__main__":
    unittest.main()
