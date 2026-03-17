from __future__ import annotations

import unittest
from unittest.mock import patch

from macro_app.display import ScreenBounds
from macro_app.recorder import MacroRecorder


class FakeListener:
    def __init__(self, *, fail_on_start: bool = False) -> None:
        self.fail_on_start = fail_on_start
        self.started = False
        self.stopped = False
        self.joined = False

    def start(self) -> None:
        self.started = True
        if self.fail_on_start:
            raise RuntimeError("boom")

    def stop(self) -> None:
        self.stopped = True

    def join(self, timeout: float | None = None) -> None:
        self.joined = True


class MacroRecorderTests(unittest.TestCase):
    def test_start_rolls_back_when_listener_start_fails(self) -> None:
        bounds = ScreenBounds(left=0, top=0, width=1920, height=1080)
        mouse_listener = FakeListener()
        keyboard_listener = FakeListener(fail_on_start=True)

        with patch("macro_app.recorder.get_screen_bounds", return_value=bounds):
            with patch("macro_app.recorder.mouse.Listener", side_effect=lambda **kwargs: mouse_listener):
                with patch("macro_app.recorder.keyboard.Listener", side_effect=lambda **kwargs: keyboard_listener):
                    recorder = MacroRecorder()

                    with self.assertRaisesRegex(RuntimeError, "boom"):
                        recorder.start()

        self.assertFalse(recorder.active)
        self.assertIsNone(recorder._mouse_listener)
        self.assertIsNone(recorder._keyboard_listener)
        self.assertTrue(mouse_listener.started)
        self.assertTrue(mouse_listener.stopped)
        self.assertTrue(mouse_listener.joined)
        self.assertTrue(keyboard_listener.started)
        self.assertTrue(keyboard_listener.stopped)
        self.assertTrue(keyboard_listener.joined)

    def test_stop_orders_events_by_time_offset_then_sequence(self) -> None:
        recorder = MacroRecorder()
        recorder._active = True
        recorder._mouse_listener = FakeListener()
        recorder._keyboard_listener = FakeListener()
        recorder._recording_bounds = ScreenBounds(left=0, top=0, width=1920, height=1080)

        recorder._append_event("key_press", {"key": {"type": "char", "value": "late"}}, time_offset=0.2)
        recorder._append_event("key_press", {"key": {"type": "char", "value": "first"}}, time_offset=0.1)
        recorder._append_event("key_press", {"key": {"type": "char", "value": "second"}}, time_offset=0.1)

        script = recorder.stop()

        self.assertEqual(
            [event.payload["key"]["value"] for event in script.events],
            ["first", "second", "late"],
        )
        self.assertEqual(
            [event.time_offset for event in script.events],
            [0.1, 0.1, 0.2],
        )


if __name__ == "__main__":
    unittest.main()
