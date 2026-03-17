from __future__ import annotations

from pathlib import Path

from .models import MacroEvent, MacroScript
from .script_text_constants import (
    PRESS_LABELS,
    TEXT_EVENTS_MARKER,
    TEXT_HEADER_COMMENTS,
    TEXT_KEY_EVENT_LABELS,
    TEXT_METADATA_KEYS,
    TEXT_MOUSE_DRAG,
    TEXT_MOUSE_SCROLL,
    TEXT_MOUSE_TAP,
)
from .script_text_legacy import simplify_events_for_text
from .script_text_read import script_from_text
from .script_text_shared import button_to_text, key_to_text, pointer_text_fields


def script_to_text(script: MacroScript, *, base_text: str | None = None) -> str:
    visible_events = simplify_events_for_text(script.events)
    metadata_values = build_text_metadata_values(script, visible_events=visible_events)
    event_lines = build_text_event_lines(visible_events)
    if base_text is not None:
        merged_lines = merge_script_text(
            base_text=base_text,
            script=script,
            metadata_values=metadata_values,
            fallback_event_lines=event_lines,
        )
        if merged_lines is not None:
            return join_text_lines(merged_lines)

    return join_text_lines(
        [
            *TEXT_HEADER_COMMENTS,
            "",
            *format_text_metadata_lines(metadata_values),
            "",
            TEXT_EVENTS_MARKER,
            *event_lines,
        ]
    )


def merge_script_text(
    *,
    base_text: str,
    script: MacroScript,
    metadata_values: dict[str, str],
    fallback_event_lines: list[str],
) -> list[str] | None:
    split_lines = split_text_sections(base_text)
    if split_lines is None:
        return None

    header_lines, preserved_event_lines = split_lines
    event_lines = preserved_event_lines if can_preserve_event_block(base_text, script) else fallback_event_lines
    return [
        *merge_header_lines(header_lines, metadata_values),
        TEXT_EVENTS_MARKER,
        *event_lines,
    ]


def build_text_metadata_values(script: MacroScript, *, visible_events: list[MacroEvent]) -> dict[str, str]:
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


def format_text_metadata_lines(metadata_values: dict[str, str]) -> list[str]:
    return [f"{key}: {metadata_values[key]}" for key in TEXT_METADATA_KEYS]


def build_text_event_lines(events: list[MacroEvent]) -> list[str]:
    lines: list[str] = []
    previous_offset = 0.0
    for event in events:
        interval = max(event.time_offset - previous_offset, 0.0)
        previous_offset = event.time_offset
        lines.append(event_to_text(event, interval=interval))
    return lines


def split_text_sections(text: str) -> tuple[list[str], list[str]] | None:
    source_lines = text.splitlines()
    marker_index = next((index for index, line in enumerate(source_lines) if line.strip() == TEXT_EVENTS_MARKER), None)
    if marker_index is None:
        return None
    return source_lines[:marker_index], source_lines[marker_index + 1 :]


def merge_header_lines(header_lines: list[str], metadata_values: dict[str, str]) -> list[str]:
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


def join_text_lines(lines: list[str]) -> str:
    return "\n".join(lines) + "\n"


def read_preserved_text_source(source: str | Path | None) -> str | None:
    if source is None:
        return None

    source_path = Path(source)
    if source_path.suffix.lower() != ".txt" or not source_path.exists():
        return None

    return source_path.read_text(encoding="utf-8")


def can_preserve_event_block(base_text: str, script: MacroScript) -> bool:
    try:
        source_script = script_from_text(base_text, default_name=script.name)
    except Exception:
        return False

    return source_script.events == script.events


def event_to_text(event: MacroEvent, *, interval: float) -> str:
    parts = [f"间隔={interval:.6f}"]
    payload = event.payload

    if event.kind in {"mouse_tap", "mouse_click"}:
        parts.append(TEXT_MOUSE_TAP)
        parts.extend(pointer_text_fields(payload))
        parts.append(f"按键={button_to_text(payload['button']['name'])}")
        if event.kind == "mouse_click":
            parts.append(f"动作={PRESS_LABELS[bool(payload['pressed'])]}")
        return " | ".join(parts)

    if event.kind == "mouse_drag":
        parts.append(TEXT_MOUSE_DRAG)
        parts.append(f"起点x={int(payload['start_x'])}")
        parts.append(f"起点y={int(payload['start_y'])}")
        parts.append(f"终点x={int(payload['end_x'])}")
        parts.append(f"终点y={int(payload['end_y'])}")
        parts.append(f"按键={button_to_text(payload['button']['name'])}")
        parts.append(f"耗时={float(payload.get('duration', 0.12)):.6f}")
        return " | ".join(parts)

    if event.kind == "mouse_scroll":
        parts.append(TEXT_MOUSE_SCROLL)
        parts.extend(pointer_text_fields(payload))
        parts.append(f"横向={int(payload['dx'])}")
        parts.append(f"纵向={int(payload['dy'])}")
        return " | ".join(parts)

    if event.kind in TEXT_KEY_EVENT_LABELS:
        parts.append(TEXT_KEY_EVENT_LABELS[event.kind])
        parts.append(f"按键={key_to_text(payload['key'])}")
        return " | ".join(parts)

    raise ValueError(f"不支持导出此事件类型：{event.kind}")
