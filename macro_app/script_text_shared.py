from __future__ import annotations

from .display import ScreenBounds, normalize_point
from .script_text_constants import (
    BUTTON_LABELS,
    BUTTON_NAMES,
    VISIBLE_CHARACTERS,
    VISIBLE_CHARACTER_VALUES,
)


def pointer_payload_from_fields(fields: dict[str, str], *, bounds: ScreenBounds) -> dict[str, object]:
    x = int(fields["x"])
    y = int(fields["y"])
    normalized_x, normalized_y = normalize_point(x, y, bounds)

    return {
        "x": x,
        "y": y,
        "normalized_x": normalized_x,
        "normalized_y": normalized_y,
    }


def pointer_text_fields(payload: dict[str, object]) -> list[str]:
    return [
        f"x={int(payload['x'])}",
        f"y={int(payload['y'])}",
    ]


def drag_payload_from_fields(fields: dict[str, str], *, bounds: ScreenBounds) -> dict[str, object]:
    start_x = int(fields["起点x"])
    start_y = int(fields["起点y"])
    end_x = int(fields["终点x"])
    end_y = int(fields["终点y"])
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
    }


def parse_fields(parts: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in parts:
        key, separator, value = part.partition("=")
        if not separator:
            raise ValueError(f"无法解析字段：{part}")
        fields[key.strip()] = value.strip()
    return fields


def parse_int_pair(raw_value: str, *, field_name: str) -> tuple[int, int]:
    left_text, separator, right_text = raw_value.partition(",")
    if not separator:
        raise ValueError(f"{field_name} 格式应为 a,b")
    return int(left_text.strip()), int(right_text.strip())


def parse_optional_int(raw_value: str) -> int | None:
    if not raw_value:
        return None
    return int(raw_value)


def button_to_text(name: str) -> str:
    return BUTTON_LABELS.get(name, name)


def button_from_text(value: str) -> str:
    return BUTTON_NAMES.get(value, value)


def key_to_text(data: dict[str, object]) -> str:
    key_type = str(data["type"])
    value = data["value"]

    if key_type == "char":
        char_value = str(value)
        return f"字符:{VISIBLE_CHARACTERS.get(char_value, char_value)}"
    if key_type == "special":
        return f"特殊:{value}"
    if key_type == "vk":
        return f"虚拟键:{value}"

    return f"原样:{value}"


def key_from_text(value: str) -> dict[str, object]:
    prefix, separator, payload = value.partition(":")
    if not separator:
        raise ValueError(f"无法解析按键：{value}")

    if prefix == "字符":
        return {"type": "char", "value": VISIBLE_CHARACTER_VALUES.get(payload, payload)}
    if prefix == "特殊":
        return {"type": "special", "value": payload}
    if prefix == "虚拟键":
        return {"type": "vk", "value": int(payload)}
    if prefix == "原样":
        return {"type": "repr", "value": payload}

    raise ValueError(f"不支持的按键格式：{value}")
