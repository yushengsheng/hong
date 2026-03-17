from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from tkinter import messagebox
from uuid import uuid4

from .app_support import MacroLibraryItem, WINDOWS_RESERVED_FILENAMES
from .models import MacroScript
from .script_io import load_script, save_script


class MacroAppStorageMixin:
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

    def _is_macro_file_path(self, path: Path) -> bool:
        if not path.is_file():
            return False
        if path.suffix.lower() not in {".txt", ".json"}:
            return False
        if path.name.startswith("."):
            return False
        return True

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

    def _parse_created_at_sort_key(self, created_at: str) -> float:
        try:
            return datetime.fromisoformat(created_at).timestamp()
        except (TypeError, ValueError):
            return float("inf")

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
            messagebox.showerror("保存排序失败", str(exc), parent=self.root)
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

    def _load_macro_file(self, path: Path, *, show_error: bool) -> MacroScript | None:
        try:
            return load_script(path)
        except Exception as exc:
            if show_error:
                messagebox.showerror("加载失败", f"无法加载宏文件：\n{path}\n\n{exc}", parent=self.root)
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

    def _auto_save_recorded_macro(self, script: MacroScript) -> Path:
        stem = self._build_auto_macro_stem()
        script.name = stem
        path = self._unique_macro_path(stem)
        save_script(path, script)
        return path
