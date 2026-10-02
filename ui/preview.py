"""
Live preview panel: continuously grabs the currently configured capture
region (independent of whether a recording is running) and shows it as a
thumbnail, so the user can confirm framing before hitting Start. When
Smart Recording is enabled, the preview applies the same crop/zoom math
used by the real recorder so the zoom behaviour can be tuned by eye.
"""
import time

import mss
import numpy as np
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap, QCursor, QColor
from PyQt5.QtWidgets import QLabel, QVBoxLayout, QFrame, QSizePolicy

from core.zoom_engine import ZoomEngine

PREVIEW_FPS = 12


class PreviewPanel(QFrame):
    def __init__(self, cfg, recorder, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.recorder = recorder
        self.setObjectName("Card")

        layout = QVBoxLayout(self)
        header = QLabel("Live Preview")
        layout.addWidget(header)

        self.image_label = QLabel("Preview will appear here")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setMinimumHeight(260)
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.image_label.setStyleSheet(
            "background-color: #0c0d12; border-radius: 8px; color: #666;"
        )
        layout.addWidget(self.image_label)

        self.info_label = QLabel("")
        self.info_label.setObjectName("Subtitle")
        layout.addWidget(self.info_label)

        self._sct = None
        self._zoom_engine = None
        self._last_region_key = None
        self._last_tick_time = None

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(int(1000 / PREVIEW_FPS))

    def _ensure_sct(self):
        if self._sct is None:
            self._sct = mss.mss()
        return self._sct

    def _tick(self):
        # Nobody can see the preview when the window is hidden/minimised, and
        # grabbing the screen 12x/s competes with the real recorder for CPU.
        win = self.window()
        if win is None or not win.isVisible() or win.isMinimized():
            return
        try:
            region = self.recorder.get_preview_region()
        except Exception:
            return

        key = (region["left"], region["top"], region["width"], region["height"])
        if key != self._last_region_key or self._zoom_engine is None:
            self._zoom_engine = ZoomEngine(
                region["width"], region["height"],
                zoom_factor=self.cfg.get("zoom_factor", 2.0),
                smoothing=self.cfg.get("zoom_smoothing", 0.15),
            )
            self._last_region_key = key

        sct = self._ensure_sct()
        try:
            raw = sct.grab(region)
        except Exception:
            return
        frame = np.array(raw)[:, :, :3]  # BGRA -> BGR

        if self.cfg.get("smart_recording", False):
            self._zoom_engine.set_zoom_factor(self.cfg.get("zoom_factor", 2.0))
            self._zoom_engine.set_smoothing(self.cfg.get("zoom_smoothing", 0.15))
            now = time.perf_counter()
            dt = now - self._last_tick_time if self._last_tick_time else None
            self._last_tick_time = now
            cursor = QCursor.pos()
            lx = cursor.x() - region["left"]
            ly = cursor.y() - region["top"]
            x, y, w, h = self._zoom_engine.update(lx, ly, dt=dt)
            frame = frame[y:y + h, x:x + w]
        else:
            self._last_tick_time = None

        # BGR -> RGB for QImage, contiguous copy required
        rgb = np.ascontiguousarray(frame[:, :, ::-1])
        h, w, _ = rgb.shape
        qimg = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg).scaled(
            self.image_label.width(), self.image_label.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        self.image_label.setPixmap(pixmap)

        mode = self.cfg.get("mode", "fullscreen").title()
        zoom_note = " · Smart Zoom preview" if self.cfg.get("smart_recording", False) else ""
        self.info_label.setText(
            f"{mode} · {region['width']}x{region['height']}{zoom_note}"
        )

    def closeEvent(self, event):
        self.timer.stop()
        if self._sct:
            self._sct.close()
        super().closeEvent(event)
