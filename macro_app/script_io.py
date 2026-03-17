from __future__ import annotations

import json
from pathlib import Path

from .models import MacroScript, load_script as load_script_json, save_script as save_script_json
from .script_text_read import script_from_text
from .script_text_write import read_preserved_text_source, script_to_text


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
        base_text = read_preserved_text_source(preserve_text_from)
        target.write_text(script_to_text(script, base_text=base_text), encoding="utf-8")
        return

    raise ValueError("仅支持 .txt 或 .json 格式。")


def load_script(path: str | Path) -> MacroScript:
    source = Path(path)
    suffix = source.suffix.lower()

    if suffix == ".json":
        return load_script_json(source)

    if suffix == ".txt":
        return script_from_text(source.read_text(encoding="utf-8"), default_name=source.stem)

    raw_text = source.read_text(encoding="utf-8")
    if raw_text.lstrip().startswith("{"):
        return MacroScript.from_dict(json.loads(raw_text))

    return script_from_text(raw_text, default_name=source.stem)
