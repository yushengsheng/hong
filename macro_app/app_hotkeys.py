from __future__ import annotations

from pathlib import Path

from pynput import keyboard as pynput_keyboard

from .app_support import MacroLibraryItem
from .hotkeys import HotkeyParseError, normalize_hotkey


class MacroAppHotkeysMixin:
    def _suspend_global_hotkeys(self) -> None:
        self._global_hotkeys_suspended += 1
        self._stop_global_hotkey_listener()

    def _resume_global_hotkeys(self) -> None:
        if self._global_hotkeys_suspended > 0:
            self._global_hotkeys_suspended -= 1
        if self._global_hotkeys_suspended == 0:
            self._rebuild_global_hotkeys()

    def _find_hotkey_conflict(self, current_path: Path, canonical_hotkey: str) -> MacroLibraryItem | None:
        if not canonical_hotkey:
            return None

        for item in self.macro_items:
            if item.path == current_path:
                continue
            raw_hotkey = item.script.global_hotkey.strip()
            if not raw_hotkey:
                continue
            try:
                other_canonical, _ = normalize_hotkey(raw_hotkey)
            except HotkeyParseError:
                continue
            if other_canonical == canonical_hotkey:
                return item
        return None

    def _queue_hotkey_play(self, path: Path, hotkey_display: str) -> None:
        self.ui_queue.put(
            (
                "request_play_macro_hotkey",
                {"path": str(path), "hotkey": hotkey_display},
            )
        )

    def _handle_hotkey_play_request(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return

        raw_path = payload.get("path")
        if not raw_path:
            return

        hotkey_display = str(payload.get("hotkey") or "")
        path = Path(str(raw_path))
        if not path.exists():
            self._log(f"快捷键 {hotkey_display} 对应的宏文件不存在：{path.name}")
            self._refresh_macro_list()
            return

        if self._is_macro_interaction_locked():
            self._log(f"已按下快捷键 {hotkey_display}，但当前正在录制或播放，已忽略。")
            return

        self._log(f"已通过快捷键 {hotkey_display} 触发宏：{path.stem}")
        self.play_macro(path)

    def _rebuild_global_hotkeys(self) -> None:
        self._stop_global_hotkey_listener()

        hotkey_actions: dict[str, object] = {}
        seen_hotkeys: dict[str, str] = {}

        for item in self.macro_items:
            raw_hotkey = item.script.global_hotkey.strip()
            if not raw_hotkey:
                continue

            try:
                canonical_hotkey, display_hotkey = normalize_hotkey(raw_hotkey)
            except HotkeyParseError as exc:
                self._log(f"宏“{item.script.name}”的全局快捷键无效，已忽略：{exc}")
                continue

            conflict_name = seen_hotkeys.get(canonical_hotkey)
            if conflict_name is not None:
                self._log(
                    f"宏“{item.script.name}”的全局快捷键 {display_hotkey} 与“{conflict_name}”重复，已忽略。"
                )
                continue

            seen_hotkeys[canonical_hotkey] = item.script.name
            hotkey_actions[canonical_hotkey] = (
                lambda path=item.path, hotkey=display_hotkey: self._queue_hotkey_play(path, hotkey)
            )

        if not hotkey_actions:
            return

        listener: pynput_keyboard.GlobalHotKeys | None = None
        try:
            listener = pynput_keyboard.GlobalHotKeys(hotkey_actions)
            listener.start()
        except Exception as exc:
            if listener is not None:
                try:
                    listener.stop()
                except Exception:
                    pass
                try:
                    listener.join(timeout=1.0)
                except Exception:
                    pass
            self._global_hotkey_listener = None
            self._log(f"启动全局快捷键监听失败：{exc}")
            return

        self._global_hotkey_listener = listener

    def _stop_global_hotkey_listener(self) -> None:
        if self._global_hotkey_listener is None:
            return

        try:
            self._global_hotkey_listener.stop()
            self._global_hotkey_listener.join(timeout=1.0)
        except Exception:
            pass
        finally:
            self._global_hotkey_listener = None
