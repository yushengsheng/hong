from __future__ import annotations

import ctypes
import os
import sys
import traceback

from macro_app.runtime import get_runtime_root


APP_TITLE = "宏录制器"


def show_message(message: str, *, error: bool = False) -> None:
    flags = 0x10 if error else 0x40
    ctypes.windll.user32.MessageBoxW(0, message, APP_TITLE, flags)


def main() -> None:
    project_root = get_runtime_root()
    os.chdir(project_root)

    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from macro_app.app import run

    run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log_path = get_runtime_root() / "launch-error.log"
        log_path.write_text(traceback.format_exc(), encoding="utf-8")
        show_message(
            "启动失败。\n\n"
            f"详细错误已写入：\n{log_path}",
            error=True,
        )
