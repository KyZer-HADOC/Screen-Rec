"""
Resolves bundled resource paths (icons, etc.) so they work the same way
whether the app is run from source (`python main.py`) or from a PyInstaller
onedir/onefile build, where bundled data files live under `sys._MEIPASS`.
"""
import os
import sys


def resource_path(relative_path: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS  # noqa: SLF001
    else:
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(base, relative_path)


def icon_path() -> str:
    return resource_path(os.path.join("assets", "icon.ico"))
