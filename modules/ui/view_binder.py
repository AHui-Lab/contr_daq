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
        self._clear_legacy_inline_styles()
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
            "forceModeLabel": "Mode",
            "forceDeviceLabel": "Force DAQ",
            "forceSampleRateLabel": "Rate (Hz)",
            "forceTerminalConfigLabel": "Input",
            "forceVoltageRangeLabel": "Voltage",
            "forceFullScaleLabel": "Full Scale",
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

    def _clear_legacy_inline_styles(self) -> None:
        for widget_name in (
            "tabWidget",
            "tabWidget_2",
            "tabWidget_3",
            "tabWidget_4",
            "groupBox",
            "groupBox_2",
            "groupBox_4",
            "groupBox_5",
            "groupBox_6",
            "groupBox_7",
        ):
            widget = getattr(self.ui, widget_name, None)
            if widget is not None and hasattr(widget, "setStyleSheet"):
                widget.setStyleSheet("")

    def _tune_layout_density(self) -> None:
        for widget_name in ("daqPlotWidget", "forcePlotWidget", "Camera1", "Camera2"):
            widget = getattr(self.ui, widget_name, None)
            if widget is not None:
                widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._set_max_height("tabWidget_4", 126)
        self._set_min_height("groupBox_2", 118)
        self._set_max_height("groupBox_2", 150)
        self._set_max_height("widget_5", 96)
        self._compact_force_panel()
        self._set_min_height("groupBox_4", 155)
        self._set_max_height("groupBox_4", 175)
        self._set_min_height("daqPlotWidget", 225)
        self._set_min_height("forcePlotWidget", 185)
        self._set_min_height("groupBox_5", 180)
        self._set_min_height("groupBox_6", 230)
        self._set_min_width("forceStartButton", 120)
        self._set_min_width("forceZeroButton", 120)
        self._set_min_width("startStopButton", 92)
        self._set_min_width("aoControlButton", 92)
        self._set_min_width("recorderStartButton", 100)
        self._set_min_width("recorderStopButton", 100)
        self._set_max_height("Emergency_Stop", 42)
        self._set_min_width("tabWidget", 700)
        self._set_min_height("tabWidget", 640)
        self._set_max_width("tabWidget_3", 430)
        self._set_min_width("tabWidget_3", 340)
        self._set_min_height("tabWidget_3", 430)

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
                layout.setSpacing(6)

        for layout_name in ("gridLayout_5", "gridLayout_6", "gridLayout_9", "gridLayout_10", "gridLayout_11"):
            layout = getattr(self.ui, layout_name, None)
            if layout is not None and hasattr(layout, "setContentsMargins"):
                layout.setContentsMargins(8, 8, 8, 8)

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

    def _compact_force_panel(self) -> None:
        layout = getattr(self.ui, "gridLayout_6", None)
        if layout is None:
            return

        placement = {
            "forceModeLabel": (0, 0),
            "forceModeComboBox": (0, 1),
            "forceDeviceLabel": (0, 2),
            "forceDeviceComboBox": (0, 3),
            "forceStartButton": (0, 4),
            "forceZeroButton": (0, 5),
            "forceSampleRateLabel": (1, 0),
            "forceSampleRateSpinBox": (1, 1),
            "forceTerminalConfigLabel": (1, 2),
            "forceTerminalConfigComboBox": (1, 3),
            "forceVoltageRangeLabel": (1, 4),
            "forceVoltageRangeComboBox": (1, 5),
            "forceFullScaleLabel": (2, 0),
            "forceFullScaleSpinBox": (2, 1),
            "totalForceLabel": (2, 2),
            "Force1_Label": (2, 3),
            "Force2_Label": (2, 4),
            "Force3_Label": (2, 5),
            "Force4_Label": (2, 6),
        }

        for object_name, position in placement.items():
            widget = getattr(self.ui, object_name, None)
            if widget is None:
                continue
            layout.removeWidget(widget)
            layout.addWidget(widget, *position)

        redundant_label = getattr(self.ui, "label_11", None)
        if redundant_label is not None and hasattr(redundant_label, "setVisible"):
            redundant_label.setVisible(False)

        for column in range(7):
            if hasattr(layout, "setColumnStretch"):
                layout.setColumnStretch(column, 1)

    def _set_max_height(self, widget_name: str, height: int) -> None:
        widget = getattr(self.ui, widget_name, None)
        if widget is not None and hasattr(widget, "setMaximumHeight"):
            widget.setMaximumHeight(height)

    def _set_min_height(self, widget_name: str, height: int) -> None:
        widget = getattr(self.ui, widget_name, None)
        if widget is not None and hasattr(widget, "setMinimumHeight"):
            widget.setMinimumHeight(height)

    def _set_min_width(self, widget_name: str, width: int) -> None:
        widget = getattr(self.ui, widget_name, None)
        if widget is not None and hasattr(widget, "setMinimumWidth"):
            widget.setMinimumWidth(width)

    def _set_max_width(self, widget_name: str, width: int) -> None:
        widget = getattr(self.ui, widget_name, None)
        if widget is not None and hasattr(widget, "setMaximumWidth"):
            widget.setMaximumWidth(width)
