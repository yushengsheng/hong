from __future__ import annotations

from .models import MacroEvent


def simplify_events_for_text(events: list[MacroEvent]) -> list[MacroEvent]:
    simplified: list[MacroEvent] = []
    index = 0

    while index < len(events):
        event = events[index]

        if event.kind == "mouse_move":
            index += 1
            continue

        if event.kind == "mouse_click" and "pressed" in event.payload:
            collapsed_event, next_index = collapse_legacy_mouse_action(events, index)
            if collapsed_event is not None:
                simplified.append(collapsed_event)
            index = next_index
            continue

        simplified.append(event)
        index += 1

    return simplified


def collapse_legacy_mouse_action(events: list[MacroEvent], start_index: int) -> tuple[MacroEvent | None, int]:
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
