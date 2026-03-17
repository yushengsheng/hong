from __future__ import annotations

from pathlib import Path
import queue
import threading
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from macro_app.app import MacroApp, MacroLibraryItem
from macro_app.models import MacroEvent, MacroScript
from macro_app.script_io import load_script, save_script


def make_app_stub(macro_store_dir: Path) -> MacroApp:
    app = object.__new__(MacroApp)
    app.macro_store_dir = macro_store_dir
    app.project_root = macro_store_dir.parent
    app.root = SimpleNamespace()
    app.recorder = SimpleNamespace(active=False)
    app.player = SimpleNamespace(active=False)
    app.current_path = None
    app.current_script = None
    app.macro_items = []
    app._playing = False
    app._stopping_record = False
    app._stopping_playback = False
    app._recording_stop_thread = None
    app._recording_stop_result = None
    app._recording_stop_error = None
    app._playing_path = None
    app._playback_abort_listener = None
    app._arming = False
    app._resizing_window_height = False
    app._macro_store_signature = ()
    app._global_hotkeys_suspended = 0
    app._global_hotkey_listener = None
    app._is_recording_busy = MacroApp._is_recording_busy.__get__(app, MacroApp)
    app._is_playback_busy = MacroApp._is_playback_busy.__get__(app, MacroApp)
    app._is_macro_interaction_locked = MacroApp._is_macro_interaction_locked.__get__(app, MacroApp)
    app._reset_playback_state = MacroApp._reset_playback_state.__get__(app, MacroApp)
    app._stop_playback_abort_listener = MacroApp._stop_playback_abort_listener.__get__(app, MacroApp)
    app._format_loops = MacroApp._format_loops.__get__(app, MacroApp)
    app._clear_recording_stop_state = MacroApp._clear_recording_stop_state.__get__(app, MacroApp)
    app._persist_recording_before_close = MacroApp._persist_recording_before_close.__get__(app, MacroApp)
    app._load_macro_file = MacroApp._load_macro_file.__get__(app, MacroApp)
    app._parse_created_at_sort_key = MacroApp._parse_created_at_sort_key.__get__(app, MacroApp)
    app._is_macro_file_path = MacroApp._is_macro_file_path.__get__(app, MacroApp)
    app._save_macro_scripts_transactionally = MacroApp._save_macro_scripts_transactionally.__get__(app, MacroApp)
    app._save_macro_script_with_optional_rename = MacroApp._save_macro_script_with_optional_rename.__get__(app, MacroApp)
    return app


class AppLogicTests(unittest.TestCase):
    def test_collect_macro_items_ignores_hidden_backup_files(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            app = make_app_stub(base)
            save_script(
                base / "visible.txt",
                MacroScript(name="visible", created_at="2026-03-11T08:00:00+00:00", screen_size=(1, 1)),
            )
            save_script(
                base / ".visible.abc.bak.txt",
                MacroScript(name="backup", created_at="2026-03-11T09:00:00+00:00", screen_size=(1, 1)),
            )

            items = MacroApp._collect_macro_items(app)
            self.assertEqual([item.path.name for item in items], ["visible.txt"])

    def test_collect_macro_items_prefers_custom_order_then_creation_time(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            app = make_app_stub(base)
            save_script(
                base / "late.txt",
                MacroScript(name="late", created_at="2026-03-11T10:00:00+00:00", screen_size=(1, 1)),
            )
            save_script(
                base / "early.txt",
                MacroScript(name="early", created_at="2026-03-11T08:00:00+00:00", screen_size=(1, 1)),
            )
            save_script(
                base / "custom.txt",
                MacroScript(name="custom", created_at="2026-03-11T09:00:00+00:00", screen_size=(1, 1), custom_order=0),
            )

            items = MacroApp._collect_macro_items(app)
            self.assertEqual([item.script.name for item in items], ["custom", "early", "late"])

    def test_transactional_save_with_optional_rename_replaces_target_atomically(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            app = make_app_stub(base)
            source_path = base / "old.txt"
            target_path = base / "new.txt"
            save_script(
                source_path,
                MacroScript(name="old", created_at="2026-03-11T08:00:00+00:00", screen_size=(1, 1)),
            )

            updated_script = load_script(source_path)
            updated_script.name = "new"
            updated_script.custom_order = 2

            MacroApp._save_macro_script_with_optional_rename(app, source_path, target_path, updated_script)

            self.assertFalse(source_path.exists())
            self.assertTrue(target_path.exists())
            reloaded = load_script(target_path)
            self.assertEqual(reloaded.name, "new")
            self.assertEqual(reloaded.custom_order, 2)

    def test_transactional_save_with_optional_rename_preserves_event_comments(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            app = make_app_stub(base)
            source_path = base / "old.txt"
            target_path = base / "new.txt"
            source_path.write_text(
                "\n".join(
                    [
                        "# 宏脚本文本格式 v4",
                        "名称: old",
                        "创建时间: 2026-03-11T08:00:00+00:00",
                        "版本: 4",
                        "屏幕尺寸: 1,1",
                        "屏幕原点: 0,0",
                        "默认循环次数: 1",
                        "默认播放速度: 1.0",
                        "全局快捷键: ",
                        "自定义排序: ",
                        "事件数: 2",
                        "",
                        "事件:",
                        "### 标记",
                        "间隔=0.000000 | 键盘按下 | 按键=特殊:ctrl_l",
                        "间隔=0.010000 | 键盘松开 | 按键=特殊:ctrl_l",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            updated_script = load_script(source_path)
            updated_script.name = "new"
            updated_script.custom_order = 2

            MacroApp._save_macro_script_with_optional_rename(app, source_path, target_path, updated_script)

            rewritten = target_path.read_text(encoding="utf-8")
            self.assertIn("### 标记", rewritten)
            self.assertIn("名称: new", rewritten)
            self.assertIn("自定义排序: 2", rewritten)

    def test_refresh_macro_list_skips_hotkey_rebuild_while_suspended(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            app = make_app_stub(base)
            calls = {"count": 0}
            app._collect_macro_items = lambda: []
            app._get_macro_store_signature = lambda: ()
            app._render_macro_list = lambda: None
            app._set_controls = lambda: None
            app._rebuild_global_hotkeys = lambda: calls.__setitem__("count", calls["count"] + 1)
            app._global_hotkeys_suspended = 1

            MacroApp._refresh_macro_list(app)
            self.assertEqual(calls["count"], 0)

            app._global_hotkeys_suspended = 0
            MacroApp._refresh_macro_list(app)
            self.assertEqual(calls["count"], 1)

    def test_macro_interaction_helpers_preserve_original_busy_rules(self) -> None:
        app = make_app_stub(Path.cwd())

        app._stopping_record = True
        self.assertTrue(MacroApp._is_recording_busy(app))
        self.assertTrue(MacroApp._is_macro_interaction_locked(app))
        self.assertFalse(MacroApp._is_record_start_blocked(app))

        app._stopping_record = False
        app._arming = True
        self.assertTrue(MacroApp._is_record_start_blocked(app))
        self.assertTrue(MacroApp._is_macro_interaction_locked(app))

    def test_is_path_playing_requires_matching_path_and_active_playback(self) -> None:
        app = make_app_stub(Path.cwd())
        playing_path = Path("demo.txt")
        app._playing_path = playing_path

        self.assertFalse(MacroApp._is_path_playing(app, playing_path))

        app._playing = True
        self.assertTrue(MacroApp._is_path_playing(app, playing_path))
        self.assertFalse(MacroApp._is_path_playing(app, Path("other.txt")))

    def test_sync_current_script_clears_missing_current_path(self) -> None:
        app = make_app_stub(Path.cwd())
        app.current_path = Path("missing.txt")
        app.current_script = MacroScript(name="stale", created_at="2026-03-11T08:00:00+00:00", screen_size=(1, 1))

        MacroApp._sync_current_script_from_current_path(app)

        self.assertIsNone(app.current_path)
        self.assertIsNone(app.current_script)

    def test_sync_current_script_clears_current_path_when_reload_fails(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            app = make_app_stub(base)
            path = base / "demo.txt"
            save_script(path, MacroScript(name="demo", created_at="2026-03-11T08:00:00+00:00", screen_size=(1, 1)))
            app.current_path = path
            app.current_script = MacroScript(name="stale", created_at="2026-03-11T08:00:00+00:00", screen_size=(1, 1))
            app._load_macro_file = lambda _path, show_error=False: None

            MacroApp._sync_current_script_from_current_path(app)

            self.assertIsNone(app.current_path)
            self.assertIsNone(app.current_script)

    def test_get_macro_store_signature_skips_files_that_disappear_during_stat(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            app = make_app_stub(base)
            app._is_macro_file_path = lambda path: path.suffix == ".txt"
            stable_path = base / "stable.txt"
            flaky_path = base / "flaky.txt"
            save_script(stable_path, MacroScript(name="stable", created_at="2026-03-11T08:00:00+00:00", screen_size=(1, 1)))
            save_script(flaky_path, MacroScript(name="flaky", created_at="2026-03-11T08:00:00+00:00", screen_size=(1, 1)))

            path_type = type(stable_path)
            original_stat = path_type.stat

            def flaky_stat(path: Path, *args: object, **kwargs: object) -> object:
                if path.name == "flaky.txt":
                    raise FileNotFoundError
                return original_stat(path, *args, **kwargs)

            with patch.object(path_type, "stat", new=flaky_stat):
                signature = MacroApp._get_macro_store_signature(app)

            self.assertEqual(len(signature), 1)
            self.assertEqual(signature[0][0], "stable.txt")

    def test_collect_macro_items_skips_files_that_disappear_during_stat(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            app = make_app_stub(base)
            app._is_macro_file_path = lambda path: path.suffix == ".txt"
            stable_path = base / "stable.txt"
            flaky_path = base / "flaky.txt"
            save_script(stable_path, MacroScript(name="stable", created_at="2026-03-11T08:00:00+00:00", screen_size=(1, 1)))
            save_script(flaky_path, MacroScript(name="flaky", created_at="2026-03-11T09:00:00+00:00", screen_size=(1, 1)))

            path_type = type(stable_path)
            original_stat = path_type.stat

            def flaky_stat(path: Path, *args: object, **kwargs: object) -> object:
                if path.name == "flaky.txt":
                    raise FileNotFoundError
                return original_stat(path, *args, **kwargs)

            with patch.object(path_type, "stat", new=flaky_stat):
                items = MacroApp._collect_macro_items(app)

            self.assertEqual([item.path.name for item in items], ["stable.txt"])

    def test_poll_macro_store_rearms_timer_after_scan_error(self) -> None:
        app = make_app_stub(Path.cwd())
        after_calls: list[tuple[int, object]] = []
        log_messages: list[str] = []

        class FakeRoot:
            def after(self, delay: int, callback: object) -> None:
                after_calls.append((delay, callback))

        app.root = FakeRoot()
        app._get_macro_store_signature = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        app._refresh_macro_list = lambda: None
        app._log = log_messages.append

        MacroApp._poll_macro_store(app)

        self.assertEqual(after_calls[0][0], 1500)
        self.assertIn("boom", log_messages[0])

    def test_play_macro_rolls_back_state_when_abort_listener_start_fails(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            app = make_app_stub(base)
            path = base / "demo.txt"
            save_script(path, MacroScript(name="demo", created_at="2026-03-11T08:00:00+00:00", screen_size=(1, 1)))
            app._set_status_phase = lambda *args, **kwargs: None
            app._log = lambda *args, **kwargs: None
            app._refresh_macro_list = lambda: None
            app._start_playback_abort_listener = lambda: (_ for _ in ()).throw(RuntimeError("listener boom"))

            with patch("macro_app.app.messagebox.showerror") as showerror:
                MacroApp.play_macro(app, path)

            self.assertFalse(app._playing)
            self.assertFalse(app._stopping_playback)
            self.assertIsNone(app._playing_path)
            showerror.assert_called_once()

    def test_fit_window_height_to_content_does_not_shrink_manual_height(self) -> None:
        app = make_app_stub(Path.cwd())

        class FakeRoot:
            def __init__(self) -> None:
                self.geometry_calls: list[str] = []
                self.after_idle_calls: list[object] = []

            def state(self) -> str:
                return "normal"

            def update_idletasks(self) -> None:
                return None

            def winfo_reqheight(self) -> int:
                return 532

            def winfo_screenheight(self) -> int:
                return 1080

            def winfo_height(self) -> int:
                return 800

            def winfo_width(self) -> int:
                return 460

            def winfo_x(self) -> int:
                return 100

            def winfo_y(self) -> int:
                return 120

            def geometry(self, value: str) -> None:
                self.geometry_calls.append(value)

            def after_idle(self, callback: object) -> None:
                self.after_idle_calls.append(callback)

        app.root = FakeRoot()

        MacroApp._fit_window_height_to_content(app)

        self.assertEqual(app.root.geometry_calls, [])

    def test_fit_window_height_to_content_still_grows_when_content_exceeds_window(self) -> None:
        app = make_app_stub(Path.cwd())

        class FakeRoot:
            def __init__(self) -> None:
                self.geometry_calls: list[str] = []
                self.after_idle_calls: list[object] = []

            def state(self) -> str:
                return "normal"

            def update_idletasks(self) -> None:
                return None

            def winfo_reqheight(self) -> int:
                return 532

            def winfo_screenheight(self) -> int:
                return 1080

            def winfo_height(self) -> int:
                return 420

            def winfo_width(self) -> int:
                return 460

            def winfo_x(self) -> int:
                return 100

            def winfo_y(self) -> int:
                return 120

            def geometry(self, value: str) -> None:
                self.geometry_calls.append(value)

            def after_idle(self, callback: object) -> None:
                self.after_idle_calls.append(callback)

        app.root = FakeRoot()

        MacroApp._fit_window_height_to_content(app)

        self.assertEqual(app.root.geometry_calls, ["460x532+100+120"])
        self.assertEqual(len(app.root.after_idle_calls), 1)

    def test_rebuild_global_hotkeys_closes_failed_listener(self) -> None:
        app = make_app_stub(Path.cwd())
        path = Path("demo.txt")
        logs: list[str] = []

        class FakeHotkeys:
            def __init__(self) -> None:
                self.started = False
                self.stopped = False
                self.joined = False

            def start(self) -> None:
                self.started = True
                raise RuntimeError("boom")

            def stop(self) -> None:
                self.stopped = True

            def join(self, timeout: float | None = None) -> None:
                self.joined = True

        holder: dict[str, FakeHotkeys] = {}

        def build_hotkeys(_actions: object) -> FakeHotkeys:
            holder["listener"] = FakeHotkeys()
            return holder["listener"]

        app._queue_hotkey_play = lambda *args, **kwargs: None
        app._log = logs.append
        app.macro_items = [
            MacroLibraryItem(
                path=path,
                script=MacroScript(
                    name="demo",
                    created_at="2026-03-11T08:00:00+00:00",
                    screen_size=(1, 1),
                    global_hotkey="Ctrl+Alt+1",
                ),
                modified_at=0.0,
                created_at_sort=0.0,
            )
        ]

        with patch("macro_app.app.pynput_keyboard.GlobalHotKeys", side_effect=build_hotkeys):
            MacroApp._rebuild_global_hotkeys(app)

        listener = holder["listener"]
        self.assertTrue(listener.started)
        self.assertTrue(listener.stopped)
        self.assertTrue(listener.joined)
        self.assertIsNone(app._global_hotkey_listener)
        self.assertIn("boom", logs[0])

    def test_on_close_auto_saves_active_recording_before_destroy(self) -> None:
        app = make_app_stub(Path.cwd())
        recorder_script = MacroScript(
            name="recording",
            created_at="2026-03-11T08:00:00+00:00",
            screen_size=(1, 1),
            events=[MacroEvent(0.0, "key_press", {"key": {"type": "char", "value": "a"}})],
        )
        destroyed = {"value": False}
        auto_saved: list[MacroScript] = []
        logs: list[str] = []

        class FakeRoot:
            def destroy(self) -> None:
                destroyed["value"] = True

        app.root = FakeRoot()
        app.recorder = SimpleNamespace(active=True, stop=lambda: recorder_script)
        app.player = SimpleNamespace(active=False, stop=lambda: None)
        app._stop_playback_abort_listener = lambda: None
        app._stop_global_hotkey_listener = lambda: None
        app._auto_save_recorded_macro = lambda script: auto_saved.append(script) or Path("saved.txt")
        app._log = logs.append

        MacroApp._on_close(app)

        self.assertTrue(destroyed["value"])
        self.assertEqual(auto_saved, [recorder_script])
        self.assertEqual(app.current_script, recorder_script)
        self.assertEqual(app.current_path, Path("saved.txt"))
        self.assertIn("saved.txt", logs[0])

    def test_on_close_aborts_destroy_when_recording_save_fails(self) -> None:
        app = make_app_stub(Path.cwd())
        recorder_script = MacroScript(
            name="recording",
            created_at="2026-03-11T08:00:00+00:00",
            screen_size=(1, 1),
            events=[MacroEvent(0.0, "key_press", {"key": {"type": "char", "value": "a"}})],
        )
        destroyed = {"value": False}

        class FakeRoot:
            def destroy(self) -> None:
                destroyed["value"] = True

        app.root = FakeRoot()
        app.recorder = SimpleNamespace(active=True, stop=lambda: recorder_script)
        app.player = SimpleNamespace(active=False, stop=lambda: None)
        app._stop_playback_abort_listener = lambda: None
        app._stop_global_hotkey_listener = lambda: None
        app._auto_save_recorded_macro = lambda _script: (_ for _ in ()).throw(RuntimeError("disk full"))
        app._log = lambda *args, **kwargs: None

        with patch("macro_app.app.messagebox.showerror") as showerror:
            MacroApp._on_close(app)

        self.assertFalse(destroyed["value"])
        showerror.assert_called_once()

    def test_on_close_waits_for_inflight_recording_stop_without_double_stop(self) -> None:
        app = make_app_stub(Path.cwd())
        recorder_script = MacroScript(
            name="recording",
            created_at="2026-03-11T08:00:00+00:00",
            screen_size=(1, 1),
            events=[MacroEvent(0.0, "key_press", {"key": {"type": "char", "value": "a"}})],
        )
        destroyed = {"value": False}
        auto_saved: list[MacroScript] = []
        stop_started = threading.Event()
        allow_stop_finish = threading.Event()

        class FakeRoot:
            def destroy(self) -> None:
                destroyed["value"] = True

        class SlowRecorder:
            def __init__(self) -> None:
                self.active = True
                self.calls = 0

            def stop(self) -> MacroScript:
                self.calls += 1
                if self.calls > 1:
                    raise RuntimeError("stop called twice")
                stop_started.set()
                allow_stop_finish.wait(timeout=1.0)
                self.active = False
                return recorder_script

        app.root = FakeRoot()
        app.recorder = SlowRecorder()
        app.player = SimpleNamespace(active=False, stop=lambda: None)
        app._stop_playback_abort_listener = lambda: None
        app._stop_global_hotkey_listener = lambda: None
        app._auto_save_recorded_macro = lambda script: auto_saved.append(script) or Path("saved.txt")
        app._log = lambda *args, **kwargs: None
        app._set_status_phase = lambda *args, **kwargs: None
        app._set_controls = lambda: None
        app.ui_queue = queue.Queue()

        MacroApp.stop_recording(app)
        self.assertTrue(stop_started.wait(timeout=0.5))
        allow_stop_finish.set()

        with patch("macro_app.app.messagebox.showerror") as showerror:
            MacroApp._on_close(app)

        self.assertTrue(destroyed["value"])
        self.assertEqual(app.recorder.calls, 1)
        self.assertEqual(auto_saved, [recorder_script])
        self.assertEqual(app.current_path, Path("saved.txt"))
        self.assertIsNone(app._recording_stop_thread)
        self.assertIsNone(app._recording_stop_result)
        self.assertIsNone(app._recording_stop_error)
        showerror.assert_not_called()


if __name__ == "__main__":
    unittest.main()
