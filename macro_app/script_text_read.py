from __future__ import annotations

from datetime import datetime, timezone

from .display import ScreenBounds
from .models import MacroEvent, MacroScript
from .script_text_constants import (
    PRESS_VALUES,
    TEXT_EVENTS_MARKER,
    TEXT_KEY_EVENT_KINDS,
    TEXT_MOUSE_DRAG,
    TEXT_MOUSE_SCROLL,
    TEXT_MOUSE_TAP,
)
from .script_text_shared import (
    button_from_text,
    drag_payload_from_fields,
    key_from_text,
    parse_fields,
    parse_int_pair,
    parse_optional_int,
    pointer_payload_from_fields,
)


def script_from_text(text: str, *, default_name: str) -> MacroScript:
    metadata: dict[str, str] = {}
    event_lines: list[str] = []
    in_events = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line == TEXT_EVENTS_MARKER:
            in_events = True
            continue

        if not in_events:
            key, separator, value = line.partition(":")
            if not separator:
                raise ValueError(f"无法解析头信息：{line}")
            metadata[key.strip()] = value.strip()
            continue

        event_lines.append(line)

    width, height = parse_int_pair(metadata.get("屏幕尺寸", "0,0"), field_name="屏幕尺寸")
    left, top = parse_int_pair(metadata.get("屏幕原点", "0,0"), field_name="屏幕原点")
    bounds = ScreenBounds(left=left, top=top, width=max(width, 1), height=max(height, 1))

    events: list[MacroEvent] = []
    current_time = 0.0
    for line in event_lines:
        event = event_from_text(line, bounds=bounds, previous_time=current_time)
        events.append(event)
        current_time = event.time_offset

    return MacroScript(
        name=metadata.get("名称") or default_name,
        created_at=metadata.get("创建时间") or datetime.now(timezone.utc).isoformat(),
        screen_size=(width, height),
        screen_origin=(left, top),
        default_loops=int(metadata.get("默认循环次数", "1")),
        default_speed=float(metadata.get("默认播放速度", "1.0")),
        global_hotkey=metadata.get("全局快捷键", "").strip(),
        custom_order=parse_optional_int(metadata.get("自定义排序", "").strip()),
        events=events,
        version=int(metadata.get("版本", "4")),
    )


def event_from_text(line: str, *, bounds: ScreenBounds, previous_time: float) -> MacroEvent:
    parts = [part.strip() for part in line.split("|")]
    if len(parts) < 2:
        raise ValueError(f"无法解析事件行：{line}")

    first_part = parts[0]
    if first_part.startswith("间隔="):
        interval = float(first_part.split("=", 1)[1].strip())
        time_offset = previous_time + interval
        kind_label = parts[1]
        field_parts = parts[2:]
    else:
        time_offset = float(first_part)
        kind_label = parts[1]
        field_parts = parts[2:]

    fields = parse_fields(field_parts)

    if kind_label == TEXT_MOUSE_TAP:
        payload = pointer_payload_from_fields(fields, bounds=bounds)
        payload["button"] = {"name": button_from_text(fields["按键"])}
        if "动作" in fields:
            payload["pressed"] = PRESS_VALUES[fields["动作"]]
            return MacroEvent(time_offset=time_offset, kind="mouse_click", payload=payload)
        return MacroEvent(time_offset=time_offset, kind="mouse_tap", payload=payload)

    if kind_label == TEXT_MOUSE_DRAG:
        payload = drag_payload_from_fields(fields, bounds=bounds)
        payload["button"] = {"name": button_from_text(fields["按键"])}
        payload["duration"] = float(fields.get("耗时", "0.12"))
        return MacroEvent(time_offset=time_offset, kind="mouse_drag", payload=payload)

    if kind_label == TEXT_MOUSE_SCROLL:
        payload = pointer_payload_from_fields(fields, bounds=bounds)
        payload["dx"] = int(fields["横向"])
        payload["dy"] = int(fields["纵向"])
        return MacroEvent(time_offset=time_offset, kind="mouse_scroll", payload=payload)

    if kind_label in TEXT_KEY_EVENT_KINDS:
        return MacroEvent(
            time_offset=time_offset,
            kind=TEXT_KEY_EVENT_KINDS[kind_label],
            payload={"key": key_from_text(fields["按键"])},
        )

    raise ValueError(f"不支持的事件类型：{kind_label}")
