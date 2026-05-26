from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy

from modules.app_state import AppState
from modules.ui.theme import STATUS_PILL_STYLE


class ViewBinder:
    def __init__(self, ui, state_provider: Callable[[], AppState]):
        self.ui = ui
        self.state_provider = state_provider
        self.status_labels: dict[str, QLabel] = {}

    def setup(self) -> None:
        self._apply_window_metadata()
        self._remove_placeholder_tabs()
        self._name_workbench_sections()
        self._tune_layout_density()
        self._build_status_bar()
        self.update_status()

    def refresh_static_text(self) -> None:
        self._name_workbench_sections()

    def update_status(self) -> None:
        summary = self.state_provider().summary
        for key, value in summary.items():
            label = self.status_labels.get(key)
            if label is not None:
                label.setText(f"{key.upper()}: {value}")

    def _apply_window_metadata(self) -> None:
        self.ui.setWindowTitle("NI-USB-6259 Control Workbench")
        self.ui.setMinimumSize(1280, 820)

    def _name_workbench_sections(self) -> None:
        self._set_tab_text("tabWidget", {0: "Camera 1", 1: "Camera 2"})
        self._set_tab_text("tabWidget_2", {0: "Acquisition"})
        self._set_tab_text("tabWidget_3", {0: "Motion"})
        self._set_tab_text("tabWidget_4", {0: "DAQ", 1: "IV"})

        self._set_title("groupBox", "Acquisition Control")
        self._set_title("groupBox_2", "AI Channels")
        self._set_title("groupBox_4", "Force Sensor")
        self._set_title("groupBox_5", "Manual Jog")
        self._set_title("groupBox_6", "Loop Motion")
        self._set_title("groupBox_7", "Channel Activity")

        text_map = {
            "startStopButton": "Start DAQ",
            "aoControlButton": "Output AO",
            "ivControlButton": "Start IV",
            "recorderStartButton": "Record",
            "recorderStopButton": "Stop Record",
            "forceStartButton": "Start Force",
            "forceZeroButton": "Zero",
            "Forward_circle": "Forward Loop",
            "Backward_circle": "Backward Loop",
            "Emergency_Stop": "Emergency Stop",
            "autoRangeCheckBox": "Auto Y Range",
            "label_6": "Window",
            "label_8": "Y Min",
            "label_10": "Y Max",
            "label_12": "AO Voltage",
            "label_13": "Speed",
            "totalForceLabel": "Total: 0.00 N",
            "Force1_Label": "P1: 0.00",
            "Force2_Label": "P2: 0.00",
            "Force3_Label": "P3: 0.00",
            "Force4_Label": "P4: 0.00",
        }
        for object_name, text in text_map.items():
            widget = getattr(self.ui, object_name, None)
            if widget is not None and hasattr(widget, "setText"):
                widget.setText(text)

    def _remove_placeholder_tabs(self) -> None:
        for widget_name, keep_count in (("tabWidget_2", 1), ("tabWidget_3", 1)):
            tab_widget = getattr(self.ui, widget_name, None)
            if tab_widget is None:
                continue
            while tab_widget.count() > keep_count:
                tab_widget.removeTab(tab_widget.count() - 1)

    def _tune_layout_density(self) -> None:
        for widget_name in ("daqPlotWidget", "forcePlotWidget", "Camera1", "Camera2"):
            widget = getattr(self.ui, widget_name, None)
            if widget is not None:
                widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        if hasattr(self.ui, "gridLayout_3"):
            self.ui.gridLayout_3.setContentsMargins(10, 10, 10, 10)
            self.ui.gridLayout_3.setSpacing(10)

        for layout_name in (
            "gridLayout",
            "gridLayout_2",
            "gridLayout_4",
            "gridLayout_5",
            "gridLayout_6",
            "gridLayout_7",
            "gridLayout_8",
            "gridLayout_9",
            "gridLayout_10",
            "gridLayout_11",
            "gridLayout_12",
        ):
            layout = getattr(self.ui, layout_name, None)
            if layout is not None:
                layout.setSpacing(8)

    def _build_status_bar(self) -> None:
        status_bar = self.ui.statusBar()
        status_bar.showMessage("Workbench ready")

        for key in ("daq", "camera", "motion", "force", "recording"):
            label = QLabel()
            label.setStyleSheet(STATUS_PILL_STYLE)
            label.setAlignment(Qt.AlignCenter)
            label.setMinimumWidth(110)
            status_bar.addPermanentWidget(label)
            self.status_labels[key] = label

    def _set_tab_text(self, widget_name: str, labels: dict[int, str]) -> None:
        tab_widget = getattr(self.ui, widget_name, None)
        if tab_widget is None:
            return
        for index, label in labels.items():
            if index < tab_widget.count():
                tab_widget.setTabText(index, label)

    def _set_title(self, widget_name: str, title: str) -> None:
        widget = getattr(self.ui, widget_name, None)
        if widget is not None and hasattr(widget, "setTitle"):
            widget.setTitle(title)
