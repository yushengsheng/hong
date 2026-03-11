from __future__ import annotations

from typing import Any

from pynput import keyboard, mouse


def serialize_key(key: keyboard.Key | keyboard.KeyCode) -> dict[str, Any]:
    if isinstance(key, keyboard.KeyCode):
        if key.char is not None:
            return {"type": "char", "value": key.char}
        if key.vk is not None:
            return {"type": "vk", "value": key.vk}

    if isinstance(key, keyboard.Key):
        return {"type": "special", "value": key.name}

    return {"type": "repr", "value": str(key)}


def deserialize_key(data: dict[str, Any]) -> keyboard.Key | keyboard.KeyCode:
    key_type = data.get("type")
    value = data.get("value")

    if key_type == "char":
        return keyboard.KeyCode.from_char(value)
    if key_type == "vk":
        return keyboard.KeyCode.from_vk(int(value))
    if key_type == "special":
        return keyboard.Key[value]
    if key_type == "repr":
        return _deserialize_repr_key(str(value))

    raise ValueError(f"Unsupported key payload: {data!r}")


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
