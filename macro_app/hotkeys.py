from __future__ import annotations

import re

from pynput import keyboard as pynput_keyboard


class HotkeyParseError(ValueError):
    pass


MODIFIER_ORDER = ("<ctrl>", "<alt>", "<shift>", "<cmd>")

MODIFIER_ALIASES = {
    "ctrl": "<ctrl>",
    "control": "<ctrl>",
    "ctl": "<ctrl>",
    "alt": "<alt>",
    "option": "<alt>",
    "shift": "<shift>",
    "win": "<cmd>",
    "windows": "<cmd>",
    "cmd": "<cmd>",
    "super": "<cmd>",
    "meta": "<cmd>",
}

SPECIAL_KEY_ALIASES = {
    "esc": "<esc>",
    "escape": "<esc>",
    "tab": "<tab>",
    "space": "<space>",
    "enter": "<enter>",
    "return": "<enter>",
    "backspace": "<backspace>",
    "delete": "<delete>",
    "del": "<delete>",
    "insert": "<insert>",
    "ins": "<insert>",
    "home": "<home>",
    "end": "<end>",
    "pageup": "<page_up>",
    "page_up": "<page_up>",
    "pgup": "<page_up>",
    "pagedown": "<page_down>",
    "page_down": "<page_down>",
    "pgdn": "<page_down>",
    "up": "<up>",
    "down": "<down>",
    "left": "<left>",
    "right": "<right>",
}

DISPLAY_NAMES = {
    "<ctrl>": "Ctrl",
    "<alt>": "Alt",
    "<shift>": "Shift",
    "<cmd>": "Win",
    "<esc>": "Esc",
    "<tab>": "Tab",
    "<space>": "Space",
    "<enter>": "Enter",
    "<backspace>": "Backspace",
    "<delete>": "Delete",
    "<insert>": "Insert",
    "<home>": "Home",
    "<end>": "End",
    "<page_up>": "PgUp",
    "<page_down>": "PgDn",
    "<up>": "Up",
    "<down>": "Down",
    "<left>": "Left",
    "<right>": "Right",
}

TK_STATE_SHIFT = 0x0001
TK_STATE_CTRL = 0x0004
TK_STATE_ALT = 0x0008
TK_STATE_WIN = 0x0040


def normalize_hotkey(raw: str) -> tuple[str, str]:
    text = raw.strip().replace("＋", "+")
    if not text:
        return "", ""

    parts = [part.strip() for part in text.split("+")]
    if not parts or any(not part for part in parts):
        raise HotkeyParseError("快捷键格式不正确，请使用 Ctrl+Alt+1 这类格式。")

    modifiers: list[str] = []
    trigger_key: str | None = None
    seen_tokens: set[str] = set()

    for part in parts:
        token = _normalize_token(part)
        if token in seen_tokens:
            raise HotkeyParseError("快捷键里有重复按键。")
        seen_tokens.add(token)

        if token in MODIFIER_ORDER:
            modifiers.append(token)
            continue

        if trigger_key is not None:
            raise HotkeyParseError("当前只支持一个主键，例如 Ctrl+Alt+1。")
        trigger_key = token

    if trigger_key is None:
        raise HotkeyParseError("快捷键至少需要一个主键，例如 Ctrl+Alt+1。")
    if not modifiers:
        raise HotkeyParseError("全局快捷键至少需要一个修饰键，例如 Ctrl+Alt+1。")

    ordered_tokens = [token for token in MODIFIER_ORDER if token in modifiers]
    ordered_tokens.append(trigger_key)
    canonical = "+".join(ordered_tokens)

    try:
        pynput_keyboard.HotKey.parse(canonical)
    except Exception as exc:
        raise HotkeyParseError("这个快捷键当前无法识别，请换一个组合。") from exc

    display = "+".join(_display_token(token) for token in ordered_tokens)
    return canonical, display


def format_hotkey(raw: str) -> str:
    canonical, display = normalize_hotkey(raw)
    return display if canonical else ""


def hotkey_from_tk_event(keysym: str, state: int) -> tuple[str, str] | None:
    normalized_key = _normalize_tk_keysym(keysym)
    if normalized_key is None:
        return None

    modifiers = _modifier_tokens_from_tk_state(state)

    if not modifiers:
        raise HotkeyParseError("全局快捷键至少需要一个修饰键，例如 Ctrl+Alt+1。")

    return normalize_hotkey("+".join([*modifiers, normalized_key]))


def _normalize_token(raw_token: str) -> str:
    token = raw_token.strip()
    folded = token.casefold().replace(" ", "")
    if not folded:
        raise HotkeyParseError("快捷键里不能有空按键。")

    if folded in MODIFIER_ORDER or folded in DISPLAY_NAMES:
        return folded

    if folded in MODIFIER_ALIASES:
        return MODIFIER_ALIASES[folded]
    if folded in SPECIAL_KEY_ALIASES:
        return SPECIAL_KEY_ALIASES[folded]

    function_match = re.fullmatch(r"f([1-9]|1[0-9]|2[0-4])", folded)
    if function_match:
        return f"<f{function_match.group(1)}>"
    canonical_function_match = re.fullmatch(r"<f([1-9]|1[0-9]|2[0-4])>", folded)
    if canonical_function_match:
        return folded

    if len(token) == 1 and token.isascii() and token.isprintable() and token != "+":
        return token.lower()

    raise HotkeyParseError(f"不支持的按键：{raw_token}")


def _normalize_tk_keysym(keysym: str) -> str | None:
    folded = keysym.strip().casefold()
    if folded in {
        "control_l",
        "control_r",
        "shift_l",
        "shift_r",
        "alt_l",
        "alt_r",
        "win_l",
        "win_r",
        "super_l",
        "super_r",
        "meta_l",
        "meta_r",
    }:
        return None

    keysym_aliases = {
        "return": "Enter",
        "escape": "Esc",
        "backspace": "Backspace",
        "delete": "Delete",
        "insert": "Insert",
        "home": "Home",
        "end": "End",
        "prior": "PgUp",
        "next": "PgDn",
        "page_up": "PgUp",
        "page_down": "PgDn",
        "left": "Left",
        "right": "Right",
        "up": "Up",
        "down": "Down",
        "space": "Space",
        "tab": "Tab",
    }
    if folded in keysym_aliases:
        return keysym_aliases[folded]

    function_match = re.fullmatch(r"f([1-9]|1[0-9]|2[0-4])", folded)
    if function_match:
        return f"F{function_match.group(1)}"

    if len(keysym) == 1 and keysym.isascii() and keysym.isprintable() and keysym != "+":
        return keysym.upper()

    raise HotkeyParseError(f"不支持的按键：{keysym}")


def _modifier_tokens_from_tk_state(state: int) -> list[str]:
    modifiers: list[str] = []
    if state & TK_STATE_CTRL:
        modifiers.append("Ctrl")
    if state & TK_STATE_ALT:
        modifiers.append("Alt")
    if state & TK_STATE_SHIFT:
        modifiers.append("Shift")
    if state & TK_STATE_WIN:
        modifiers.append("Win")
    return modifiers


def _display_token(token: str) -> str:
    if token in DISPLAY_NAMES:
        return DISPLAY_NAMES[token]
    if token.startswith("<f") and token.endswith(">"):
        return token[1:-1].upper()
    if len(token) == 1:
        return token.upper()
    return token.strip("<>").replace("_", " ").title()
