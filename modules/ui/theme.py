LED_ON_STYLE = """
    background-color: #2eea78;
    border: 2px solid #1b9f56;
    border-radius: 9px;
"""

LED_OFF_STYLE = """
    background-color: #26313a;
    border: 1px solid #3c4b56;
    border-radius: 9px;
"""

INDUSTRIAL_GRAPH_CONFIG = {
    "background": "#0b0f14",
    "foreground": "#d8e1ea",
    "gridColor": "#2b3a45",
    "antialias": True,
}

STATUS_PILL_STYLE = """
    background-color: #17242d;
    border: 1px solid #2f4e60;
    border-radius: 4px;
    color: #d8e1ea;
    padding: 4px 8px;
    font-weight: 600;
"""

CAMERA_PREVIEW_STYLE = """
    background-color: #050708;
    border: 1px solid #26323b;
    border-radius: 6px;
    color: #7f93a5;
    font-size: 13px;
"""


def build_stylesheet() -> str:
    return """
QMainWindow {
    background-color: #10151a;
}

QWidget {
    background-color: #10151a;
    color: #d8e1ea;
    font-family: "Microsoft YaHei UI", "Segoe UI", Arial, sans-serif;
    font-size: 12px;
}

QGroupBox {
    background-color: #17202a;
    border: 1px solid #334757;
    border-radius: 6px;
    margin-top: 18px;
    padding: 12px 10px 10px 10px;
    font-weight: 600;
    color: #f4b860;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: #f4b860;
}

QTabWidget::pane {
    border: 1px solid #293946;
    border-radius: 6px;
    background-color: #111820;
    top: -1px;
}

QTabBar::tab {
    background-color: #18222c;
    border: 1px solid #293946;
    border-bottom: none;
    color: #91a5b5;
    padding: 7px 14px;
    margin-right: 2px;
    min-width: 58px;
}

QTabBar::tab:selected {
    background-color: #10151a;
    color: #73d5ff;
    border-top: 2px solid #73d5ff;
}

QTabBar::tab:hover:!selected {
    color: #d8e1ea;
    background-color: #202c37;
}

QPushButton {
    background-color: #22303a;
    border: 1px solid #3e5364;
    border-radius: 4px;
    color: #d8e1ea;
    padding: 6px 12px;
    min-height: 24px;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #2d3d49;
    border-color: #73d5ff;
    color: #ffffff;
}

QPushButton:pressed {
    background-color: #1f78a5;
    border-color: #73d5ff;
}

QPushButton:disabled {
    background-color: #182028;
    border-color: #26333d;
    color: #5d6d78;
}

QPushButton#startStopButton,
QPushButton#ivControlButton,
QPushButton#aoControlButton,
QPushButton#forceStartButton,
QPushButton#recorderStartButton {
    border-color: #2f8652;
}

QPushButton#startStopButton:hover,
QPushButton#ivControlButton:hover,
QPushButton#aoControlButton:hover,
QPushButton#forceStartButton:hover,
QPushButton#recorderStartButton:hover {
    background-color: #203a2b;
    border-color: #2eea78;
}

QPushButton#Emergency_Stop {
    background-color: #6f1717;
    border: 2px solid #d84545;
    color: #ffffff;
    min-height: 32px;
    font-weight: 700;
}

QPushButton#Emergency_Stop:hover {
    background-color: #8d2020;
    border-color: #ff6b6b;
}

QLineEdit,
QComboBox,
QSpinBox,
QDoubleSpinBox {
    background-color: #0b0f14;
    border: 1px solid #334757;
    border-radius: 4px;
    color: #9bd1ff;
    padding: 4px 7px;
    min-height: 22px;
}

QLineEdit:focus,
QComboBox:focus,
QSpinBox:focus,
QDoubleSpinBox:focus {
    border-color: #73d5ff;
}

QComboBox::drop-down {
    width: 22px;
    border-left: 1px solid #334757;
}

QComboBox QAbstractItemView {
    background-color: #111820;
    border: 1px solid #334757;
    selection-background-color: #1f78a5;
    selection-color: #ffffff;
}

QCheckBox {
    color: #b8c7d3;
    spacing: 6px;
}

QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border-radius: 3px;
    border: 1px solid #475b6a;
    background-color: #0b0f14;
}

QCheckBox::indicator:checked {
    background-color: #2eea78;
    border-color: #2eea78;
}

QLabel {
    color: #b8c7d3;
    background: transparent;
}

QLabel#totalForceLabel,
QLabel#Force1_Label,
QLabel#Force2_Label,
QLabel#Force3_Label,
QLabel#Force4_Label {
    color: #2eea78;
    font-family: Consolas, "Cascadia Mono", monospace;
    font-weight: 700;
}

QPlainTextEdit {
    background-color: #050708;
    border: 1px solid #26323b;
    border-radius: 6px;
    color: #68d391;
    font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 11px;
    padding: 8px;
}

QStatusBar {
    background-color: #0b0f14;
    border-top: 1px solid #26323b;
    color: #91a5b5;
}

QMenuBar {
    background-color: #0b0f14;
    border-bottom: 1px solid #26323b;
    color: #d8e1ea;
}

QToolTip {
    background-color: #17202a;
    border: 1px solid #73d5ff;
    color: #d8e1ea;
    padding: 5px;
}
"""


def apply_graph_theme(pg_module) -> None:
    _set_graph_option(pg_module, "background", INDUSTRIAL_GRAPH_CONFIG["background"])
    _set_graph_option(pg_module, "foreground", INDUSTRIAL_GRAPH_CONFIG["foreground"])
    _set_graph_option(pg_module, "gridColor", INDUSTRIAL_GRAPH_CONFIG["gridColor"])
    pg_module.setConfigOptions(antialias=INDUSTRIAL_GRAPH_CONFIG["antialias"])


def _set_graph_option(pg_module, key: str, value: str) -> None:
    try:
        pg_module.setConfigOption(key, value)
    except KeyError:
        return


def style_led_widget(widget, on: bool) -> None:
    widget.setStyleSheet(LED_ON_STYLE if on else LED_OFF_STYLE)


def patch_led_manager(led_manager) -> None:
    def set_led(index: int, on: bool) -> None:
        widget = getattr(led_manager.ui, f"led{index}Widget", None)
        if widget is not None:
            style_led_widget(widget, on)

    led_manager.set_led = set_led
    led_manager.reset_all()
