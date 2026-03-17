from __future__ import annotations

from pathlib import Path
import subprocess
import tkinter as tk
from tkinter import messagebox, ttk

from .hotkeys import HotkeyParseError, format_hotkey, hotkey_from_tk_event, normalize_hotkey


class MacroAppDialogsMixin:
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
