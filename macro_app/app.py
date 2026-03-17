from __future__ import annotations

from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox

from pynput import keyboard as pynput_keyboard

from .app_dialogs import MacroAppDialogsMixin
from .app_hotkeys import MacroAppHotkeysMixin
from .app_storage import MacroAppStorageMixin
from .app_support import MacroLibraryItem
from .app_ui import MacroAppUIMixin
from .app_workflows import MacroAppWorkflowsMixin
from .display import ensure_dpi_awareness
from .models import MacroScript
from .player import MacroPlayer
from .recorder import MacroRecorder
from .runtime import get_runtime_root

ensure_dpi_awareness()


class MacroApp(
    MacroAppDialogsMixin,
    MacroAppWorkflowsMixin,
    MacroAppHotkeysMixin,
    MacroAppStorageMixin,
    MacroAppUIMixin,
):
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
        self._recording_stop_thread: threading.Thread | None = None
        self._recording_stop_result: MacroScript | None = None
        self._recording_stop_error: str | None = None
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

    def run(self) -> None:
        self.root.mainloop()


def run() -> None:
    MacroApp().run()
