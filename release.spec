# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_root = Path(SPECPATH).resolve().parent
macros_dir = project_root / "macros"

datas = []
if macros_dir.exists():
    for macro_file in macros_dir.rglob("*"):
        if macro_file.is_file():
            relative_parent = macro_file.relative_to(macros_dir).parent
            target_dir = Path("macros") / relative_parent
            datas.append((str(macro_file), str(target_dir)))


a = Analysis(
    ["launch.pyw"],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="宏录制器",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="宏录制器",
)
