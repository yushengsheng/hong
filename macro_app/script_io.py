from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from .display import ScreenBounds, normalize_point
from .models import MacroEvent, MacroScript, load_script as load_script_json, save_script as save_script_json


TEXT_HEADER = "# 宏脚本文本格式 v4"
TEXT_EVENTS_MARKER = "事件:"

TEXT_MOUSE_TAP = "鼠标点击"
TEXT_MOUSE_DRAG = "鼠标拖拽"
TEXT_MOUSE_SCROLL = "鼠标滚轮"
TEXT_KEY_PRESS = "键盘按下"
TEXT_KEY_RELEASE = "键盘松开"
TEXT_KEY_EVENT_LABELS = {
    "key_press": TEXT_KEY_PRESS,
    "key_release": TEXT_KEY_RELEASE,
}
TEXT_KEY_EVENT_KINDS = {value: key for key, value in TEXT_KEY_EVENT_LABELS.items()}

BUTTON_LABELS = {
    "left": "左键",
    "right": "右键",
    "middle": "中键",
    "x1": "侧键1",
    "x2": "侧键2",
}
BUTTON_NAMES = {value: key for key, value in BUTTON_LABELS.items()}

PRESS_LABELS = {
    True: "按下",
    False: "松开",
}
PRESS_VALUES = {value: key for key, value in PRESS_LABELS.items()}

VISIBLE_CHARACTERS = {
    " ": "<空格>",
    "\t": "<Tab>",
    "\n": "<换行>",
}
VISIBLE_CHARACTER_VALUES = {value: key for key, value in VISIBLE_CHARACTERS.items()}
TEXT_METADATA_KEYS = (
    "名称",
    "创建时间",
    "版本",
    "屏幕尺寸",
    "屏幕原点",
    "默认循环次数",
    "默认播放速度",
    "全局快捷键",
    "自定义排序",
    "事件数",
)
TEXT_HEADER_COMMENTS = (
    TEXT_HEADER,
    "# 每一行只保留一个动作节点，不写入鼠标移动轨迹。",
    "# “间隔”表示距离上一条动作的等待秒数。",
    "# “默认循环次数”和“默认播放速度”会在列表播放时直接生效。",
    "# “全局快捷键”格式示例：Ctrl+Alt+1 / Ctrl+Shift+F2。",
    "# “自定义排序”留空时按录制时间排序，填写数字时按数字从小到大排。",
    "# 修改 x/y 后，加载时会自动重算比例坐标，方便跨 1K、2K、4K 屏幕适配。",
    "# 键盘按键格式：字符:a / 特殊:enter / 虚拟键:13",
)


def save_script(
    path: str | Path,
    script: MacroScript,
    *,
    preserve_text_from: str | Path | None = None,
) -> None:
    target = Path(path)
    suffix = target.suffix.lower()

    if not suffix:
        target = target.with_suffix(".txt")
        suffix = ".txt"

    if suffix == ".json":
        save_script_json(target, script)
        return

    if suffix == ".txt":
        base_text = _read_preserved_text_source(preserve_text_from)
        target.write_text(_script_to_text(script, base_text=base_text), encoding="utf-8")
        return

    raise ValueError("仅支持 .txt 或 .json 格式。")


def load_script(path: str | Path) -> MacroScript:
    source = Path(path)
    suffix = source.suffix.lower()

    if suffix == ".json":
        return load_script_json(source)

    if suffix == ".txt":
        return _script_from_text(source.read_text(encoding="utf-8"), default_name=source.stem)

    raw_text = source.read_text(encoding="utf-8")
    if raw_text.lstrip().startswith("{"):
        return MacroScript.from_dict(json.loads(raw_text))

    return _script_from_text(raw_text, default_name=source.stem)


def _script_to_text(script: MacroScript, *, base_text: str | None = None) -> str:
    visible_events = _simplify_events_for_text(script.events)
    metadata_values = _build_text_metadata_values(script, visible_events=visible_events)
    event_lines = _build_text_event_lines(visible_events)
    if base_text is not None:
        merged_lines = _merge_script_text(
            base_text=base_text,
            script=script,
            metadata_values=metadata_values,
            fallback_event_lines=event_lines,
        )
        if merged_lines is not None:
            return _join_text_lines(merged_lines)

    return _join_text_lines(
        [
            *TEXT_HEADER_COMMENTS,
            "",
            *_format_text_metadata_lines(metadata_values),
            "",
            TEXT_EVENTS_MARKER,
            *event_lines,
        ]
    )


def _merge_script_text(
    *,
    base_text: str,
    script: MacroScript,
    metadata_values: dict[str, str],
    fallback_event_lines: list[str],
) -> list[str] | None:
    split_lines = _split_text_sections(base_text)
    if split_lines is None:
        return None

    header_lines, preserved_event_lines = split_lines
    event_lines = preserved_event_lines if _can_preserve_event_block(base_text, script) else fallback_event_lines
    return [
        *_merge_header_lines(header_lines, metadata_values),
        TEXT_EVENTS_MARKER,
        *event_lines,
    ]


def _build_text_metadata_values(script: MacroScript, *, visible_events: list[MacroEvent]) -> dict[str, str]:
    width, height = script.screen_size
    left, top = script.screen_origin
    return {
        "名称": script.name,
        "创建时间": script.created_at,
        "版本": str(script.version),
        "屏幕尺寸": f"{width},{height}",
        "屏幕原点": f"{left},{top}",
        "默认循环次数": str(script.default_loops),
        "默认播放速度": str(script.default_speed),
        "全局快捷键": script.global_hotkey,
        "自定义排序": "" if script.custom_order is None else str(script.custom_order),
        "事件数": str(len(visible_events)),
    }


def _format_text_metadata_lines(metadata_values: dict[str, str]) -> list[str]:
    return [f"{key}: {metadata_values[key]}" for key in TEXT_METADATA_KEYS]


def _build_text_event_lines(events: list[MacroEvent]) -> list[str]:
    lines: list[str] = []
    previous_offset = 0.0
    for event in events:
        interval = max(event.time_offset - previous_offset, 0.0)
        previous_offset = event.time_offset
        lines.append(_event_to_text(event, interval=interval))
    return lines


def _split_text_sections(text: str) -> tuple[list[str], list[str]] | None:
    source_lines = text.splitlines()
    marker_index = next((index for index, line in enumerate(source_lines) if line.strip() == TEXT_EVENTS_MARKER), None)
    if marker_index is None:
        return None
    return source_lines[:marker_index], source_lines[marker_index + 1 :]


def _merge_header_lines(header_lines: list[str], metadata_values: dict[str, str]) -> list[str]:
    merged_lines: list[str] = []
    seen_metadata_keys: set[str] = set()

    for raw_line in header_lines:
        stripped_line = raw_line.strip()
        if not stripped_line or stripped_line.startswith("#"):
            merged_lines.append(raw_line)
            continue

        key, separator, _value = stripped_line.partition(":")
        metadata_key = key.strip()
        if separator and metadata_key in metadata_values:
            merged_lines.append(f"{metadata_key}: {metadata_values[metadata_key]}")
            seen_metadata_keys.add(metadata_key)
            continue

        merged_lines.append(raw_line)

    missing_metadata_lines = [
        f"{key}: {metadata_values[key]}"
        for key in TEXT_METADATA_KEYS
        if key not in seen_metadata_keys
    ]
    if missing_metadata_lines:
        insert_at = len(merged_lines)
        while insert_at > 0 and not merged_lines[insert_at - 1].strip():
            insert_at -= 1
        merged_lines[insert_at:insert_at] = missing_metadata_lines

    return merged_lines


def _join_text_lines(lines: list[str]) -> str:
    return "\n".join(lines) + "\n"


def _read_preserved_text_source(source: str | Path | None) -> str | None:
    if source is None:
        return None

    source_path = Path(source)
    if source_path.suffix.lower() != ".txt" or not source_path.exists():
        return None

    return source_path.read_text(encoding="utf-8")


def _can_preserve_event_block(base_text: str, script: MacroScript) -> bool:
    try:
        source_script = _script_from_text(base_text, default_name=script.name)
    except Exception:
        return False

    return source_script.events == script.events


def _script_from_text(text: str, *, default_name: str) -> MacroScript:
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

    width, height = _parse_int_pair(metadata.get("屏幕尺寸", "0,0"), field_name="屏幕尺寸")
    left, top = _parse_int_pair(metadata.get("屏幕原点", "0,0"), field_name="屏幕原点")
    bounds = ScreenBounds(left=left, top=top, width=max(width, 1), height=max(height, 1))

    events: list[MacroEvent] = []
    current_time = 0.0
    for line in event_lines:
        event = _event_from_text(line, bounds=bounds, previous_time=current_time)
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
        custom_order=_parse_optional_int(metadata.get("自定义排序", "").strip()),
        events=events,
        version=int(metadata.get("版本", "4")),
    )


def _simplify_events_for_text(events: list[MacroEvent]) -> list[MacroEvent]:
    simplified: list[MacroEvent] = []
    index = 0

    while index < len(events):
        event = events[index]

        if event.kind == "mouse_move":
            index += 1
            continue

        if event.kind == "mouse_click" and "pressed" in event.payload:
            collapsed_event, next_index = _collapse_legacy_mouse_action(events, index)
            if collapsed_event is not None:
                simplified.append(collapsed_event)
            index = next_index
            continue

        simplified.append(event)
        index += 1

    return simplified


def _collapse_legacy_mouse_action(events: list[MacroEvent], start_index: int) -> tuple[MacroEvent | None, int]:
    start_event = events[start_index]
    payload = start_event.payload

    if not bool(payload.get("pressed")):
        return None, start_index + 1

    button_name = payload["button"]["name"]
    start_x = int(payload["x"])
    start_y = int(payload["y"])
    end_x = start_x
    end_y = start_y
    duration = 0.0
    moved = False

    for index in range(start_index + 1, len(events)):
        current_event = events[index]

        if current_event.kind == "mouse_move":
            end_x = int(current_event.payload["x"])
            end_y = int(current_event.payload["y"])
            moved = True
            continue

        if current_event.kind == "mouse_click" and current_event.payload["button"]["name"] == button_name:
            if bool(current_event.payload.get("pressed")):
                break

            end_x = int(current_event.payload["x"])
            end_y = int(current_event.payload["y"])
            duration = max(current_event.time_offset - start_event.time_offset, 0.0)

            if moved or end_x != start_x or end_y != start_y:
                return (
                    MacroEvent(
                        time_offset=start_event.time_offset,
                        kind="mouse_drag",
                        payload={
                            "start_x": start_x,
                            "start_y": start_y,
                            "end_x": end_x,
                            "end_y": end_y,
                            "button": {"name": button_name},
                            "duration": duration,
                        },
                    ),
                    index + 1,
                )

            return (
                MacroEvent(
                    time_offset=start_event.time_offset,
                    kind="mouse_tap",
                    payload={
                        "x": end_x,
                        "y": end_y,
                        "button": {"name": button_name},
                    },
                ),
                index + 1,
            )

        break

    return (
        MacroEvent(
            time_offset=start_event.time_offset,
            kind="mouse_tap",
            payload={
                "x": start_x,
                "y": start_y,
                "button": {"name": button_name},
            },
        ),
        start_index + 1,
    )


def _event_to_text(event: MacroEvent, *, interval: float) -> str:
    parts = [f"间隔={interval:.6f}"]
    payload = event.payload

    if event.kind in {"mouse_tap", "mouse_click"}:
        parts.append(TEXT_MOUSE_TAP)
        parts.extend(_pointer_text_fields(payload))
        parts.append(f"按键={_button_to_text(payload['button']['name'])}")
        if event.kind == "mouse_click":
            parts.append(f"动作={PRESS_LABELS[bool(payload['pressed'])]}")
        return " | ".join(parts)

    if event.kind == "mouse_drag":
        parts.append(TEXT_MOUSE_DRAG)
        parts.append(f"起点x={int(payload['start_x'])}")
        parts.append(f"起点y={int(payload['start_y'])}")
        parts.append(f"终点x={int(payload['end_x'])}")
        parts.append(f"终点y={int(payload['end_y'])}")
        parts.append(f"按键={_button_to_text(payload['button']['name'])}")
        parts.append(f"耗时={float(payload.get('duration', 0.12)):.6f}")
        return " | ".join(parts)

    if event.kind == "mouse_scroll":
        parts.append(TEXT_MOUSE_SCROLL)
        parts.extend(_pointer_text_fields(payload))
        parts.append(f"横向={int(payload['dx'])}")
        parts.append(f"纵向={int(payload['dy'])}")
        return " | ".join(parts)

    if event.kind in TEXT_KEY_EVENT_LABELS:
        parts.append(TEXT_KEY_EVENT_LABELS[event.kind])
        parts.append(f"按键={_key_to_text(payload['key'])}")
        return " | ".join(parts)

    raise ValueError(f"不支持导出此事件类型：{event.kind}")


def _event_from_text(line: str, *, bounds: ScreenBounds, previous_time: float) -> MacroEvent:
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

    fields = _parse_fields(field_parts)

    if kind_label == TEXT_MOUSE_TAP:
        payload = _pointer_payload_from_fields(fields, bounds=bounds)
        payload["button"] = {"name": _button_from_text(fields["按键"])}
        if "动作" in fields:
            payload["pressed"] = PRESS_VALUES[fields["动作"]]
            return MacroEvent(time_offset=time_offset, kind="mouse_click", payload=payload)
        return MacroEvent(time_offset=time_offset, kind="mouse_tap", payload=payload)

    if kind_label == TEXT_MOUSE_DRAG:
        payload = _drag_payload_from_fields(fields, bounds=bounds)
        payload["button"] = {"name": _button_from_text(fields["按键"])}
        payload["duration"] = float(fields.get("耗时", "0.12"))
        return MacroEvent(time_offset=time_offset, kind="mouse_drag", payload=payload)

    if kind_label == TEXT_MOUSE_SCROLL:
        payload = _pointer_payload_from_fields(fields, bounds=bounds)
        payload["dx"] = int(fields["横向"])
        payload["dy"] = int(fields["纵向"])
        return MacroEvent(time_offset=time_offset, kind="mouse_scroll", payload=payload)

    if kind_label in TEXT_KEY_EVENT_KINDS:
        return MacroEvent(
            time_offset=time_offset,
            kind=TEXT_KEY_EVENT_KINDS[kind_label],
            payload={"key": _key_from_text(fields["按键"])},
        )

    raise ValueError(f"不支持的事件类型：{kind_label}")


def _pointer_payload_from_fields(fields: dict[str, str], *, bounds: ScreenBounds) -> dict[str, object]:
    x = int(fields["x"])
    y = int(fields["y"])
    normalized_x, normalized_y = normalize_point(x, y, bounds)

    return {
        "x": x,
        "y": y,
        "normalized_x": normalized_x,
        "normalized_y": normalized_y,
    }


def _pointer_text_fields(payload: dict[str, object]) -> list[str]:
    return [
        f"x={int(payload['x'])}",
        f"y={int(payload['y'])}",
    ]


def _drag_payload_from_fields(fields: dict[str, str], *, bounds: ScreenBounds) -> dict[str, object]:
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


def _parse_fields(parts: list[str]) -> dict[str, str]:
    fields: dict[str, str] = {}
    for part in parts:
        key, separator, value = part.partition("=")
        if not separator:
            raise ValueError(f"无法解析字段：{part}")
        fields[key.strip()] = value.strip()
    return fields


def _parse_int_pair(raw_value: str, *, field_name: str) -> tuple[int, int]:
    left_text, separator, right_text = raw_value.partition(",")
    if not separator:
        raise ValueError(f"{field_name} 格式应为 a,b")
    return int(left_text.strip()), int(right_text.strip())


def _parse_optional_int(raw_value: str) -> int | None:
    if not raw_value:
        return None
    return int(raw_value)


def _button_to_text(name: str) -> str:
    return BUTTON_LABELS.get(name, name)


def _button_from_text(value: str) -> str:
    return BUTTON_NAMES.get(value, value)


def _key_to_text(data: dict[str, object]) -> str:
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


def _key_from_text(value: str) -> dict[str, object]:
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
