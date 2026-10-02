"""
Smart Screen Recorder - entry point.

Run with:  python main.py
Requires Windows + packages in requirements.txt (see README.md).
"""
import sys

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication

from core.resources import icon_path
from ui.main_window import MainWindow


def main():
    # On Windows, this groups the app under its own taskbar icon/identity
    # instead of being lumped in with generic python.exe processes.
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "KyZerHADOC.SmartScreenRecorder"
            )
        except Exception:  # noqa: BLE001
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("Smart Screen Recorder")
    app.setQuitOnLastWindowClosed(False)  # keep running in tray
    icon = QIcon(icon_path())
    if not icon.isNull():
        app.setWindowIcon(icon)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
