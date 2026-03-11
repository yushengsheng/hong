from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from macro_app.app import MacroApp
from macro_app.models import MacroScript
from macro_app.script_io import load_script, save_script


def make_app_stub(macro_store_dir: Path) -> MacroApp:
    app = object.__new__(MacroApp)
    app.macro_store_dir = macro_store_dir
    app.project_root = macro_store_dir.parent
    app.current_path = None
    app.current_script = None
    app.macro_items = []
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


if __name__ == "__main__":
    unittest.main()
