from __future__ import annotations

from datetime import datetime
import math
import threading
import time
from typing import Callable

from pynput import keyboard, mouse

from .display import ScreenBounds, get_screen_bounds, normalize_point
from .input_codec import serialize_button, serialize_key
from .models import MacroEvent, MacroScript, build_script


class MacroRecorder:
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

    _ALL_MODIFIER_NAMES = _SHORTCUT_MODIFIER_NAMES | {
        "shift",
        "shift_l",
        "shift_r",
    }

    def __init__(
        self,
        *,
        on_stop_requested: Callable[[], None] | None = None,
        should_capture_pointer: Callable[[int, int], bool] | None = None,
        drag_threshold: int = 4,
    ) -> None:
        self._on_stop_requested = on_stop_requested
        self._should_capture_pointer = should_capture_pointer
        self._drag_threshold = drag_threshold

        self._mouse_listener: mouse.Listener | None = None
        self._keyboard_listener: keyboard.Listener | None = None
        self._lock = threading.Lock()
        self._events: list[MacroEvent] = []
        self._start_time = 0.0
        self._recording_bounds: ScreenBounds | None = None
        self._pressed_buttons: dict[str, dict[str, object]] = {}
        self._pressed_modifiers: set[str] = set()
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    @property
    def event_count(self) -> int:
        with self._lock:
            return len(self._events)

    def start(self) -> None:
        if self._active:
            raise RuntimeError("Recorder is already active")

        with self._lock:
            self._events = []

        self._pressed_buttons = {}
        self._pressed_modifiers = set()
        self._recording_bounds = get_screen_bounds()
        self._start_time = time.perf_counter()

        self._mouse_listener = mouse.Listener(
            on_move=self._on_move,
            on_click=self._on_click,
            on_scroll=self._on_scroll,
        )
        self._keyboard_listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )

        self._active = True
        self._mouse_listener.start()
        self._keyboard_listener.start()

    def stop(self) -> MacroScript:
        if not self._active:
            raise RuntimeError("Recorder is not active")

        self._active = False

        if self._mouse_listener is not None:
            self._mouse_listener.stop()
            self._mouse_listener.join(timeout=1.0)
            self._mouse_listener = None

        if self._keyboard_listener is not None:
            self._keyboard_listener.stop()
            self._keyboard_listener.join(timeout=1.0)
            self._keyboard_listener = None

        self._pressed_buttons = {}
        self._pressed_modifiers = set()

        with self._lock:
            events = list(self._events)

        name = f"macro-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        bounds = self._recording_bounds or get_screen_bounds()
        self._recording_bounds = None
        return build_script(
            name=name,
            screen_size=bounds.size,
            screen_origin=bounds.origin,
            events=events,
        )

    def _elapsed_time(self) -> float:
        return time.perf_counter() - self._start_time

    def _append_event(
        self,
        kind: str,
        payload: dict[str, object],
        *,
        time_offset: float | None = None,
    ) -> None:
        if not self._active:
            return

        event = MacroEvent(
            time_offset=self._elapsed_time() if time_offset is None else float(time_offset),
            kind=kind,
            payload=payload,
        )
        with self._lock:
            self._events.append(event)

    def _build_pointer_payload(self, x: int, y: int, **extra: object) -> dict[str, object]:
        bounds = self._recording_bounds or get_screen_bounds()
        normalized_x, normalized_y = normalize_point(x, y, bounds)

        payload: dict[str, object] = {
            "x": x,
            "y": y,
            "normalized_x": normalized_x,
            "normalized_y": normalized_y,
        }
        payload.update(extra)
        return payload

    def _build_drag_payload(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        *,
        button: dict[str, str],
        duration: float,
    ) -> dict[str, object]:
        bounds = self._recording_bounds or get_screen_bounds()
        start_normalized_x, start_normalized_y = normalize_point(start_x, start_y, bounds)
        end_normalized_x, end_normalized_y = normalize_point(end_x, end_y, bounds)

        return {
            "start_x": start_x,
            "start_y": start_y,
            "end_x": end_x,
            "end_y": end_y,
            "start_normalized_x": start_normalized_x,
            "start_normalized_y": start_normalized_y,
            "end_normalized_x": end_normalized_x,
            "end_normalized_y": end_normalized_y,
            "button": button,
            "duration": max(duration, 0.0),
        }

    def _should_capture_pointer_event(self, x: int, y: int) -> bool:
        if self._should_capture_pointer is None:
            return True

        try:
            return bool(self._should_capture_pointer(x, y))
        except Exception:
            return True

    def _on_move(self, x: int, y: int) -> None:
        if not self._pressed_buttons:
            return

        for state in self._pressed_buttons.values():
            state["last_x"] = x
            state["last_y"] = y
            distance = math.hypot(x - int(state["start_x"]), y - int(state["start_y"]))
            if distance >= self._drag_threshold:
                state["dragged"] = True

    def _on_click(self, x: int, y: int, button: mouse.Button, pressed: bool) -> None:
        button_name = button.name

        if pressed:
            if not self._should_capture_pointer_event(x, y):
                return

            self._pressed_buttons[button_name] = {
                "start_x": x,
                "start_y": y,
                "last_x": x,
                "last_y": y,
                "time_offset": self._elapsed_time(),
                "dragged": False,
            }
            return

        state = self._pressed_buttons.pop(button_name, None)
        if state is None:
            return

        if not self._should_capture_pointer_event(x, y):
            return

        start_x = int(state["start_x"])
        start_y = int(state["start_y"])
        last_x = int(state["last_x"])
        last_y = int(state["last_y"])
        start_offset = float(state["time_offset"])

        distance = math.hypot(x - start_x, y - start_y)
        dragged = bool(state["dragged"]) or distance >= self._drag_threshold

        if dragged:
            end_x = x if x != start_x or y != start_y else last_x
            end_y = y if x != start_x or y != start_y else last_y
            self._append_event(
                "mouse_drag",
                self._build_drag_payload(
                    start_x,
                    start_y,
                    end_x,
                    end_y,
                    button=serialize_button(button),
                    duration=self._elapsed_time() - start_offset,
                ),
                time_offset=start_offset,
            )
            return

        self._append_event(
            "mouse_tap",
            self._build_pointer_payload(
                x,
                y,
                button=serialize_button(button),
            ),
            time_offset=start_offset,
        )

    def _on_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        if not self._should_capture_pointer_event(x, y):
            return

        self._append_event(
            "mouse_scroll",
            self._build_pointer_payload(x, y, dx=dx, dy=dy),
        )

    def _on_press(self, key: keyboard.Key | keyboard.KeyCode) -> bool | None:
        if key == keyboard.Key.esc:
            if self._on_stop_requested is not None:
                threading.Thread(target=self._on_stop_requested, daemon=True).start()
            return False

        self._append_event(
            "key_press",
            {"key": serialize_key(key, prefer_vk=self._should_prefer_vk_for_key(key))},
        )
        self._update_pressed_modifiers(key, pressed=True)
        return None

    def _on_release(self, key: keyboard.Key | keyboard.KeyCode) -> bool | None:
        if key == keyboard.Key.esc:
            return False

        self._append_event(
            "key_release",
            {"key": serialize_key(key, prefer_vk=self._should_prefer_vk_for_key(key))},
        )
        self._update_pressed_modifiers(key, pressed=False)
        return None

    def _should_prefer_vk_for_key(self, key: keyboard.Key | keyboard.KeyCode) -> bool:
        return isinstance(key, keyboard.KeyCode) and any(
            name in self._SHORTCUT_MODIFIER_NAMES for name in self._pressed_modifiers
        )

    def _update_pressed_modifiers(
        self,
        key: keyboard.Key | keyboard.KeyCode,
        *,
        pressed: bool,
    ) -> None:
        modifier_name = self._modifier_name(key)
        if modifier_name is None:
            return

        if pressed:
            self._pressed_modifiers.add(modifier_name)
            return

        self._pressed_modifiers.discard(modifier_name)

    def _modifier_name(self, key: keyboard.Key | keyboard.KeyCode) -> str | None:
        if not isinstance(key, keyboard.Key):
            return None

        key_name = key.name
        if key_name in self._ALL_MODIFIER_NAMES:
            return key_name

        return None
