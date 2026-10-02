DARK_STYLE = """
QWidget {
    background-color: #14161c;
    color: #e7e9ee;
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
}
QMainWindow {
    background-color: #14161c;
}
QLabel#Title {
    font-size: 20px;
    font-weight: 600;
    color: #ffffff;
}
QLabel#Subtitle {
    color: #8a8f9c;
    font-size: 12px;
}
QFrame#Card {
    background-color: #1c1f28;
    border-radius: 12px;
    border: 1px solid #2a2e3a;
}
QPushButton {
    background-color: #262a36;
    color: #e7e9ee;
    border: 1px solid #333747;
    border-radius: 8px;
    padding: 8px 14px;
}
QPushButton:hover {
    background-color: #303543;
    border-color: #4a5066;
}
QPushButton:pressed {
    background-color: #1f222c;
}
QPushButton#RecordButton {
    background-color: #e5484d;
    border: none;
    color: white;
    font-weight: 600;
    border-radius: 22px;
}
QPushButton#RecordButton:hover {
    background-color: #ff5b60;
}
QPushButton#RecordButton[recording="true"] {
    background-color: #6c6f7a;
}
QPushButton#StopButton {
    background-color: #2b2f3a;
    border: 1px solid #444a5c;
}
QComboBox, QSpinBox, QLineEdit {
    background-color: #20232c;
    border: 1px solid #333747;
    border-radius: 6px;
    padding: 5px 8px;
}
QComboBox::drop-down { border: none; }
QSlider::groove:horizontal {
    height: 4px;
    background: #333747;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #5b8cff;
    width: 14px;
    margin: -6px 0;
    border-radius: 7px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #444a5c;
    background: #20232c;
}
QCheckBox::indicator:checked {
    background: #5b8cff;
    border-color: #5b8cff;
}
QTabWidget::pane {
    border: 1px solid #2a2e3a;
    border-radius: 8px;
}
QTabBar::tab {
    background: #1c1f28;
    padding: 8px 16px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    color: #8a8f9c;
}
QTabBar::tab:selected {
    background: #262a36;
    color: white;
}
QStatusBar {
    background: #10121780;
    color: #8a8f9c;
}
"""
