from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit, QPushButton, QLabel,
    QSpinBox, QComboBox, QColorDialog, QHBoxLayout, QTabWidget, QWidget,
    QKeySequenceEdit
)
from PyQt5.QtGui import QKeySequence, QColor


def _color_button(initial_rgb, on_pick):
    btn = QPushButton()
    btn.setFixedWidth(60)

    def _apply(rgb):
        btn.setStyleSheet(f"background-color: rgb({rgb[0]},{rgb[1]},{rgb[2]});")

    _apply(initial_rgb)

    def _clicked():
        c = QColorDialog.getColor(QColor(*initial_rgb))
        if c.isValid():
            rgb = (c.red(), c.green(), c.blue())
            _apply(rgb)
            on_pick(rgb)

    btn.clicked.connect(_clicked)
    return btn


class SettingsDialog(QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Settings")
        self.resize(420, 420)

        tabs = QTabWidget()
        tabs.addTab(self._hotkeys_tab(), "Hotkeys")
        tabs.addTab(self._appearance_tab(), "Click Colours")
        tabs.addTab(self._quality_tab(), "Custom Quality")

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _hotkeys_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        hk = self.cfg.get("hotkeys")

        note = QLabel("Restart the app after changing hotkeys for them to take effect.")
        note.setWordWrap(True)
        form.addRow(note)

        for action, label in [
            ("smart_recording", "Smart Recording"),
            ("screenshot", "Screenshot"),
            ("start", "Start Recording"),
            ("stop", "Stop Recording"),
            ("pause", "Pause / Resume"),
        ]:
            edit = QLineEdit(hk.get(action, ""))
            edit.setPlaceholderText("e.g. F9")

            def make_saver(a, e):
                def _save():
                    new_hk = dict(self.cfg.get("hotkeys"))
                    new_hk[a] = e.text().strip() or new_hk[a]
                    self.cfg.set("hotkeys", new_hk)
                return _save

            edit.editingFinished.connect(make_saver(action, edit))
            form.addRow(label, edit)
        return w

    def _appearance_tab(self):
        w = QWidget()
        form = QFormLayout(w)

        left_btn = _color_button(
            self.cfg.get("click_color_left"),
            lambda rgb: self.cfg.set("click_color_left", list(rgb)),
        )
        right_btn = _color_button(
            self.cfg.get("click_color_right"),
            lambda rgb: self.cfg.set("click_color_right", list(rgb)),
        )
        mid_btn = _color_button(
            self.cfg.get("click_color_middle"),
            lambda rgb: self.cfg.set("click_color_middle", list(rgb)),
        )
        form.addRow("Left click", left_btn)
        form.addRow("Right click", right_btn)
        form.addRow("Mouse wheel / middle click", mid_btn)

        radius_spin = QSpinBox()
        radius_spin.setRange(10, 80)
        radius_spin.setValue(self.cfg.get("click_max_radius", 32))
        radius_spin.valueChanged.connect(lambda v: self.cfg.set("click_max_radius", v))
        form.addRow("Max flash radius", radius_spin)

        fade_spin = QSpinBox()
        fade_spin.setRange(100, 2000)
        fade_spin.setSingleStep(50)
        fade_spin.setValue(self.cfg.get("click_fade_ms", 450))
        fade_spin.valueChanged.connect(lambda v: self.cfg.set("click_fade_ms", v))
        form.addRow("Fade duration (ms)", fade_spin)
        return w

    def _quality_tab(self):
        w = QWidget()
        form = QFormLayout(w)

        res = self.cfg.get("custom_resolution", [1920, 1080])
        w_spin = QSpinBox()
        w_spin.setRange(320, 7680)
        w_spin.setValue(res[0])
        h_spin = QSpinBox()
        h_spin.setRange(240, 4320)
        h_spin.setValue(res[1])

        def _save_res():
            self.cfg.set("custom_resolution", [w_spin.value(), h_spin.value()])

        w_spin.valueChanged.connect(_save_res)
        h_spin.valueChanged.connect(_save_res)

        res_row = QHBoxLayout()
        res_row.addWidget(w_spin)
        res_row.addWidget(QLabel("x"))
        res_row.addWidget(h_spin)
        res_container = QWidget()
        res_container.setLayout(res_row)
        form.addRow("Custom resolution", res_container)

        bitrate_spin = QSpinBox()
        bitrate_spin.setRange(1, 100)
        bitrate_spin.setValue(self.cfg.get("custom_bitrate_mbps", 12))
        bitrate_spin.valueChanged.connect(lambda v: self.cfg.set("custom_bitrate_mbps", v))
        form.addRow("Bitrate (Mbps)", bitrate_spin)

        note = QLabel("Select 'Custom' under Quality on the main window to use these.")
        note.setWordWrap(True)
        form.addRow(note)
        return w
