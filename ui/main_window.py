import os
import sys
import time

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSpinBox, QSlider, QCheckBox, QFrame, QFileDialog,
    QLineEdit, QGridLayout, QSizePolicy, QMessageBox
)

from core.config import Config
from core.hotkeys import HotkeyManager
from core.recorder import Recorder, RecordingState
from core.region_selector import RegionSelector
from core.resources import icon_path
from ui.styles import DARK_STYLE
from ui.settings_dialog import SettingsDialog
from ui.tray import Tray
from ui.preview import PreviewPanel


class Signals(QObject):
    status = pyqtSignal(str)
    error = pyqtSignal(str)


class StopWorker(QThread):
    finished_path = pyqtSignal(str)

    def __init__(self, recorder):
        super().__init__()
        self.recorder = recorder

    def run(self):
        path = self.recorder.stop()
        self.finished_path.emit(path or "")


def _card():
    frame = QFrame()
    frame.setObjectName("Card")
    return frame


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = Config()
        self.setWindowTitle("Smart Screen Recorder")
        self.resize(920, 820)
        self.setStyleSheet(DARK_STYLE)
        self._app_icon = QIcon(icon_path())
        if not self._app_icon.isNull():
            self.setWindowIcon(self._app_icon)

        self.signals = Signals()
        self.signals.status.connect(self._on_status)
        self.signals.error.connect(self._on_error)

        self.recorder = Recorder(
            self.cfg,
            on_status=lambda s: self.signals.status.emit(s),
            on_error=lambda e: self.signals.error.emit(e),
        )

        self.hotkeys = HotkeyManager()
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)
        self._record_start_time = None

        self._build_ui()
        self._bind_hotkeys()

        tray_icon = self._app_icon if not self._app_icon.isNull() else QIcon.fromTheme("media-record")
        self.tray = Tray(self, tray_icon)
        if self.cfg.get("minimize_to_tray", True):
            self.tray.show()

    # ---------------- UI BUILD ----------------

    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Smart Screen Recorder")
        title.setObjectName("Title")
        subtitle = QLabel("F9 Smart Zoom · F10 Screenshot · F11 Start · F12 Stop · F8 Pause")
        subtitle.setObjectName("Subtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()
        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self._open_settings)
        header.addWidget(settings_btn)
        root.addLayout(header)

        self.preview_panel = PreviewPanel(self.cfg, self.recorder)
        root.addWidget(self.preview_panel, stretch=1)

        grid = QGridLayout()
        grid.setSpacing(16)
        grid.addWidget(self._build_mode_card(), 0, 0)
        grid.addWidget(self._build_smart_card(), 0, 1)
        grid.addWidget(self._build_audio_card(), 1, 0)
        grid.addWidget(self._build_output_card(), 1, 1)
        root.addLayout(grid)

        root.addLayout(self._build_controls())

        self.status_label = QLabel("Idle")
        self.status_label.setObjectName("Subtitle")
        root.addWidget(self.status_label)

        self.setCentralWidget(central)

    def _build_mode_card(self):
        card = _card()
        lay = QVBoxLayout(card)
        lay.addWidget(QLabel("Capture Mode"))

        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Full Screen", "Selected Area", "Display", "Gaming"])
        mode_map = {"fullscreen": 0, "area": 1, "display": 2, "gaming": 3}
        self.mode_combo.setCurrentIndex(mode_map.get(self.cfg.get("mode"), 0))
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        lay.addWidget(self.mode_combo)

        self.pick_area_btn = QPushButton("Pick Area on Screen")
        self.pick_area_btn.clicked.connect(self._pick_area)
        lay.addWidget(self.pick_area_btn)

        row = QHBoxLayout()
        row.addWidget(QLabel("FPS"))
        self.fps_spin = QSpinBox()
        self.fps_spin.setRange(10, 120)
        self.fps_spin.setValue(self.cfg.get("fps", 30))
        self.fps_spin.valueChanged.connect(lambda v: self.cfg.set("fps", v))
        row.addWidget(self.fps_spin)
        lay.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Quality"))
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Low", "Medium", "High", "Custom"])
        q_map = {"low": 0, "medium": 1, "high": 2, "custom": 3}
        self.quality_combo.setCurrentIndex(q_map.get(self.cfg.get("quality"), 2))
        self.quality_combo.currentTextChanged.connect(
            lambda t: self.cfg.set("quality", t.lower())
        )
        row2.addWidget(self.quality_combo)
        lay.addLayout(row2)

        self._on_mode_changed(self.mode_combo.currentIndex())
        return card

    def _build_smart_card(self):
        card = _card()
        lay = QVBoxLayout(card)
        lay.addWidget(QLabel("Smart Recording (cursor-follow zoom)"))

        self.smart_check = QCheckBox("Enable Smart Recording  (F9)")
        self.smart_check.setChecked(self.cfg.get("smart_recording", False))
        self.smart_check.stateChanged.connect(
            lambda s: self.cfg.set("smart_recording", bool(s))
        )
        lay.addWidget(self.smart_check)

        lay.addWidget(QLabel("Zoom amount"))
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(10, 40)  # maps to 1.0x - 4.0x
        self.zoom_slider.setValue(int(self.cfg.get("zoom_factor", 2.0) * 10))
        self.zoom_slider.valueChanged.connect(
            lambda v: self.cfg.set("zoom_factor", v / 10.0)
        )
        lay.addWidget(self.zoom_slider)

        lay.addWidget(QLabel("Follow smoothness"))
        self.smooth_slider = QSlider(Qt.Horizontal)
        self.smooth_slider.setRange(5, 60)
        self.smooth_slider.setValue(int(self.cfg.get("zoom_smoothing", 0.15) * 100))
        self.smooth_slider.valueChanged.connect(
            lambda v: self.cfg.set("zoom_smoothing", v / 100.0)
        )
        lay.addWidget(self.smooth_slider)

        self.clicks_check = QCheckBox("Show colour-coded clicks "
                                       "(Left=Blue, Right=Red, Wheel=Yellow)")
        self.clicks_check.setChecked(self.cfg.get("show_clicks", True))
        self.clicks_check.stateChanged.connect(
            lambda s: self.cfg.set("show_clicks", bool(s))
        )
        lay.addWidget(self.clicks_check)
        return card

    def _build_audio_card(self):
        card = _card()
        lay = QVBoxLayout(card)
        lay.addWidget(QLabel("Audio"))

        self.mic_check = QCheckBox("Record Microphone")
        self.mic_check.setChecked(self.cfg.get("record_mic", True))
        self.mic_check.stateChanged.connect(lambda s: self.cfg.set("record_mic", bool(s)))
        lay.addWidget(self.mic_check)

        self.sys_check = QCheckBox("Record System / Desktop Audio")
        self.sys_check.setChecked(self.cfg.get("record_system_audio", True))
        self.sys_check.stateChanged.connect(
            lambda s: self.cfg.set("record_system_audio", bool(s))
        )
        lay.addWidget(self.sys_check)

        note = QLabel("System audio uses WASAPI loopback (Windows only).")
        note.setObjectName("Subtitle")
        lay.addWidget(note)
        return card

    def _build_output_card(self):
        card = _card()
        lay = QVBoxLayout(card)
        lay.addWidget(QLabel("Save Location"))

        row = QHBoxLayout()
        self.save_dir_edit = QLineEdit(self.cfg.get("save_dir"))
        self.save_dir_edit.setReadOnly(True)
        row.addWidget(self.save_dir_edit)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._browse_save_dir)
        row.addWidget(browse_btn)
        lay.addLayout(row)

        hint = QLabel("Hotkeys: F9 Smart Zoom · F10 Screenshot · F11 Start\n"
                       "F12 Stop · F8 Pause / Resume")
        hint.setObjectName("Subtitle")
        lay.addWidget(hint)
        return card

    def _build_controls(self):
        row = QHBoxLayout()
        row.addStretch()

        self.screenshot_btn = QPushButton("Screenshot (F10)")
        self.screenshot_btn.clicked.connect(self.take_screenshot)
        row.addWidget(self.screenshot_btn)

        self.pause_btn = QPushButton("Pause (F8)")
        self.pause_btn.clicked.connect(self.toggle_pause)
        row.addWidget(self.pause_btn)

        self.record_btn = QPushButton("● Start (F11)")
        self.record_btn.setObjectName("RecordButton")
        self.record_btn.setFixedSize(140, 44)
        self.record_btn.clicked.connect(self._toggle_record_button)
        row.addWidget(self.record_btn)

        self.stop_btn = QPushButton("■ Stop (F12)")
        self.stop_btn.setObjectName("StopButton")
        self.stop_btn.clicked.connect(self.stop_recording)
        row.addWidget(self.stop_btn)

        self.status_dot = QLabel()
        self.status_dot.setFixedSize(12, 12)
        self._set_status_dot("idle")
        row.addWidget(self.status_dot)

        self.elapsed_label = QLabel("00:00")
        row.addWidget(self.elapsed_label)
        row.addStretch()
        return row

    def _set_status_dot(self, state):
        colors = {"idle": "#555b6b", "recording": "#e5484d", "paused": "#e0a93a"}
        color = colors.get(state, "#555b6b")
        self.status_dot.setStyleSheet(
            f"background-color: {color}; border-radius: 6px;"
        )

    # ---------------- ACTIONS ----------------

    def _on_mode_changed(self, index):
        modes = ["fullscreen", "area", "display", "gaming"]
        mode = modes[index]
        self.cfg.set("mode", mode)
        self.pick_area_btn.setEnabled(mode == "area")

    def _pick_area(self):
        self.showMinimized()
        time.sleep(0.2)
        rect = RegionSelector.pick_region()
        self.showNormal()
        if rect:
            self.cfg.set("area_rect", list(rect))
            self.status_label.setText(f"Area selected: {rect}")

    def _browse_save_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Choose Save Folder",
                                              self.cfg.get("save_dir"))
        if d:
            self.cfg.set("save_dir", d)
            self.save_dir_edit.setText(d)

    def _open_settings(self):
        dlg = SettingsDialog(self.cfg, self)
        dlg.exec_()

    def _bind_hotkeys(self):
        hk = self.cfg.get("hotkeys")
        self.hotkeys.register("smart_recording", hk["smart_recording"],
                               self._hotkey_toggle_smart)
        self.hotkeys.register("screenshot", hk["screenshot"], self._hotkey_screenshot)
        self.hotkeys.register("start", hk["start"], self._hotkey_start)
        self.hotkeys.register("stop", hk["stop"], self._hotkey_stop)
        self.hotkeys.register("pause", hk["pause"], self._hotkey_pause)

    # hotkey callbacks run on a background thread -> hop to GUI thread via signal
    def _hotkey_toggle_smart(self):
        self.signals.status.emit("__toggle_smart__")

    def _hotkey_screenshot(self):
        self.signals.status.emit("__screenshot__")

    def _hotkey_start(self):
        self.signals.status.emit("__start__")

    def _hotkey_stop(self):
        self.signals.status.emit("__stop__")

    def _hotkey_pause(self):
        self.signals.status.emit("__pause__")

    def start_recording(self):
        if self.recorder.state != RecordingState.IDLE:
            return
        try:
            self.recorder.start()
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Could not start recording:\n{e}")
            return
        self.record_btn.setText("● Recording…")
        self.record_btn.setProperty("recording", "true")
        self._set_status_dot("recording")
        self._record_start_time = time.time()
        self._elapsed_timer.start(1000)

    def stop_recording(self):
        if self.recorder.state == RecordingState.IDLE:
            return
        self.status_label.setText("Saving…")
        self._elapsed_timer.stop()
        self.record_btn.setText("● Start (F11)")
        self.record_btn.setProperty("recording", "false")
        self._set_status_dot("idle")
        self._stop_worker = StopWorker(self.recorder)
        self._stop_worker.finished_path.connect(self._on_saved)
        self._stop_worker.start()

    def _on_saved(self, path):
        if path:
            self.status_label.setText(f"Saved: {path}")
        else:
            self.status_label.setText("Idle")

    def toggle_pause(self):
        self.recorder.toggle_pause()

    def take_screenshot(self):
        try:
            path = self.recorder.screenshot()
            self.status_label.setText(f"Screenshot saved: {path}")
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Screenshot failed", str(e))

    def _toggle_record_button(self):
        if self.recorder.state == RecordingState.IDLE:
            self.start_recording()
        else:
            self.stop_recording()

    def _tick_elapsed(self):
        if self._record_start_time:
            secs = int(time.time() - self._record_start_time)
            self.elapsed_label.setText(f"{secs // 60:02d}:{secs % 60:02d}")

    def _on_status(self, msg):
        if msg == "__toggle_smart__":
            self.smart_check.setChecked(not self.smart_check.isChecked())
            return
        if msg == "__screenshot__":
            self.take_screenshot()
            return
        if msg == "__start__":
            self.start_recording()
            return
        if msg == "__stop__":
            self.stop_recording()
            return
        if msg == "__pause__":
            self.toggle_pause()
            return
        if msg.startswith("screenshot_saved:"):
            self.status_label.setText(msg.replace("screenshot_saved:", "Screenshot saved: "))
            return
        pretty = {
            "recording_started": "Recording…",
            "paused": "Paused",
            "resumed": "Recording…",
            "stopped": "Idle",
        }
        if msg == "paused":
            self._set_status_dot("paused")
        elif msg == "resumed":
            self._set_status_dot("recording")
        self.status_label.setText(pretty.get(msg, msg))

    def _on_error(self, msg):
        QMessageBox.warning(self, "Warning", msg)

    def quit_app(self):
        self.hotkeys.unregister_all()
        if self.recorder.state != RecordingState.IDLE:
            self.recorder.stop()
        self.tray.hide()
        sys.exit(0)

    def closeEvent(self, event):
        if self.cfg.get("minimize_to_tray", True):
            event.ignore()
            self.hide()
            self.preview_panel.timer.stop()
        else:
            self.quit_app()

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, "preview_panel") and not self.preview_panel.timer.isActive():
            self.preview_panel.timer.start(int(1000 / 12))
