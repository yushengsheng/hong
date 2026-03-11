from __future__ import annotations

from dataclasses import dataclass
import sys
from typing import Collection


WINDOWS_UI_FONT_CANDIDATES = (
    "Microsoft YaHei UI",
    "Microsoft JhengHei UI",
    "DengXian",
    "Microsoft YaHei",
    "Microsoft JhengHei",
    "Segoe UI",
)


@dataclass(frozen=True, slots=True)
class UIFontSet:
    family: str
    small: tuple[str, int]
    body: tuple[str, int]
    body_bold: tuple[str, int, str]
    title: tuple[str, int, str]
    stage: tuple[str, int, str]


def choose_ui_font_family(
    available_families: Collection[str],
    *,
    platform: str = sys.platform,
) -> str:
    if platform == "win32":
        for family in WINDOWS_UI_FONT_CANDIDATES:
            if family in available_families:
                return family

    return "TkDefaultFont"


def build_ui_fonts(
    available_families: Collection[str],
    *,
    platform: str = sys.platform,
) -> UIFontSet:
    family = choose_ui_font_family(available_families, platform=platform)
    if platform == "win32":
        return UIFontSet(
            family=family,
            small=(family, 9),
            body=(family, 10),
            body_bold=(family, 10, "bold"),
            title=(family, 11, "bold"),
            stage=(family, 18, "bold"),
        )

    return UIFontSet(
        family=family,
        small=(family, 8),
        body=(family, 9),
        body_bold=(family, 9, "bold"),
        title=(family, 10, "bold"),
        stage=(family, 17, "bold"),
    )
