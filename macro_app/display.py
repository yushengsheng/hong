from __future__ import annotations

import ctypes
from dataclasses import dataclass
import sys


SM_CXSCREEN = 0
SM_CYSCREEN = 1
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

PROCESS_PER_MONITOR_DPI_AWARE = 2
LOGPIXELSX = 88
DEFAULT_DPI = 96
E_ACCESSDENIED = -2147024891

_DPI_AWARENESS_SET = False


@dataclass(slots=True)
class ScreenBounds:
    left: int
    top: int
    width: int
    height: int

    @property
    def origin(self) -> tuple[int, int]:
        return self.left, self.top

    @property
    def size(self) -> tuple[int, int]:
        return self.width, self.height


def ensure_dpi_awareness() -> None:
    global _DPI_AWARENESS_SET

    if _DPI_AWARENESS_SET or sys.platform != "win32":
        _DPI_AWARENESS_SET = True
        return

    user32 = ctypes.windll.user32

    try:
        awareness_context = ctypes.c_void_p(-4)
        user32.SetProcessDpiAwarenessContext.restype = ctypes.c_bool
        if user32.SetProcessDpiAwarenessContext(awareness_context):
            _DPI_AWARENESS_SET = True
            return
    except AttributeError:
        pass

    try:
        shcore = ctypes.windll.shcore
        shcore.SetProcessDpiAwareness.restype = ctypes.c_long
        result = shcore.SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE)
        if result in (0, E_ACCESSDENIED):
            _DPI_AWARENESS_SET = True
            return
    except AttributeError:
        pass

    try:
        user32.SetProcessDPIAware.restype = ctypes.c_bool
        user32.SetProcessDPIAware()
    except AttributeError:
        pass

    _DPI_AWARENESS_SET = True


def get_screen_bounds() -> ScreenBounds:
    ensure_dpi_awareness()

    user32 = ctypes.windll.user32
    left = int(user32.GetSystemMetrics(SM_XVIRTUALSCREEN))
    top = int(user32.GetSystemMetrics(SM_YVIRTUALSCREEN))
    width = int(user32.GetSystemMetrics(SM_CXVIRTUALSCREEN))
    height = int(user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))

    if width <= 0 or height <= 0:
        left = 0
        top = 0
        width = int(user32.GetSystemMetrics(SM_CXSCREEN))
        height = int(user32.GetSystemMetrics(SM_CYSCREEN))

    return ScreenBounds(
        left=left,
        top=top,
        width=max(width, 1),
        height=max(height, 1),
    )


def get_screen_size() -> tuple[int, int]:
    return get_screen_bounds().size


def get_system_dpi() -> int:
    ensure_dpi_awareness()

    user32 = ctypes.windll.user32
    try:
        return int(user32.GetDpiForSystem())
    except AttributeError:
        hdc = user32.GetDC(0)
        if not hdc:
            return DEFAULT_DPI

        try:
            dpi = int(ctypes.windll.gdi32.GetDeviceCaps(hdc, LOGPIXELSX))
            return dpi or DEFAULT_DPI
        finally:
            user32.ReleaseDC(0, hdc)


def get_scale_percent() -> int:
    return round(get_system_dpi() / DEFAULT_DPI * 100)


def format_display_profile() -> str:
    bounds = get_screen_bounds()
    return f"{bounds.width}x{bounds.height} @ {get_scale_percent()}%"


def normalize_point(x: int, y: int, bounds: ScreenBounds) -> tuple[float, float]:
    span_x = max(bounds.width - 1, 1)
    span_y = max(bounds.height - 1, 1)

    normalized_x = (x - bounds.left) / span_x
    normalized_y = (y - bounds.top) / span_y
    return round(_clamp(normalized_x), 8), round(_clamp(normalized_y), 8)


def denormalize_point(normalized_x: float, normalized_y: float, bounds: ScreenBounds) -> tuple[int, int]:
    span_x = max(bounds.width - 1, 1)
    span_y = max(bounds.height - 1, 1)

    x = bounds.left + round(_clamp(normalized_x) * span_x)
    y = bounds.top + round(_clamp(normalized_y) * span_y)
    return x, y


def scale_point(x: int, y: int, recorded_bounds: ScreenBounds, current_bounds: ScreenBounds) -> tuple[int, int]:
    span_x = max(recorded_bounds.width - 1, 1)
    span_y = max(recorded_bounds.height - 1, 1)

    normalized_x = (x - recorded_bounds.left) / span_x
    normalized_y = (y - recorded_bounds.top) / span_y
    return denormalize_point(normalized_x, normalized_y, current_bounds)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
