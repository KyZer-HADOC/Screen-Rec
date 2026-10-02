from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction


class Tray(QSystemTrayIcon):
    def __init__(self, main_window, icon: QIcon):
        super().__init__(icon, main_window)
        self.main_window = main_window
        self.setToolTip("Smart Screen Recorder")

        menu = QMenu()
        show_action = QAction("Open", main_window)
        show_action.triggered.connect(self._show_window)
        menu.addAction(show_action)

        start_action = QAction("Start Recording (F11)", main_window)
        start_action.triggered.connect(main_window.start_recording)
        menu.addAction(start_action)

        stop_action = QAction("Stop Recording (F12)", main_window)
        stop_action.triggered.connect(main_window.stop_recording)
        menu.addAction(stop_action)

        menu.addSeparator()
        quit_action = QAction("Quit", main_window)
        quit_action.triggered.connect(main_window.quit_app)
        menu.addAction(quit_action)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._show_window()

    def _show_window(self):
        self.main_window.showNormal()
        self.main_window.activateWindow()
