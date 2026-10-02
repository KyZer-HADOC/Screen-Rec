"""
A fullscreen, semi-transparent overlay that lets the user drag a rectangle
to pick the capture region (like a snipping tool). Returns (x, y, w, h) in
virtual-desktop coordinates, or None if cancelled with Esc.
"""
from PyQt5.QtCore import Qt, QRect, QPoint
from PyQt5.QtGui import QPainter, QColor, QPen
from PyQt5.QtWidgets import QWidget, QApplication


class RegionSelector(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)

        geo = QApplication.desktop().geometry()
        self.setGeometry(geo)

        self._origin = QPoint()
        self._current = QPoint()
        self._selecting = False
        self.result_rect = None

    def mousePressEvent(self, event):
        self._origin = event.pos()
        self._current = event.pos()
        self._selecting = True
        self.update()

    def mouseMoveEvent(self, event):
        if self._selecting:
            self._current = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        self._selecting = False
        rect = QRect(self._origin, self._current).normalized()
        if rect.width() > 5 and rect.height() > 5:
            self.result_rect = (rect.x(), rect.y(), rect.width(), rect.height())
        self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.result_rect = None
            self.close()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 90))
        if self._selecting:
            rect = QRect(self._origin, self._current).normalized()
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(rect, Qt.transparent)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            pen = QPen(QColor(80, 170, 255), 2)
            painter.setPen(pen)
            painter.drawRect(rect)

    @staticmethod
    def pick_region():
        """Blocking helper: shows the overlay and returns the chosen rect or None."""
        selector = RegionSelector()
        selector.showFullScreen()
        loop_app = QApplication.instance()
        selector_result = {"rect": None}

        def _on_close():
            selector_result["rect"] = selector.result_rect

        selector.destroyed.connect(_on_close)
        while selector.isVisible():
            loop_app.processEvents()
        return selector.result_rect
