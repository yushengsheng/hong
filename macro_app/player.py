from __future__ import annotations

import json
import threading
import time

from pynput import keyboard, mouse

from .display import ScreenBounds, denormalize_point, get_screen_bounds, scale_point
from .input_codec import deserialize_button, deserialize_key, virtual_key_from_char
from .models import MacroEvent, MacroScript


class MacroPlayer:
    _SHORTCUT_MODIFIER_NAMES = {
        "ctrl",
        "ctrl_l",
        "ctrl_r",
        "alt",
        "alt_l",
        "alt_r",
        "alt_gr",
        "cmd",
        "cmd_l",
        "cmd_r",
    }

    def __init__(self) -> None:
        self._keyboard = keyboard.Controller()
        self._mouse = mouse.Controller()
        self._stop_event = threading.Event()
        self._active = False
        self._pressed_keys: dict[str, keyboard.Key | keyboard.KeyCode] = {}
        self._pressed_buttons: dict[str, mouse.Button] = {}

    @property
    def active(self) -> bool:
        return self._active

    def stop(self) -> None:
        self._stop_event.set()

    def play(self, script: MacroScript, *, loops: int = 1, speed: float = 1.0) -> bool:
        if self._active:
            raise RuntimeError("Player is already active")
        if speed <= 0:
            raise ValueError("Speed must be greater than zero")
        if loops < 0:
            raise ValueError("Loops must be zero or greater")

        self._active = True
        self._stop_event.clear()
        self._pressed_keys.clear()
        self._pressed_buttons.clear()
        completed = True
        has_events = bool(script.events)

        try:
            remaining_loops = loops
            while not self._stop_event.is_set():
                if has_events:
                    self._play_once(script, speed=speed)
                elif loops == 0 and self._wait_or_stop(0.05):
                    completed = False
                    break

                if self._stop_event.is_set():
                    completed = False
                    break

                if loops == 0:
                    continue

                remaining_loops -= 1
                if remaining_loops <= 0:
                    break
        finally:
            self._release_pressed_inputs()
            self._active = False

        return completed

    def _play_once(self, script: MacroScript, *, speed: float) -> None:
        recorded_bounds = self._get_recorded_bounds(script)
        current_bounds = get_screen_bounds()

        loop_started = time.perf_counter()
        for event in script.events:
            target_time = loop_started + (event.time_offset / speed)
            self._sleep_until(target_time)
            if self._stop_event.is_set():
                break
            self._apply_event(
                event,
                recorded_bounds=recorded_bounds,
                current_bounds=current_bounds,
            )

    def _sleep_until(self, target_time: float) -> None:
        while not self._stop_event.is_set():
            remaining = target_time - time.perf_counter()
            if remaining <= 0:
                return
            if self._wait_or_stop(min(remaining, 0.01)):
                return

    def _apply_event(
        self,
        event: MacroEvent,
        *,
        recorded_bounds: ScreenBounds,
        current_bounds: ScreenBounds,
    ) -> None:
        payload = event.payload

        if event.kind == "mouse_move":
            self._mouse.position = self._resolve_pointer_position(
                payload,
                recorded_bounds=recorded_bounds,
                current_bounds=current_bounds,
            )
            return

        if event.kind == "mouse_tap":
            button = deserialize_button(payload["button"])
            position = self._resolve_pointer_position(
                payload,
                recorded_bounds=recorded_bounds,
                current_bounds=current_bounds,
            )
            self._perform_tap(position, button)
            return

        if event.kind == "mouse_drag":
            button = deserialize_button(payload["button"])
            start_position = self._resolve_pointer_position(
                payload,
                recorded_bounds=recorded_bounds,
                current_bounds=current_bounds,
                x_key="start_x",
                y_key="start_y",
                normalized_x_key="start_normalized_x",
                normalized_y_key="start_normalized_y",
            )
            end_position = self._resolve_pointer_position(
                payload,
                recorded_bounds=recorded_bounds,
                current_bounds=current_bounds,
                x_key="end_x",
                y_key="end_y",
                normalized_x_key="end_normalized_x",
                normalized_y_key="end_normalized_y",
            )
            self._perform_drag(
                start_position,
                end_position,
                button,
                duration=float(payload.get("duration", 0.12)),
            )
            return

        if event.kind == "mouse_click":
            button = deserialize_button(payload["button"])
            self._mouse.position = self._resolve_pointer_position(
                payload,
                recorded_bounds=recorded_bounds,
                current_bounds=current_bounds,
            )
            if payload["pressed"]:
                self._mouse.press(button)
                self._pressed_buttons[button.name] = button
            else:
                self._mouse.release(button)
                self._pressed_buttons.pop(button.name, None)
            return

        if event.kind == "mouse_scroll":
            self._mouse.position = self._resolve_pointer_position(
                payload,
                recorded_bounds=recorded_bounds,
                current_bounds=current_bounds,
            )
            self._mouse.scroll(int(payload["dx"]), int(payload["dy"]))
            return

        if event.kind == "key_press":
            key_id = json.dumps(payload["key"], sort_keys=True)
            key = self._resolve_playback_key(payload["key"])
            self._keyboard.press(key)
            self._pressed_keys[key_id] = key
            return

        if event.kind == "key_release":
            key_id = json.dumps(payload["key"], sort_keys=True)
            key = self._pressed_keys.get(key_id)
            if key is None:
                key = self._resolve_playback_key(payload["key"])
            self._keyboard.release(key)
            self._pressed_keys.pop(key_id, None)
            return

        raise ValueError(f"Unsupported event kind: {event.kind}")

    def _perform_tap(self, position: tuple[int, int], button: mouse.Button) -> None:
        if self._stop_event.is_set():
            return

        self._mouse.position = position
        if self._stop_event.is_set():
            return

        self._mouse.press(button)
        self._pressed_buttons[button.name] = button
        try:
            self._wait_or_stop(0.01)
        finally:
            self._mouse.release(button)
            self._pressed_buttons.pop(button.name, None)

    def _perform_drag(
        self,
        start_position: tuple[int, int],
        end_position: tuple[int, int],
        button: mouse.Button,
        *,
        duration: float,
    ) -> None:
        if self._stop_event.is_set():
            return

        self._mouse.position = start_position
        if self._wait_or_stop(0.01):
            return
        if self._stop_event.is_set():
            return

        self._mouse.press(button)
        self._pressed_buttons[button.name] = button

        try:
            total_duration = max(duration, 0.02)
            steps = max(3, min(int(total_duration / 0.01), 60))
            start_x, start_y = start_position
            end_x, end_y = end_position

            for index in range(1, steps + 1):
                if self._stop_event.is_set():
                    break

                progress = index / steps
                next_x = round(start_x + (end_x - start_x) * progress)
                next_y = round(start_y + (end_y - start_y) * progress)
                self._mouse.position = (next_x, next_y)
                if self._wait_or_stop(total_duration / steps):
                    break
        finally:
            try:
                self._mouse.release(button)
            finally:
                self._pressed_buttons.pop(button.name, None)

    def _get_recorded_bounds(self, script: MacroScript) -> ScreenBounds:
        width, height = script.screen_size
        left, top = script.screen_origin
        return ScreenBounds(
            left=int(left),
            top=int(top),
            width=max(int(width), 1),
            height=max(int(height), 1),
        )

    def _resolve_pointer_position(
        self,
        payload: dict[str, object],
        *,
        recorded_bounds: ScreenBounds,
        current_bounds: ScreenBounds,
        x_key: str = "x",
        y_key: str = "y",
        normalized_x_key: str = "normalized_x",
        normalized_y_key: str = "normalized_y",
    ) -> tuple[int, int]:
        normalized_x = payload.get(normalized_x_key)
        normalized_y = payload.get(normalized_y_key)
        if isinstance(normalized_x, (int, float)) and isinstance(normalized_y, (int, float)):
            return denormalize_point(float(normalized_x), float(normalized_y), current_bounds)

        return scale_point(
            int(payload[x_key]),
            int(payload[y_key]),
            recorded_bounds,
            current_bounds,
        )

    def _release_pressed_inputs(self) -> None:
        for key in list(self._pressed_keys.values()):
            try:
                self._keyboard.release(key)
            except Exception:
                pass
        self._pressed_keys.clear()

        for button in list(self._pressed_buttons.values()):
            try:
                self._mouse.release(button)
            except Exception:
                pass
        self._pressed_buttons.clear()

    def _resolve_playback_key(self, data: dict[str, object]) -> keyboard.Key | keyboard.KeyCode:
        if data.get("type") == "char" and self._shortcut_modifier_active():
            vk = virtual_key_from_char(str(data.get("value", "")))
            if vk is not None:
                return keyboard.KeyCode.from_vk(vk)

        return deserialize_key(data)

    def _wait_or_stop(self, timeout: float) -> bool:
        wait_time = max(float(timeout), 0.0)
        if wait_time == 0:
            return self._stop_event.is_set()
        return bool(self._stop_event.wait(wait_time))

    def _shortcut_modifier_active(self) -> bool:
        return any(
            getattr(key, "name", None) in self._SHORTCUT_MODIFIER_NAMES
            for key in self._pressed_keys.values()
        )
