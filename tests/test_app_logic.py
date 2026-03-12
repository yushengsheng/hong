from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from macro_app.app import MacroApp
from macro_app.models import MacroScript
from macro_app.script_io import load_script, save_script


def make_app_stub(macro_store_dir: Path) -> MacroApp:
    app = object.__new__(MacroApp)
    app.macro_store_dir = macro_store_dir
    app.project_root = macro_store_dir.parent
    app.recorder = SimpleNamespace(active=False)
    app.player = SimpleNamespace(active=False)
    app.current_path = None
    app.current_script = None
    app.macro_items = []
    app._playing = False
    app._stopping_record = False
    app._stopping_playback = False
    app._playing_path = None
    app._arming = False
    app._macro_store_signature = ()
    app._global_hotkeys_suspended = 0
    app._global_hotkey_listener = None
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


if __name__ == "__main__":
    unittest.main()
