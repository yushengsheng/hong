from __future__ import annotations

from datetime import datetime
from pathlib import Path
import queue
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk

from .display import format_display_profile
from .models import MacroScript
from .ui_theme import UIFontSet, build_ui_fonts


class MacroAppUIMixin:
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

    def _flush_startup_messages(self) -> None:
        for message in self._startup_messages:
            self._log(message)
        self._startup_messages.clear()

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
                self._clear_recording_stop_state()
                self._set_status_phase("出错", "出错", "请查看日志内容，修正后再重试。", "#b91c1c")
                self._log(text)
                messagebox.showerror("错误", text, parent=self.root)
                self._refresh_macro_list()
                continue

        self.root.after(100, self._drain_ui_queue)

    def _log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

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
        if current_height >= desired_height - 2:
            return

        current_width = max(int(self.root.winfo_width()), 400)
        x = int(self.root.winfo_x())
        y = int(self.root.winfo_y())
        self._resizing_window_height = True
        self.root.geometry(f"{current_width}x{desired_height}+{x}+{y}")
        self.root.after_idle(self._finish_window_height_resize)

    def _finish_window_height_resize(self) -> None:
        self._resizing_window_height = False

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
