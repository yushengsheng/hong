from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import queue
import subprocess
import threading
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk
from uuid import uuid4

from pynput import keyboard as pynput_keyboard

from .display import ensure_dpi_awareness, format_display_profile
from .hotkeys import HotkeyParseError, format_hotkey, hotkey_from_tk_event, normalize_hotkey
from .models import MacroScript
from .player import MacroPlayer
from .recorder import MacroRecorder
from .runtime import get_runtime_root
from .script_io import load_script, save_script
from .ui_theme import UIFontSet, build_ui_fonts

ensure_dpi_awareness()

WINDOWS_RESERVED_FILENAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}


@dataclass(slots=True)
class MacroLibraryItem:
    path: Path
    script: MacroScript
    modified_at: float
    created_at_sort: float


class MacroApp:
    def __init__(self) -> None:
        self.project_root = get_runtime_root()
        self.macro_store_dir = self.project_root / "macros"
        self._startup_messages: list[str] = []
        self._ensure_macro_store_dir()

        self.root = tk.Tk()
        self.root.title("宏录制器")
        self.root.geometry("560x460")
        self.root.minsize(460, 420)
        self.ui_fonts = self._configure_ui_fonts()
        self._measure_fonts: dict[tuple[object, ...], tkfont.Font] = {}
        self.always_on_top_var = tk.BooleanVar(master=self.root, value=False)
        self._control_layout_mode = "wide"
        self._resizing_window_height = False

        self.recorder = MacroRecorder(
            on_stop_requested=self._handle_recorder_stop,
            should_capture_pointer=self._should_capture_pointer,
        )
        self.player = MacroPlayer()

        self.current_script: MacroScript | None = None
        self.current_path: Path | None = None
        self.macro_items: list[MacroLibraryItem] = []
        self.macro_row_controls: list[dict[str, object]] = []

        self.ui_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._window_bounds = (0, 0, 0, 0)

        self._arming = False
        self._playing = False
        self._stopping_record = False
        self._stopping_playback = False
        self._playing_path: Path | None = None
        self._playback_abort_listener: pynput_keyboard.Listener | None = None
        self._global_hotkey_listener: pynput_keyboard.GlobalHotKeys | None = None
        self._global_hotkeys_suspended = 0
        self._macro_store_signature: tuple[tuple[str, float, int], ...] = ()
        self._dragging_macro_path: Path | None = None
        self._drag_previous_status: str | None = None

        self._build_ui()
        self._refresh_macro_list()
        self._update_window_bounds()

        self.root.after(100, self._drain_ui_queue)
        self.root.after(1500, self._poll_macro_store)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Configure>", self._update_window_bounds)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill=tk.BOTH, expand=True)

        self.control_frame = ttk.LabelFrame(outer, text="控制")
        self.control_frame.pack(anchor=tk.W)

        self.top_section = ttk.Frame(self.control_frame)
        self.top_section.pack(fill=tk.X, padx=6, pady=6)
        self.top_section.columnconfigure(0, weight=1)
        self.top_section.columnconfigure(1, weight=0)

        self.stage_panel = tk.Frame(self.top_section, bg="#f8fafc", bd=1, relief=tk.SOLID)
        self.stage_panel.grid(row=0, column=0, sticky=tk.NSEW, padx=(0, 6))

        self.actions_panel = ttk.Frame(self.top_section)
        self.actions_panel.grid(row=0, column=1, sticky=tk.NW)

        self.record_button = ttk.Button(self.actions_panel, text="开始录制", command=self.start_recording, width=8)
        self.stop_record_button = ttk.Button(
            self.actions_panel,
            text="停止录制",
            command=lambda: self.stop_recording(trigger="button"),
            width=8,
        )
        self.stop_play_button = ttk.Button(
            self.actions_panel,
            text="停止播放",
            command=lambda: self.stop_playback(trigger="button"),
            width=8,
        )
        self.topmost_button = ttk.Checkbutton(
            self.actions_panel,
            text="置顶",
            variable=self.always_on_top_var,
            command=self._toggle_always_on_top,
        )
        self.actions_hint_label = ttk.Label(
            self.actions_panel,
            text="Esc: 停止录制 / 中断播放",
            font=self.ui_fonts.small,
        )

        self.record_button.grid(row=0, column=0, padx=(0, 4), pady=(0, 6), sticky=tk.W)
        self.stop_record_button.grid(row=0, column=1, padx=4, pady=(0, 6), sticky=tk.W)
        self.stop_play_button.grid(row=0, column=2, padx=(4, 0), pady=(0, 6), sticky=tk.W)
        self.topmost_button.grid(row=1, column=0, sticky=tk.W)
        self.actions_hint_label.grid(
            row=1,
            column=1,
            columnspan=2,
            sticky=tk.W,
            padx=(4, 0),
        )

        self.phase_var = tk.StringVar(value="待机")
        self.phase_hint_var = tk.StringVar(value="点击“开始录制”后，会先倒计时 3 秒。")
        self.status_var = tk.StringVar(value="空闲")

        self.phase_label = tk.Label(
            self.stage_panel,
            textvariable=self.phase_var,
            font=self.ui_fonts.stage,
            bg="#f8fafc",
            fg="#166534",
            padx=8,
            pady=5,
        )
        self.phase_label.grid(row=0, column=0, rowspan=2, sticky=tk.W)

        self.phase_status_caption_label = tk.Label(
            self.stage_panel,
            text="当前状态",
            font=self.ui_fonts.small,
            bg="#f8fafc",
            fg="#64748b",
        )
        self.phase_status_caption_label.grid(row=0, column=1, sticky=tk.W, pady=(8, 0))

        self.phase_status_value_label = tk.Label(
            self.stage_panel,
            textvariable=self.status_var,
            font=self.ui_fonts.body_bold,
            bg="#f8fafc",
            fg="#0f172a",
        )
        self.phase_status_value_label.grid(row=0, column=2, sticky=tk.W, padx=(8, 10), pady=(8, 0))

        self.phase_hint_label = tk.Label(
            self.stage_panel,
            textvariable=self.phase_hint_var,
            font=self.ui_fonts.small,
            bg="#f8fafc",
            fg="#475569",
            pady=4,
            justify=tk.LEFT,
            anchor="w",
            wraplength=220,
        )
        self.phase_hint_label.grid(row=1, column=1, columnspan=2, sticky=tk.EW, padx=(0, 10), pady=(2, 6))

        self.library_frame = ttk.LabelFrame(outer, text="宏列表")
        self.library_frame.pack(fill=tk.X, pady=(8, 0))

        list_container = ttk.Frame(self.library_frame)
        list_container.pack(fill=tk.X, padx=4, pady=4)

        self.macro_canvas = tk.Canvas(list_container, highlightthickness=0, borderwidth=0, height=64)
        self.macro_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)

        macro_scrollbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.macro_canvas.yview)
        macro_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.macro_canvas.configure(yscrollcommand=macro_scrollbar.set)

        self.macro_body = ttk.Frame(self.macro_canvas)
        self.macro_window_id = self.macro_canvas.create_window((0, 0), window=self.macro_body, anchor="nw")
        self.macro_body.bind("<Configure>", self._on_macro_body_configure)
        self.macro_canvas.bind("<Configure>", self._on_macro_canvas_configure)
        self.root.bind_all("<MouseWheel>", self._on_macro_mouse_wheel, add="+")

        self.log_frame = ttk.LabelFrame(outer, text="日志")
        self.log_frame.pack(fill=tk.X, pady=(8, 0))

        self.log_text = tk.Text(
            self.log_frame,
            wrap="word",
            state=tk.DISABLED,
            height=2,
            font=self.ui_fonts.small,
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        log_scrollbar = ttk.Scrollbar(self.log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)

        self._apply_responsive_layout(480)
        self._log(f"界面已就绪，当前屏幕：{format_display_profile()}。")
        self._flush_startup_messages()

    def _set_controls(self) -> None:
        recording = self._is_recording_busy()
        playing = self._is_playback_busy()
        locked = self._is_macro_interaction_locked()

        self.record_button.configure(state=tk.DISABLED if locked else tk.NORMAL)
        self.stop_record_button.configure(
            state=tk.NORMAL if self.recorder.active and not self._stopping_record else tk.DISABLED
        )
        self.stop_play_button.configure(state=tk.NORMAL if playing else tk.DISABLED)

        for row_controls in self.macro_row_controls:
            play_button = row_controls["play"]
            settings_button = row_controls["settings"]
            play_button.configure(state=tk.DISABLED if locked else tk.NORMAL)
            settings_button.configure(state=tk.DISABLED if locked else tk.NORMAL)

    def _is_recording_busy(self) -> bool:
        return bool(self.recorder.active or self._stopping_record)

    def _is_playback_busy(self) -> bool:
        return bool(self.player.active or self._playing or self._stopping_playback)

    def _is_macro_interaction_locked(self) -> bool:
        return bool(self._is_recording_busy() or self._is_playback_busy() or self._arming)

    def _is_record_start_blocked(self) -> bool:
        return bool(self.recorder.active or self.player.active or self._playing or self._arming)

    def _is_path_playing(self, path: Path) -> bool:
        return bool(self._playing_path == path and self._is_playback_busy())

    def _configure_ui_fonts(self) -> UIFontSet:
        available_families = set(tkfont.families(self.root))
        ui_fonts = build_ui_fonts(available_families)
        actual_family = ui_fonts.family
        if actual_family == "TkDefaultFont":
            actual_family = str(tkfont.nametofont("TkDefaultFont").cget("family"))

        resolved_fonts = UIFontSet(
            family=actual_family,
            small=(actual_family, ui_fonts.small[1]),
            body=(actual_family, ui_fonts.body[1]),
            body_bold=(actual_family, ui_fonts.body_bold[1], ui_fonts.body_bold[2]),
            title=(actual_family, ui_fonts.title[1], ui_fonts.title[2]),
            stage=(actual_family, ui_fonts.stage[1], ui_fonts.stage[2]),
        )
        ttk_style = ttk.Style(self.root)
        ttk_style.configure(".", font=resolved_fonts.body)
        ttk_style.configure("TLabelframe.Label", font=resolved_fonts.body_bold)

        named_font_specs = {
            "TkDefaultFont": resolved_fonts.body,
            "TkTextFont": resolved_fonts.body,
            "TkMenuFont": resolved_fonts.body,
            "TkHeadingFont": resolved_fonts.body_bold,
            "TkCaptionFont": resolved_fonts.small,
            "TkSmallCaptionFont": resolved_fonts.small,
            "TkIconFont": resolved_fonts.small,
            "TkTooltipFont": resolved_fonts.small,
        }

        for name, spec in named_font_specs.items():
            try:
                named_font = tkfont.nametofont(name)
            except tk.TclError:
                continue

            named_font.configure(
                family=spec[0],
                size=spec[1],
                weight=spec[2] if len(spec) > 2 else "normal",
            )

        return resolved_fonts

    def _ensure_macro_store_dir(self) -> None:
        self.macro_store_dir.mkdir(exist_ok=True)

        migrated_files = 0
        for pattern in ("*.txt", "*.json"):
            for path in self.project_root.glob(pattern):
                if not self._is_macro_file_path(path) or not self._is_legacy_macro_file(path):
                    continue

                target_path = self._unique_macro_path(path.stem, suffix=path.suffix or ".txt")
                try:
                    path.replace(target_path)
                except Exception as exc:
                    self._startup_messages.append(f"迁移旧宏失败：{path.name}，{exc}")
                    continue

                migrated_files += 1
                self._startup_messages.append(f"已迁移旧宏到 macros：{target_path.name}")

        if migrated_files and not self._startup_messages:
            self._startup_messages.append(f"已迁移 {migrated_files} 个旧宏到 macros。")

    def _is_legacy_macro_file(self, path: Path) -> bool:
        try:
            raw_text = path.read_text(encoding="utf-8")
        except Exception:
            return False

        suffix = path.suffix.lower()
        if suffix == ".txt":
            return raw_text.lstrip().startswith("# 宏脚本文本格式")
        if suffix == ".json":
            try:
                payload = json.loads(raw_text)
            except json.JSONDecodeError:
                return False
            return isinstance(payload, dict) and "events" in payload and "screen_size" in payload
        return False

    def _flush_startup_messages(self) -> None:
        for message in self._startup_messages:
            self._log(message)
        self._startup_messages.clear()

    def _is_macro_file_path(self, path: Path) -> bool:
        if not path.is_file():
            return False
        if path.suffix.lower() not in {".txt", ".json"}:
            return False
        if path.name.startswith("."):
            return False
        return True

    def _suspend_global_hotkeys(self) -> None:
        self._global_hotkeys_suspended += 1
        self._stop_global_hotkey_listener()

    def _resume_global_hotkeys(self) -> None:
        if self._global_hotkeys_suspended > 0:
            self._global_hotkeys_suspended -= 1
        if self._global_hotkeys_suspended == 0:
            self._rebuild_global_hotkeys()

    def _toggle_always_on_top(self) -> None:
        enabled = bool(self.always_on_top_var.get())
        try:
            self.root.attributes("-topmost", enabled)
        except tk.TclError:
            self.always_on_top_var.set(False)
            return

        self._log("已开启窗口置顶。" if enabled else "已取消窗口置顶。")

    def _apply_responsive_layout(self, width: int) -> None:
        layout_mode = "stacked" if width < 700 else "wide"
        if layout_mode != self._control_layout_mode:
            self._control_layout_mode = layout_mode
            if layout_mode == "stacked":
                self.top_section.columnconfigure(0, weight=0)
                self.top_section.columnconfigure(1, weight=0)
                self.stage_panel.grid_configure(row=0, column=0, sticky=tk.W, padx=0, pady=(0, 6))
                self.actions_panel.grid_configure(row=1, column=0, sticky=tk.W, padx=0, pady=0)
            else:
                self.top_section.columnconfigure(0, weight=1)
                self.top_section.columnconfigure(1, weight=0)
                self.stage_panel.grid_configure(row=0, column=0, sticky=tk.EW, padx=(0, 6), pady=0)
                self.actions_panel.grid_configure(row=0, column=1, sticky=tk.NW, padx=0, pady=0)

        if layout_mode == "stacked":
            wraplength = max(min(width - 210, 320), 180)
        else:
            wraplength = max(min((width // 2) - 110, 320), 180)
        self.phase_hint_label.configure(wraplength=wraplength)

    def _update_window_bounds(self, _event: object | None = None) -> None:
        try:
            if self.root.state() == "iconic":
                self._window_bounds = (0, 0, 0, 0)
                return
        except tk.TclError:
            return

        self.root.update_idletasks()
        left = int(self.root.winfo_rootx())
        top = int(self.root.winfo_rooty())
        width = int(self.root.winfo_width())
        height = int(self.root.winfo_height())
        self._window_bounds = (left, top, width, height)
        self._apply_responsive_layout(width)

    def _should_capture_pointer(self, x: int, y: int) -> bool:
        left, top, width, height = self._window_bounds
        if width <= 1 or height <= 1:
            return True
        return not (left <= x < left + width and top <= y < top + height)

    def _on_macro_body_configure(self, _event: object | None = None) -> None:
        self.macro_canvas.configure(scrollregion=self.macro_canvas.bbox("all"))
        self._update_macro_list_view_height()

    def _on_macro_canvas_configure(self, event: tk.Event[tk.Canvas]) -> None:
        self.macro_canvas.itemconfigure(self.macro_window_id, width=event.width)
        self._refresh_macro_row_layouts(event.width)

    def _on_macro_mouse_wheel(self, event: tk.Event[tk.Canvas]) -> str | None:
        if not self.macro_items or not self._is_pointer_over_widget(self.macro_canvas):
            return None
        self.macro_canvas.yview_scroll(-int(event.delta / 120), "units")
        return "break"

    def _is_pointer_over_widget(self, widget: tk.Misc) -> bool:
        try:
            pointer_x, pointer_y = self.root.winfo_pointerxy()
            hovered_widget = self.root.winfo_containing(pointer_x, pointer_y)
        except tk.TclError:
            return False

        while hovered_widget is not None:
            if hovered_widget == widget:
                return True
            hovered_widget = hovered_widget.master
        return False

    def _set_phase(self, title: str, hint: str, color: str) -> None:
        self.phase_var.set(title)
        self.phase_hint_var.set(hint)
        self.phase_label.configure(fg=color)

    def _set_status_phase(self, status: str, title: str, hint: str, color: str) -> None:
        self.status_var.set(status)
        self._set_phase(title, hint, color)

    def _reset_playback_state(self) -> None:
        self._playing = False
        self._stopping_playback = False
        self._playing_path = None
        self._stop_playback_abort_listener()

    def _clear_current_selection(self) -> None:
        self.current_path = None
        self.current_script = None

    def _drain_ui_queue(self) -> None:
        while True:
            try:
                message, payload = self.ui_queue.get_nowait()
            except queue.Empty:
                break

            if message == "request_stop_recording":
                self.stop_recording(trigger=str(payload))
                continue

            if message == "request_stop_playback":
                self.stop_playback(trigger=str(payload))
                continue

            if message == "request_play_macro_hotkey":
                self._handle_hotkey_play_request(payload)
                continue

            if message == "recording_finished":
                script = payload
                assert isinstance(script, MacroScript)
                self._handle_recording_finished(script)
                continue

            if message == "playback_finished":
                self._handle_playback_finished(payload)
                continue

            if message == "error":
                text = str(payload)
                self._reset_playback_state()
                self._stopping_record = False
                self._set_status_phase("出错", "出错", "请查看日志内容，修正后再重试。", "#b91c1c")
                self._log(text)
                messagebox.showerror("错误", text)
                self._refresh_macro_list()
                continue

        self.root.after(100, self._drain_ui_queue)

    def _handle_recording_finished(self, script: MacroScript) -> None:
        self._stopping_record = False

        if not script.events:
            self._clear_current_selection()
            self._set_status_phase("录制结果为空", "未保存", "本次没有捕获到动作节点，因此没有自动保存。", "#92400e")
            self._log("录制完成，但没有捕获到动作节点，未自动保存。")
            self._refresh_macro_list()
            return

        try:
            path = self._auto_save_recorded_macro(script)
        except Exception as exc:
            self.ui_queue.put(("error", f"自动保存录制宏失败：{exc}"))
            return

        self.current_script = script
        self.current_path = path
        self._set_status_phase("录制完成并已保存", "录制完成", "宏已自动保存，现在可以直接在列表中播放或设置。", "#166534")
        self._log(f"录制完成，共捕获 {len(script.events)} 个事件，已自动保存：{path.name}")
        self._refresh_macro_list()

    def _handle_playback_finished(self, payload: object) -> None:
        detail = "播放完成"
        played_path: Path | None = None

        if isinstance(payload, dict):
            detail = str(payload.get("detail", detail))
            raw_path = payload.get("path")
            if raw_path:
                played_path = Path(str(raw_path))
        else:
            detail = str(payload)

        self._reset_playback_state()

        if played_path is not None:
            self.current_path = played_path
            script = self._load_macro_file(played_path, show_error=False)
            if script is not None:
                self.current_script = script

        if detail == "播放完成":
            self._set_status_phase(detail, "播放完成", "本次回放已结束，可以在列表中再次播放。", "#166534")
        else:
            self._set_status_phase(detail, "播放已停止", "回放已中断，可以重新开始。", "#92400e")
        self._log(detail)
        self._refresh_macro_list()

    def _log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _refresh_macro_list(self) -> None:
        self.macro_items = self._collect_macro_items()
        self._macro_store_signature = self._get_macro_store_signature()
        self._sync_current_script_from_current_path()
        if self._global_hotkeys_suspended == 0:
            self._rebuild_global_hotkeys()
        self._render_macro_list()
        self._set_controls()

    def _sync_current_script_from_current_path(self) -> None:
        if self.current_path is None:
            return

        if not self.current_path.exists():
            self._clear_current_selection()
            return

        current_script = self._load_macro_file(self.current_path, show_error=False)
        if current_script is None:
            self._clear_current_selection()
            return

        self.current_script = current_script

    def _poll_macro_store(self) -> None:
        try:
            latest_signature = self._get_macro_store_signature()
            if latest_signature != self._macro_store_signature:
                self._refresh_macro_list()
        except Exception as exc:
            self._log(f"扫描宏目录时发生变化，已忽略本次刷新：{exc}")
        finally:
            self.root.after(1500, self._poll_macro_store)

    def _get_macro_store_signature(self) -> tuple[tuple[str, float, int], ...]:
        entries: list[tuple[str, float, int]] = []
        for path in self._iter_macro_store_paths():
            try:
                stat = path.stat()
            except OSError:
                continue
            entries.append((path.name.lower(), stat.st_mtime, stat.st_size))
        return tuple(sorted(entries))

    def _collect_macro_items(self) -> list[MacroLibraryItem]:
        candidates = self._iter_macro_store_paths()

        items: list[MacroLibraryItem] = []
        for path in sorted(candidates, key=lambda item: item.name.lower()):
            script = self._load_macro_file(path, show_error=False)
            if script is None:
                continue
            try:
                modified_at = path.stat().st_mtime
            except OSError:
                continue
            created_at_sort = self._parse_created_at_sort_key(script.created_at)
            items.append(
                MacroLibraryItem(
                    path=path,
                    script=script,
                    modified_at=modified_at,
                    created_at_sort=created_at_sort,
                )
            )
        return sorted(
            items,
            key=lambda item: (
                item.script.custom_order is None,
                item.script.custom_order if item.script.custom_order is not None else 0,
                item.created_at_sort,
                item.path.name.lower(),
            ),
        )

    def _iter_macro_store_paths(self) -> list[Path]:
        try:
            candidates = list(self.macro_store_dir.iterdir())
        except FileNotFoundError:
            self.macro_store_dir.mkdir(exist_ok=True)
            return []
        except OSError:
            return []

        return [path for path in candidates if self._is_macro_file_path(path)]

    def _render_macro_list(self) -> None:
        for child in self.macro_body.winfo_children():
            child.destroy()

        self.macro_row_controls = []

        if not self.macro_items:
            empty_label = ttk.Label(
                self.macro_body,
                text="还没有可用的宏。点击上方“开始录制”即可自动生成并保存。",
                padding=(8, 16),
            )
            empty_label.pack(fill=tk.X)
            self.root.after_idle(self._sync_macro_list_layout)
            return

        for item in self.macro_items:
            row = ttk.Frame(self.macro_body, padding=(8, 8))
            row.pack(fill=tk.X)
            row.columnconfigure(0, weight=1)

            tags: list[str] = []
            if self.current_path == item.path:
                tags.append("当前")
            if self._is_path_playing(item.path):
                tags.append("播放中")

            info_parts = [
                f"事件 {len(item.script.events)}",
                f"循环 {self._format_loops(item.script.default_loops)}",
                f"速度 {item.script.default_speed:g}x",
            ]
            if tags:
                info_parts.append(f"状态 {' / '.join(tags)}")

            content_frame = ttk.Frame(row)
            content_frame.grid(row=0, column=0, sticky=tk.EW, padx=(0, 12))
            content_frame.columnconfigure(0, weight=1)

            buttons_frame = ttk.Frame(row)
            buttons_frame.grid(row=0, column=1, sticky=tk.NE)

            title_label = ttk.Label(content_frame, text=item.script.name, font=self.ui_fonts.title, anchor=tk.W)
            title_label.grid(row=0, column=0, sticky=tk.EW)

            drag_handle = tk.Label(
                buttons_frame,
                text="排序",
                font=self.ui_fonts.small,
                fg="#64748b",
                cursor="fleur",
                padx=4,
                pady=1,
            )
            drag_handle.pack(side=tk.LEFT, padx=(0, 4))
            drag_handle.bind("<ButtonPress-1>", lambda event, path=item.path: self._start_macro_drag(event, path))

            play_button = ttk.Button(
                buttons_frame,
                text="播放",
                width=5,
                command=lambda path=item.path: self.play_macro(path),
            )
            settings_button = ttk.Button(
                buttons_frame,
                text="设置",
                width=5,
                command=lambda path=item.path: self.open_macro_settings(path),
            )
            play_button.pack(side=tk.LEFT, padx=(0, 4))
            settings_button.pack(side=tk.LEFT)

            detail_text = f"{'  ·  '.join(info_parts)}\n文件：{item.path.name}"
            detail_label = ttk.Label(
                content_frame,
                text=detail_text,
                font=self.ui_fonts.small,
                justify=tk.LEFT,
                anchor=tk.W,
            )
            detail_label.grid(row=1, column=0, sticky=tk.EW, pady=(4, 0))

            self.macro_row_controls.append(
                {
                    "play": play_button,
                    "settings": settings_button,
                    "drag": drag_handle,
                    "path": item.path,
                    "row": row,
                    "title": title_label,
                    "detail": detail_label,
                    "title_text": item.script.name,
                    "detail_text": detail_text,
                }
            )

            separator = ttk.Separator(self.macro_body, orient=tk.HORIZONTAL)
            separator.pack(fill=tk.X, pady=(0, 2))

        self.root.after_idle(self._sync_macro_list_layout)

    def _refresh_macro_row_layouts(self, width: int | None = None) -> None:
        if not self.macro_row_controls:
            return

        text_width = self._get_macro_text_wraplength(width)
        title_width = max(text_width, 140)

        for row_controls in self.macro_row_controls:
            title_label = row_controls.get("title")
            detail_label = row_controls.get("detail")
            title_text = str(row_controls.get("title_text", ""))
            detail_text = str(row_controls.get("detail_text", ""))

            if isinstance(title_label, ttk.Label):
                title_label.configure(text=self._truncate_text_to_width(title_text, title_width, self.ui_fonts.title))
            if isinstance(detail_label, ttk.Label):
                detail_label.configure(wraplength=text_width, text=detail_text)

    def _get_macro_text_wraplength(self, width: int | None = None) -> int:
        canvas_width = width or self.macro_canvas.winfo_width() or self.macro_canvas.winfo_reqwidth() or 420
        return max(min(int(canvas_width) - 150, 440), 220)

    def _truncate_text_to_width(self, text: str, max_width: int, font_spec: tuple[str, ...]) -> str:
        display_font = self._get_measure_font(font_spec)
        if display_font.measure(text) <= max_width:
            return text

        ellipsis = "..."
        available_width = max_width - display_font.measure(ellipsis)
        if available_width <= 0:
            return ellipsis

        trimmed = text
        while trimmed and display_font.measure(trimmed) > available_width:
            trimmed = trimmed[:-1]
        return f"{trimmed.rstrip()}{ellipsis}"

    def _get_measure_font(self, font_spec: tuple[str, ...]) -> tkfont.Font:
        cache = getattr(self, "_measure_fonts", None)
        if cache is None:
            cache = {}
            self._measure_fonts = cache

        cache_key = tuple(font_spec)
        display_font = cache.get(cache_key)
        if display_font is None:
            display_font = tkfont.Font(font=font_spec)
            cache[cache_key] = display_font
        return display_font

    def _sync_macro_list_layout(self) -> None:
        self._update_macro_list_view_height()
        self._fit_window_height_to_content()

    def _update_macro_list_view_height(self) -> None:
        children = self.macro_body.winfo_children()
        if not children:
            desired_height = 64
        elif not self.macro_items:
            desired_height = max(children[0].winfo_reqheight(), 48) + 4
        else:
            visible_items = min(len(self.macro_items), 5)
            desired_height = 4
            child_index = 0
            item_count = 0
            while child_index < len(children) and item_count < visible_items:
                desired_height += max(children[child_index].winfo_reqheight(), children[child_index].winfo_height())
                child_index += 1
                if child_index < len(children):
                    desired_height += max(children[child_index].winfo_reqheight(), children[child_index].winfo_height())
                    child_index += 1
                item_count += 1

        current_height = int(float(self.macro_canvas.cget("height")))
        if current_height != desired_height:
            self.macro_canvas.configure(height=desired_height)

    def _fit_window_height_to_content(self) -> None:
        if self._resizing_window_height:
            return
        try:
            if self.root.state() in {"zoomed", "iconic"}:
                return
        except tk.TclError:
            return

        self.root.update_idletasks()
        desired_height = max(self.root.winfo_reqheight(), 420)
        desired_height = min(desired_height, self.root.winfo_screenheight() - 120)
        current_height = max(int(self.root.winfo_height()), 1)
        if abs(current_height - desired_height) <= 2:
            return

        current_width = max(int(self.root.winfo_width()), 400)
        x = int(self.root.winfo_x())
        y = int(self.root.winfo_y())
        self._resizing_window_height = True
        self.root.geometry(f"{current_width}x{desired_height}+{x}+{y}")
        self.root.after_idle(self._finish_window_height_resize)

    def _finish_window_height_resize(self) -> None:
        self._resizing_window_height = False

    def _parse_created_at_sort_key(self, created_at: str) -> float:
        try:
            return datetime.fromisoformat(created_at).timestamp()
        except (TypeError, ValueError):
            return float("inf")

    def _start_macro_drag(self, _event: tk.Event[tk.Label], path: Path) -> str:
        if self._is_macro_interaction_locked():
            return "break"
        if len(self.macro_items) <= 1:
            return "break"

        self._drag_previous_status = self.status_var.get()
        self._dragging_macro_path = path
        self.root.bind("<B1-Motion>", self._on_macro_drag_motion)
        self.root.bind("<ButtonRelease-1>", self._finish_macro_drag)
        self.status_var.set("拖动中")
        return "break"

    def _on_macro_drag_motion(self, _event: tk.Event[tk.Misc]) -> None:
        return None

    def _finish_macro_drag(self, event: tk.Event[tk.Misc]) -> None:
        self.root.unbind("<B1-Motion>")
        self.root.unbind("<ButtonRelease-1>")
        if self._drag_previous_status is not None:
            self.status_var.set(self._drag_previous_status)
            self._drag_previous_status = None

        if self._dragging_macro_path is None:
            return

        dragged_path = self._dragging_macro_path
        self._dragging_macro_path = None
        target_index = self._get_macro_drop_index(dragged_path, event.y_root)
        if target_index is None:
            return

        source_index = next((index for index, item in enumerate(self.macro_items) if item.path == dragged_path), None)
        if source_index is None:
            return

        reordered_items = [item for item in self.macro_items if item.path != dragged_path]
        if target_index > len(reordered_items):
            target_index = len(reordered_items)
        dragged_item = self.macro_items[source_index]
        reordered_items.insert(target_index, dragged_item)

        if [item.path for item in reordered_items] == [item.path for item in self.macro_items]:
            return

        self.macro_items = reordered_items
        self._persist_macro_order()

    def _get_macro_drop_index(self, dragged_path: Path, y_root: int) -> int | None:
        rows = [
            row_controls["row"]
            for row_controls in self.macro_row_controls
            if row_controls["path"] != dragged_path and isinstance(row_controls["row"], ttk.Frame)
        ]
        if not rows:
            return 0

        for index, row in enumerate(rows):
            midpoint = row.winfo_rooty() + (row.winfo_height() / 2)
            if y_root < midpoint:
                return index
        return len(rows)

    def _persist_macro_order(self) -> None:
        try:
            updates: list[tuple[Path, MacroScript]] = []
            for index, item in enumerate(self.macro_items):
                latest_script = self._load_macro_file(item.path, show_error=True)
                if latest_script is None:
                    return
                latest_script.custom_order = index
                updates.append((item.path, latest_script))

            self._save_macro_scripts_transactionally(updates)

            for item, (_path, latest_script) in zip(self.macro_items, updates):
                item.script = latest_script
                item.modified_at = item.path.stat().st_mtime
                item.created_at_sort = self._parse_created_at_sort_key(latest_script.created_at)
                if self.current_path == item.path:
                    self.current_script = latest_script
        except Exception as exc:
            messagebox.showerror("保存排序失败", str(exc))
            self._refresh_macro_list()
            return

        self._log("已更新宏自定义排序。")
        self._refresh_macro_list()

    def _save_macro_scripts_transactionally(self, updates: list[tuple[Path, MacroScript]]) -> None:
        temp_paths: dict[Path, Path] = {}
        backup_paths: dict[Path, Path] = {}

        try:
            for path, script in updates:
                suffix = path.suffix or ".txt"
                temp_path = path.with_name(f".{path.stem}.{uuid4().hex}.tmp{suffix}")
                save_script(temp_path, script, preserve_text_from=path)
                temp_paths[path] = temp_path

            for path, _script in updates:
                suffix = path.suffix or ".txt"
                backup_path = path.with_name(f".{path.stem}.{uuid4().hex}.bak{suffix}")
                path.replace(backup_path)
                backup_paths[path] = backup_path

            for path, _script in updates:
                temp_paths[path].replace(path)
        except Exception:
            for path, backup_path in backup_paths.items():
                try:
                    if path.exists():
                        path.unlink()
                    if backup_path.exists():
                        backup_path.replace(path)
                except Exception:
                    pass
            raise
        finally:
            for temp_path in temp_paths.values():
                try:
                    if temp_path.exists():
                        temp_path.unlink()
                except Exception:
                    pass
            for backup_path in backup_paths.values():
                try:
                    if backup_path.exists():
                        backup_path.unlink()
                except Exception:
                    pass

    def _save_macro_script_with_optional_rename(
        self,
        source_path: Path,
        target_path: Path,
        script: MacroScript,
    ) -> None:
        target_suffix = target_path.suffix or ".txt"
        source_suffix = source_path.suffix or ".txt"
        temp_path = target_path.with_name(f".{target_path.stem}.{uuid4().hex}.tmp{target_suffix}")
        source_backup_path = source_path.with_name(f".{source_path.stem}.{uuid4().hex}.bak{source_suffix}")
        target_backup_path: Path | None = None

        try:
            save_script(temp_path, script, preserve_text_from=source_path)

            if source_path.exists():
                source_path.replace(source_backup_path)

            if target_path != source_path and target_path.exists():
                target_backup_path = target_path.with_name(f".{target_path.stem}.{uuid4().hex}.bak{target_suffix}")
                target_path.replace(target_backup_path)

            temp_path.replace(target_path)
        except Exception:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass

            if target_path != source_path and target_path.exists():
                try:
                    target_path.unlink()
                except Exception:
                    pass

            if source_backup_path.exists():
                try:
                    source_backup_path.replace(source_path)
                except Exception:
                    pass

            if target_backup_path is not None and target_backup_path.exists():
                try:
                    target_backup_path.replace(target_path)
                except Exception:
                    pass
            raise
        finally:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass

        try:
            if source_backup_path.exists():
                source_backup_path.unlink()
        except Exception:
            pass

        if target_backup_path is not None:
            try:
                if target_backup_path.exists():
                    target_backup_path.unlink()
            except Exception:
                pass

    def _format_loops(self, loops: int) -> str:
        return "无限" if loops == 0 else str(loops)

    def _load_macro_file(self, path: Path, *, show_error: bool) -> MacroScript | None:
        try:
            return load_script(path)
        except Exception as exc:
            if show_error:
                messagebox.showerror("加载失败", f"无法加载宏文件：\n{path}\n\n{exc}")
            return None

    def _build_auto_macro_stem(self) -> str:
        return datetime.now().strftime("宏-%Y%m%d-%H%M%S")

    def _sanitize_macro_file_stem(self, name: str, suffix: str) -> str:
        stem = name.strip()
        if suffix and stem.lower().endswith(suffix.lower()):
            stem = stem[: -len(suffix)].rstrip()

        forbidden_characters = '<>:"/\\|?*'
        stem = "".join("-" if char in forbidden_characters else char for char in stem)
        stem = stem.rstrip(". ")
        stem = " ".join(stem.split())
        if not stem:
            stem = "宏"
        if stem.upper() in WINDOWS_RESERVED_FILENAMES:
            stem = f"{stem}-宏"
        return stem

    def _unique_macro_path(self, stem: str, suffix: str = ".txt", *, ignore_path: Path | None = None) -> Path:
        candidate = self.macro_store_dir / f"{stem}{suffix}"
        if candidate == ignore_path or not candidate.exists():
            return candidate

        index = 1
        while True:
            candidate = self.macro_store_dir / f"{stem}-{index}{suffix}"
            if candidate == ignore_path or not candidate.exists():
                return candidate
            index += 1

    def _build_renamed_macro_path(self, current_path: Path, name: str) -> Path:
        suffix = current_path.suffix or ".txt"
        stem = self._sanitize_macro_file_stem(name, suffix)
        if stem == current_path.stem:
            return current_path
        return self._unique_macro_path(stem, suffix=suffix, ignore_path=current_path)

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

        try:
            self._global_hotkey_listener = pynput_keyboard.GlobalHotKeys(hotkey_actions)
            self._global_hotkey_listener.start()
        except Exception as exc:
            self._global_hotkey_listener = None
            self._log(f"启动全局快捷键监听失败：{exc}")

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

    def _auto_save_recorded_macro(self, script: MacroScript) -> Path:
        stem = self._build_auto_macro_stem()
        script.name = stem
        path = self._unique_macro_path(stem)
        save_script(path, script)
        return path

    def start_recording(self) -> None:
        if self._is_record_start_blocked():
            return

        self._arming = True
        self._set_status_phase("准备开始录制", "3", "倒计时开始，请立即切换到目标窗口。", "#b45309")
        self._log("3 秒后开始录制，请切换到目标窗口。")
        self._set_controls()
        self._run_record_countdown(3)

    def _run_record_countdown(self, remaining: int) -> None:
        if remaining <= 0:
            self._arming = False
            try:
                self.recorder.start()
            except Exception as exc:
                self.ui_queue.put(("error", f"启动录制失败：{exc}"))
                return

            self._set_status_phase("正在录制，按 Esc 停止", "录制中", "正在捕获动作节点，按 Esc 会停止并自动保存。", "#b91c1c")
            self._log(f"录制已开始，按 Esc 停止并自动保存。当前屏幕：{format_display_profile()}。")
            self._set_controls()
            return

        self._set_status_phase(f"{remaining} 秒后开始录制", str(remaining), "倒计时结束后将自动开始录制。", "#b45309")
        self.root.after(1000, lambda: self._run_record_countdown(remaining - 1))

    def stop_recording(self, *, trigger: str = "button") -> None:
        if not self.recorder.active or self._stopping_record:
            return

        self._stopping_record = True
        self._set_status_phase("正在停止录制", "停止中", "正在整理录制结果并自动保存，请稍候。", "#92400e")
        if trigger == "esc":
            self._log("检测到 Esc，正在停止录制并自动保存...")
        else:
            self._log("正在停止录制并自动保存...")
        self._set_controls()
        threading.Thread(target=self._stop_recording_worker, daemon=True).start()

    def _handle_recorder_stop(self) -> None:
        self.ui_queue.put(("request_stop_recording", "esc"))

    def _stop_recording_worker(self) -> None:
        try:
            script = self.recorder.stop()
        except Exception as exc:
            self.ui_queue.put(("error", f"停止录制失败：{exc}"))
            return

        self.ui_queue.put(("recording_finished", script))

    def play_macro(self, path: Path) -> None:
        if self._is_macro_interaction_locked():
            return

        script = self._load_macro_file(path, show_error=True)
        if script is None:
            return

        if script.default_loops < 0 or script.default_speed <= 0:
            messagebox.showerror("播放设置无效", "宏的默认循环次数或默认播放速度不合法，请先在设置中修正。")
            return

        self.current_path = path
        self.current_script = script
        self._playing = True
        self._stopping_playback = False
        self._playing_path = path
        self._start_playback_abort_listener()

        self._set_status_phase("正在播放", "播放中", "正在回放宏，按 Esc 可以直接中断播放。", "#1d4ed8")
        self._log(
            f"开始播放宏：{script.name}，循环次数：{self._format_loops(script.default_loops)}，"
            f"播放速度：{script.default_speed:g}，当前屏幕：{format_display_profile()}。"
        )
        self._refresh_macro_list()

        threading.Thread(
            target=self._playback_worker,
            args=(path, script, script.default_loops, script.default_speed),
            daemon=True,
        ).start()

    def _playback_worker(self, path: Path, script: MacroScript, loops: int, speed: float) -> None:
        try:
            completed = self.player.play(script, loops=loops, speed=speed)
        except Exception as exc:
            self.ui_queue.put(("error", f"播放失败：{exc}"))
            return

        detail = "播放完成" if completed else "播放已停止"
        self.ui_queue.put(("playback_finished", {"detail": detail, "path": str(path)}))

    def stop_playback(self, *, trigger: str = "button") -> None:
        if (not self.player.active and not self._playing) or self._stopping_playback:
            return

        self._stopping_playback = True
        self._stop_playback_abort_listener()
        self._set_status_phase("正在停止播放", "停止中", "正在停止回放，请稍候。", "#92400e")
        if trigger == "esc":
            self._log("检测到 Esc，正在中断播放...")
        else:
            self._log("已请求停止播放。")
        self.player.stop()
        self._refresh_macro_list()

    def _start_playback_abort_listener(self) -> None:
        self._stop_playback_abort_listener()
        self._playback_abort_listener = pynput_keyboard.Listener(on_press=self._on_playback_abort_key)
        self._playback_abort_listener.start()

    def _stop_playback_abort_listener(self) -> None:
        if self._playback_abort_listener is None:
            return

        try:
            self._playback_abort_listener.stop()
            self._playback_abort_listener.join(timeout=1.0)
        except Exception:
            pass
        finally:
            self._playback_abort_listener = None

    def _on_playback_abort_key(
        self,
        key: pynput_keyboard.Key | pynput_keyboard.KeyCode,
    ) -> bool | None:
        if key == pynput_keyboard.Key.esc:
            self.ui_queue.put(("request_stop_playback", "esc"))
            return False
        return None

    def open_macro_settings(self, path: Path) -> None:
        script = self._load_macro_file(path, show_error=True)
        if script is None:
            return

        self._suspend_global_hotkeys()
        dialog = tk.Toplevel(self.root)
        dialog.title(f"宏设置 - {script.name}")
        dialog.geometry("420x420")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        self._show_dialog(dialog, width=420, height=420)

        content = ttk.Frame(dialog, padding=16)
        content.pack(fill=tk.BOTH, expand=True)

        hotkeys_resumed = False

        def resume_global_hotkeys() -> None:
            nonlocal hotkeys_resumed
            if hotkeys_resumed:
                return
            hotkeys_resumed = True
            self._resume_global_hotkeys()

        ttk.Label(content, text=script.name, font=self.ui_fonts.title).pack(anchor=tk.W)
        ttk.Label(content, text=f"文件：{path.name}").pack(anchor=tk.W, pady=(4, 12))

        try:
            hotkey_text = format_hotkey(script.global_hotkey)
        except HotkeyParseError:
            hotkey_text = script.global_hotkey.strip()

        name_var = tk.StringVar(value=script.name)
        loops_var = tk.StringVar(value=str(script.default_loops))
        speed_var = tk.StringVar(value=str(script.default_speed))
        hotkey_var = tk.StringVar(value=hotkey_text)
        hotkey_feedback_var = tk.StringVar(value="点击输入框后直接按组合键。Backspace 清空。")

        name_row = ttk.Frame(content)
        name_row.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(name_row, text="宏名称").pack(side=tk.LEFT)
        ttk.Entry(name_row, textvariable=name_var, width=24).pack(side=tk.RIGHT)

        loops_row = ttk.Frame(content)
        loops_row.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(loops_row, text="默认循环次数（0 = 无限）").pack(side=tk.LEFT)
        ttk.Entry(loops_row, textvariable=loops_var, width=12).pack(side=tk.RIGHT)

        speed_row = ttk.Frame(content)
        speed_row.pack(fill=tk.X, pady=(0, 16))
        ttk.Label(speed_row, text="默认播放速度").pack(side=tk.LEFT)
        ttk.Entry(speed_row, textvariable=speed_var, width=12).pack(side=tk.RIGHT)

        hotkey_row = ttk.Frame(content)
        hotkey_row.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(hotkey_row, text="全局快捷键").pack(side=tk.LEFT)
        hotkey_entry = ttk.Entry(hotkey_row, textvariable=hotkey_var, width=24)
        hotkey_entry.pack(side=tk.RIGHT)

        ttk.Label(
            content,
            textvariable=hotkey_feedback_var,
            foreground="#64748b",
        ).pack(anchor=tk.W, pady=(0, 14))

        def capture_hotkey(event: tk.Event[tk.Entry]) -> str:
            if event.keysym in {"BackSpace", "Delete"}:
                hotkey_var.set("")
                hotkey_feedback_var.set("已清空快捷键。")
                return "break"

            try:
                hotkey = hotkey_from_tk_event(event.keysym, int(event.state))
            except HotkeyParseError as exc:
                hotkey_feedback_var.set(str(exc))
                return "break"

            if hotkey is None:
                return "break"

            _canonical_hotkey, display_hotkey = hotkey
            hotkey_var.set(display_hotkey)
            hotkey_feedback_var.set(f"已捕获快捷键：{display_hotkey}")
            return "break"

        hotkey_entry.bind("<KeyPress>", capture_hotkey)

        buttons_row = ttk.Frame(content)
        buttons_row.pack(fill=tk.X, pady=(0, 8))

        def save_settings() -> None:
            name = name_var.get().strip()
            if not name:
                messagebox.showerror("输入无效", "宏名称不能为空。", parent=dialog)
                return

            hotkey_input = hotkey_var.get().strip()
            hotkey_display = ""
            canonical_hotkey = ""
            if hotkey_input:
                try:
                    canonical_hotkey, hotkey_display = normalize_hotkey(hotkey_input)
                except HotkeyParseError as exc:
                    messagebox.showerror("输入无效", str(exc), parent=dialog)
                    return

                conflict_item = self._find_hotkey_conflict(path, canonical_hotkey)
                if conflict_item is not None:
                    messagebox.showerror(
                        "快捷键冲突",
                        f"快捷键 {hotkey_display} 已被宏“{conflict_item.script.name}”使用。",
                        parent=dialog,
                    )
                    return

            try:
                loops = int(loops_var.get().strip())
                speed = float(speed_var.get().strip())
            except ValueError:
                messagebox.showerror("输入无效", "循环次数必须是整数，播放速度必须是数字。", parent=dialog)
                return

            if loops < 0 or speed <= 0:
                messagebox.showerror("输入无效", "循环次数不能小于 0，播放速度必须大于 0。", parent=dialog)
                return

            latest_script = self._load_macro_file(path, show_error=True)
            if latest_script is None:
                return

            previous_name = latest_script.name
            previous_hotkey = latest_script.global_hotkey.strip()
            target_path = self._build_renamed_macro_path(path, name)
            latest_script.name = name
            latest_script.default_loops = loops
            latest_script.default_speed = speed
            latest_script.global_hotkey = hotkey_display

            try:
                self._save_macro_script_with_optional_rename(path, target_path, latest_script)
            except Exception as exc:
                messagebox.showerror("保存失败", str(exc), parent=dialog)
                return

            if self.current_path == path:
                self.current_path = target_path
                self.current_script = latest_script
            if self._playing_path == path:
                self._playing_path = target_path

            log_message = (
                f"已更新宏设置：{previous_name} -> {name}，循环次数：{self._format_loops(loops)}，播放速度：{speed:g}。"
            )
            if target_path != path:
                log_message = f"{log_message[:-1]}，文件：{path.name} -> {target_path.name}。"
            if previous_hotkey != hotkey_display:
                if hotkey_display:
                    log_message = f"{log_message[:-1]}，快捷键：{hotkey_display}。"
                elif previous_hotkey:
                    log_message = f"{log_message[:-1]}，快捷键已清空。"
            self._log(log_message)
            self._refresh_macro_list()
            resume_global_hotkeys()
            dialog.destroy()

        def edit_script() -> None:
            try:
                subprocess.Popen(["notepad.exe", str(path)])
            except Exception as exc:
                messagebox.showerror("打开失败", str(exc), parent=dialog)
                return

            self._log(f"已打开脚本编辑器：{path.name}")

        def delete_macro() -> None:
            if self._is_path_playing(path):
                messagebox.showwarning("无法删除", "该宏正在播放，请先停止播放再删除。", parent=dialog)
                return

            confirmed = messagebox.askyesno(
                "删除宏",
                f"确定要删除这个宏吗？\n\n{path.name}",
                parent=dialog,
            )
            if not confirmed:
                return

            try:
                path.unlink()
            except Exception as exc:
                messagebox.showerror("删除失败", str(exc), parent=dialog)
                return

            if self.current_path == path:
                self._clear_current_selection()

            self._log(f"已删除宏：{path.name}")
            self._refresh_macro_list()
            resume_global_hotkeys()
            dialog.destroy()

        def close_dialog() -> None:
            resume_global_hotkeys()
            dialog.destroy()

        ttk.Button(buttons_row, text="保存设置", command=save_settings).pack(side=tk.LEFT)
        ttk.Button(buttons_row, text="编辑脚本", command=edit_script).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons_row, text="删除宏", command=delete_macro).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(content, text="关闭", command=close_dialog).pack(anchor=tk.E, pady=(12, 0))
        dialog.protocol("WM_DELETE_WINDOW", close_dialog)

    def _show_dialog(self, dialog: tk.Toplevel, *, width: int, height: int) -> None:
        self.root.update_idletasks()

        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_width = self.root.winfo_width()
        root_height = self.root.winfo_height()

        x = root_x + max((root_width - width) // 2, 0)
        y = root_y + max((root_height - height) // 2, 0)
        dialog.geometry(f"{width}x{height}+{x}+{y}")
        dialog.deiconify()
        dialog.lift()
        dialog.focus_force()
        dialog.grab_set()

        try:
            dialog.attributes("-topmost", True)
            dialog.after(150, lambda win=dialog: self._restore_dialog_topmost(win))
        except tk.TclError:
            pass

    def _restore_dialog_topmost(self, dialog: tk.Toplevel) -> None:
        try:
            if dialog.winfo_exists():
                dialog.attributes("-topmost", bool(self.always_on_top_var.get()))
        except tk.TclError:
            pass

    def _on_close(self) -> None:
        self._stop_playback_abort_listener()
        self._stop_global_hotkey_listener()

        if self.recorder.active:
            try:
                self.recorder.stop()
            except Exception:
                pass

        if self.player.active:
            self.player.stop()

        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def run() -> None:
    MacroApp().run()
