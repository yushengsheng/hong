from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class MacroEvent:
    time_offset: float
    kind: str
    payload: dict[str, Any]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MacroEvent":
        return cls(
            time_offset=float(data["time_offset"]),
            kind=str(data["kind"]),
            payload=dict(data["payload"]),
        )


@dataclass(slots=True)
class MacroScript:
    name: str
    created_at: str
    screen_size: tuple[int, int]
    screen_origin: tuple[int, int] = (0, 0)
    default_loops: int = 1
    default_speed: float = 1.0
    global_hotkey: str = ""
    custom_order: int | None = None
    events: list[MacroEvent] = field(default_factory=list)
    version: int = 4

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["screen_size"] = list(self.screen_size)
        payload["screen_origin"] = list(self.screen_origin)
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MacroScript":
        return cls(
            name=str(data.get("name") or "macro"),
            created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
            screen_size=tuple(data.get("screen_size") or (0, 0)),
            screen_origin=tuple(data.get("screen_origin") or (0, 0)),
            default_loops=int(data.get("default_loops", 1)),
            default_speed=float(data.get("default_speed", 1.0)),
            global_hotkey=str(data.get("global_hotkey", "") or "").strip(),
            custom_order=_parse_optional_int(data.get("custom_order")),
            events=[MacroEvent.from_dict(item) for item in data.get("events", [])],
            version=int(data.get("version", 1)),
        )


def build_script(
    name: str,
    screen_size: tuple[int, int],
    events: list[MacroEvent],
    *,
    screen_origin: tuple[int, int] = (0, 0),
    default_loops: int = 1,
    default_speed: float = 1.0,
    global_hotkey: str = "",
    custom_order: int | None = None,
) -> MacroScript:
    return MacroScript(
        name=name,
        created_at=datetime.now(timezone.utc).isoformat(),
        screen_size=screen_size,
        screen_origin=screen_origin,
        default_loops=default_loops,
        default_speed=default_speed,
        global_hotkey=global_hotkey,
        custom_order=custom_order,
        events=events,
        version=4,
    )


def save_script(path: str | Path, script: MacroScript) -> None:
    target = Path(path)
    target.write_text(
        json.dumps(script.to_dict(), indent=2, ensure_ascii=True),
        encoding="utf-8",
    )


def load_script(path: str | Path) -> MacroScript:
    source = Path(path)
    return MacroScript.from_dict(json.loads(source.read_text(encoding="utf-8")))


def _parse_optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)
