# Macro Recorder MVP

This project is a Windows desktop MVP for recording keyboard and mouse input
and replaying it in loops.

## Features

- Global mouse and keyboard recording
- Save and load macros as JSON or editable TXT files
- TXT scripts store only action nodes and the interval between them
- Replay with loop count and speed multiplier
- `Esc` stops recording
- Per-macro global hotkeys with combo-key support
- Drag-to-reorder macro list with persistent custom ordering
- Basic coordinate scaling when screen resolution changes
- Automatic DPI-aware coordinate handling on Windows high-DPI displays
- Recorded macros are automatically saved and listed in the app
- Playback can be interrupted with `Esc`
- Macro files are stored under `macros/`

## Limitations

- It records input events, not video
- Raw coordinates are still sensitive to window position changes
- Elevated windows, games, or anti-cheat protected apps may ignore replayed input
- The current MVP does not support image matching or conditional branches
- Macros recorded before the DPI fix should be recorded again on high-DPI systems

## Run

```powershell
python main.py
```

Double-click `start_macro_recorder.vbs` for a no-console launch on Windows.

## Install

```powershell
pip install -r requirements.txt
```

## Test

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

## Release

Push a tag like `v0.1.0` to trigger the GitHub Actions workflow that builds the
Windows executable and publishes a GitHub Release.

```powershell
git tag v0.1.0
git push origin v0.1.0
```
