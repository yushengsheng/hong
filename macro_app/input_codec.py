from __future__ import annotations

import ctypes
from ctypes import wintypes
from typing import Any

from pynput import keyboard, mouse


if hasattr(ctypes, "windll") and hasattr(ctypes.windll, "user32"):
    _VK_KEY_SCAN = ctypes.windll.user32.VkKeyScanW
    _VK_KEY_SCAN.argtypes = (wintypes.WCHAR,)
    _VK_KEY_SCAN.restype = ctypes.c_short
else:
    _VK_KEY_SCAN = None


def serialize_key(
    key: keyboard.Key | keyboard.KeyCode,
    *,
    prefer_vk: bool = False,
) -> dict[str, Any]:
    if isinstance(key, keyboard.KeyCode):
        if key.char is not None:
            normalized_char = _normalize_recorded_char(key.char)
            if prefer_vk:
                vk = key.vk if key.vk is not None else virtual_key_from_char(normalized_char)
                if vk is not None:
                    return {"type": "vk", "value": vk}
            return {"type": "char", "value": normalized_char}
        if key.vk is not None:
            return {"type": "vk", "value": key.vk}

    if isinstance(key, keyboard.Key):
        return {"type": "special", "value": key.name}

    return {"type": "repr", "value": str(key)}


def deserialize_key(data: dict[str, Any]) -> keyboard.Key | keyboard.KeyCode:
    key_type = data.get("type")
    value = data.get("value")

    if key_type == "char":
        return keyboard.KeyCode.from_char(_normalize_recorded_char(str(value)))
    if key_type == "vk":
        return keyboard.KeyCode.from_vk(int(value))
    if key_type == "special":
        return keyboard.Key[value]
    if key_type == "repr":
        return _deserialize_repr_key(str(value))

    raise ValueError(f"Unsupported key payload: {data!r}")


def virtual_key_from_char(value: str) -> int | None:
    normalized_value = _normalize_recorded_char(value)
    if len(normalized_value) != 1:
        return None

    if _VK_KEY_SCAN is not None:
        result = int(_VK_KEY_SCAN(normalized_value))
        if result != -1:
            return result & 0xFF

    upper_value = normalized_value.upper()
    if upper_value.isascii() and upper_value.isalnum():
        return ord(upper_value)

    return None


def serialize_button(button: mouse.Button) -> dict[str, str]:
    return {"name": button.name}


def deserialize_button(data: dict[str, str]) -> mouse.Button:
    return mouse.Button[data["name"]]


def _deserialize_repr_key(raw_value: str) -> keyboard.Key | keyboard.KeyCode:
    if raw_value.startswith("Key."):
        key_name = raw_value.split(".", 1)[1]
        return keyboard.Key[key_name]

    if len(raw_value) >= 2 and raw_value[0] == raw_value[-1] == "'":
        return keyboard.KeyCode.from_char(raw_value[1:-1])

    if len(raw_value) == 1:
        return keyboard.KeyCode.from_char(raw_value)

    if raw_value.isdigit():
        return keyboard.KeyCode.from_vk(int(raw_value))

    raise ValueError(f"Unsupported repr key payload: {raw_value!r}")


def _normalize_recorded_char(value: str) -> str:
    if len(value) != 1:
        return value

    code_point = ord(value)

    # Windows low-level hooks may report Ctrl+A..Ctrl+Z as ASCII control
    # characters (\x01..\x1a). Re-map them back to the printable base key so
    # playback can reproduce combinations like Ctrl+C and Ctrl+V correctly.
    if 1 <= code_point <= 26:
        return chr(code_point + 96)

    return value
