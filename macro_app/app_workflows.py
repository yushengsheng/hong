from __future__ import annotations

from pathlib import Path
import threading
from tkinter import messagebox

from pynput import keyboard as pynput_keyboard

from .display import format_display_profile
from .models import MacroScript


class MacroAppWorkflowsMixin:
    def _clear_recording_stop_state(self) -> None:
        self._recording_stop_thread = None
        self._recording_stop_result = None
        self._recording_stop_error = None

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

    def _reset_playback_state(self) -> None:
        self._playing = False
        self._stopping_playback = False
        self._playing_path = None
        self._stop_playback_abort_listener()

    def _handle_recording_finished(self, script: MacroScript) -> None:
        self._stopping_record = False

        if not script.events:
            self._clear_current_selection()
            self._set_status_phase("录制结果为空", "未保存", "本次没有捕获到动作节点，因此没有自动保存。", "#92400e")
            self._log("录制完成，但没有捕获到动作节点，未自动保存。")
            self._clear_recording_stop_state()
            self._refresh_macro_list()
            return

        try:
            path = self._auto_save_recorded_macro(script)
        except Exception as exc:
            self._clear_recording_stop_state()
            self.ui_queue.put(("error", f"自动保存录制宏失败：{exc}"))
            return

        self.current_script = script
        self.current_path = path
        self._set_status_phase("录制完成并已保存", "录制完成", "宏已自动保存，现在可以直接在列表中播放或设置。", "#166534")
        self._log(f"录制完成，共捕获 {len(script.events)} 个事件，已自动保存：{path.name}")
        self._clear_recording_stop_state()
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

    def _format_loops(self, loops: int) -> str:
        return "无限" if loops == 0 else str(loops)

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
        self._recording_stop_result = None
        self._recording_stop_error = None
        self._set_status_phase("正在停止录制", "停止中", "正在整理录制结果并自动保存，请稍候。", "#92400e")
        if trigger == "esc":
            self._log("检测到 Esc，正在停止录制并自动保存...")
        else:
            self._log("正在停止录制并自动保存...")
        self._set_controls()
        stop_thread = threading.Thread(target=self._stop_recording_worker, daemon=True)
        self._recording_stop_thread = stop_thread
        stop_thread.start()

    def _handle_recorder_stop(self) -> None:
        self.ui_queue.put(("request_stop_recording", "esc"))

    def _stop_recording_worker(self) -> None:
        try:
            script = self.recorder.stop()
        except Exception as exc:
            self._recording_stop_error = f"停止录制失败：{exc}"
            self.ui_queue.put(("error", self._recording_stop_error))
            return

        self._recording_stop_result = script
        self.ui_queue.put(("recording_finished", script))

    def play_macro(self, path: Path) -> None:
        if self._is_macro_interaction_locked():
            return

        script = self._load_macro_file(path, show_error=True)
        if script is None:
            return

        if script.default_loops < 0 or script.default_speed <= 0:
            messagebox.showerror(
                "播放设置无效",
                "宏的默认循环次数或默认播放速度不合法，请先在设置中修正。",
                parent=self.root,
            )
            return

        self.current_path = path
        self.current_script = script
        self._playing = True
        self._stopping_playback = False
        self._playing_path = path
        playback_thread = threading.Thread(
            target=self._playback_worker,
            args=(path, script, script.default_loops, script.default_speed),
            daemon=True,
        )

        try:
            self._start_playback_abort_listener()
            playback_thread.start()
        except Exception as exc:
            self._reset_playback_state()
            self._log(f"启动播放失败：{exc}")
            self._refresh_macro_list()
            messagebox.showerror(
                "启动播放失败",
                f"无法开始播放宏：\n{script.name}\n\n{exc}",
                parent=self.root,
            )
            return

        self._set_status_phase("正在播放", "播放中", "正在回放宏，按 Esc 可以直接中断播放。", "#1d4ed8")
        self._log(
            f"开始播放宏：{script.name}，循环次数：{self._format_loops(script.default_loops)}，"
            f"播放速度：{script.default_speed:g}，当前屏幕：{format_display_profile()}。"
        )
        self._refresh_macro_list()

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
        listener = pynput_keyboard.Listener(on_press=self._on_playback_abort_key)
        try:
            listener.start()
        except Exception:
            try:
                listener.stop()
            except Exception:
                pass
            try:
                listener.join(timeout=1.0)
            except Exception:
                pass
            raise

        self._playback_abort_listener = listener

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

    def _persist_recording_before_close(self, script: MacroScript) -> bool:
        if not script.events:
            self._clear_current_selection()
            return True

        try:
            path = self._auto_save_recorded_macro(script)
        except Exception as exc:
            messagebox.showerror("关闭失败", f"录制结果保存失败：\n\n{exc}", parent=self.root)
            return False

        self.current_script = script
        self.current_path = path
        self._log(f"关闭前已自动保存当前录制：{path.name}")
        return True

    def _on_close(self) -> None:
        self._stop_playback_abort_listener()
        self._stop_global_hotkey_listener()

        if self._stopping_record:
            stop_thread = self._recording_stop_thread
            if stop_thread is not None:
                stop_thread.join(timeout=2.5)
                if stop_thread.is_alive():
                    messagebox.showerror("关闭失败", "录制仍在停止中，请稍候再关闭。", parent=self.root)
                    return

            self._stopping_record = False
            if self._recording_stop_error:
                error_text = self._recording_stop_error
                self._clear_recording_stop_state()
                messagebox.showerror("关闭失败", error_text, parent=self.root)
                return

            pending_script = self._recording_stop_result
            self._clear_recording_stop_state()
            if pending_script is not None and not self._persist_recording_before_close(pending_script):
                return
        elif self.recorder.active:
            try:
                script = self.recorder.stop()
            except Exception as exc:
                messagebox.showerror("关闭失败", f"停止录制失败：\n\n{exc}", parent=self.root)
                return

            if not self._persist_recording_before_close(script):
                return

        if self.player.active:
            self.player.stop()

        self.root.destroy()
