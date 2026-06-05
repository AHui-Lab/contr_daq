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
        self._set_force_acquisition_defaults()
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
            "forceDeviceLabel": "Dev",
            "forceSampleRateLabel": "Rate (Hz)",
            "forceTerminalConfigLabel": "Input",
            "forceVoltageRangeLabel": "Range",
            "forceFullScaleLabel": "Scale",
            "Forward_circle": "Forward Loop",
            "Backward_circle": "Backward Loop",
            "Emergency_Stop": "STOP",
            "autoRangeCheckBox": "Auto Y Range",
            "label_6": "Window",
            "label_8": "Y Min",
            "label_10": "Y Max",
            "label_12": "AO Voltage",
            "label_13": "Speed (mm/s)",
            "totalForceLabel": "Total: 0.00 N",
            "Force1_Label": "P1: 0.00 N",
            "Force2_Label": "P2: 0.00 N",
            "Force3_Label": "P3: 0.00 N",
            "Force4_Label": "P4: 0.00 N",
        }
        for object_name, text in text_map.items():
            widget = getattr(self.ui, object_name, None)
            if widget is not None and hasattr(widget, "setText"):
                widget.setText(text)

    def _set_force_acquisition_defaults(self) -> None:
        self._select_combo_text("forceModeComboBox", "Analog Voltage")
        self._select_combo_text("forceTerminalConfigComboBox", "DIFFERENTIAL")
        self._set_spinbox_value("forceSampleRateSpinBox", 2000)

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

        self._set_max_height("tabWidget_4", 104)
        self._set_min_height("groupBox_2", 126)
        self._set_max_height("groupBox_2", 140)
        self._set_max_height("widget_5", 80)
        self._stabilize_ai_channel_grid()
        self._compact_force_panel()
        self._set_min_height("groupBox_4", 232)
        self._set_max_height("groupBox_4", 248)
        self._set_min_height("daqPlotWidget", 108)
        self._set_min_height("forcePlotWidget", 102)
        self._set_min_height("groupBox_5", 170)
        self._set_max_height("groupBox_5", 180)
        self._set_min_height("groupBox_6", 300)
        self._set_min_width("forceStartButton", 104)
        self._set_min_width("forceZeroButton", 104)
        self._stabilize_force_value_labels()
        self._compact_motion_loop_panel()
        self._set_min_width("startStopButton", 92)
        self._set_min_width("aoControlButton", 92)
        self._set_min_width("recorderStartButton", 100)
        self._set_min_width("recorderStopButton", 100)
        self._set_min_height("Forward_circle", 30)
        self._set_min_height("Backward_circle", 30)
        self._set_max_height("Emergency_Stop", 42)
        self._set_min_width("tabWidget", 600)
        self._set_min_height("tabWidget", 640)
        self._set_max_width("tabWidget_3", 430)
        self._set_min_width("tabWidget_3", 360)
        self._set_min_height("tabWidget_3", 430)
        self._set_min_height("logTextEdit", 120)
        self._set_max_height("logTextEdit", 180)

        if hasattr(self.ui, "gridLayout_3"):
            self.ui.gridLayout_3.setContentsMargins(10, 10, 10, 10)
            self.ui.gridLayout_3.setSpacing(10)
            self._span_motion_sidebar()

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

    def _span_motion_sidebar(self) -> None:
        layout = getattr(self.ui, "gridLayout_3", None)
        motion_tabs = getattr(self.ui, "tabWidget_3", None)
        if layout is None or motion_tabs is None:
            return

        log_widget = getattr(self.ui, "logTextEdit", None)
        if log_widget is not None:
            layout.removeWidget(log_widget)
            if hasattr(log_widget, "setVisible"):
                log_widget.setVisible(True)

        layout.removeWidget(motion_tabs)
        layout.addWidget(motion_tabs, 0, 2, 2, 1)
        if hasattr(motion_tabs, "raise_"):
            motion_tabs.raise_()

        if log_widget is not None:
            layout.addWidget(log_widget, 2, 2, 1, 1)

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
            "forceStartButton": (3, 0),
            "forceZeroButton": (3, 1),
            "forceSampleRateLabel": (1, 0),
            "forceSampleRateSpinBox": (1, 1),
            "forceTerminalConfigLabel": (1, 2),
            "forceTerminalConfigComboBox": (1, 3),
            "forceVoltageRangeLabel": (2, 0),
            "forceVoltageRangeComboBox": (2, 1),
            "forceFullScaleLabel": (2, 2),
            "forceFullScaleSpinBox": (2, 3),
            "totalForceLabel": (3, 2),
            "Force1_Label": (4, 0),
            "Force2_Label": (4, 1),
            "Force3_Label": (4, 2),
            "Force4_Label": (4, 3),
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

        for column in range(4):
            if hasattr(layout, "setColumnStretch"):
                layout.setColumnStretch(column, 1)

    def _stabilize_ai_channel_grid(self) -> None:
        layout = getattr(self.ui, "gridLayout_8", None)
        if layout is not None:
            if hasattr(layout, "setSpacing"):
                layout.setSpacing(6)
            if hasattr(layout, "setContentsMargins"):
                layout.setContentsMargins(12, 10, 12, 10)
            for column in range(4):
                if hasattr(layout, "setColumnStretch"):
                    layout.setColumnStretch(column, 1)

        for index in range(16):
            checkbox = getattr(self.ui, f"ai{index}CheckBox", None)
            if checkbox is None:
                continue
            if hasattr(checkbox, "setMinimumWidth"):
                checkbox.setMinimumWidth(72)
            if hasattr(checkbox, "setMaximumWidth"):
                checkbox.setMaximumWidth(16777215)
            if hasattr(checkbox, "setMinimumHeight"):
                checkbox.setMinimumHeight(20)

    def _stabilize_force_value_labels(self) -> None:
        self._set_fixed_width("totalForceLabel", 120)
        self._set_min_height("totalForceLabel", 22)
        for widget_name in ("Force1_Label", "Force2_Label", "Force3_Label", "Force4_Label"):
            self._set_fixed_width(widget_name, 88)
            self._set_min_height(widget_name, 22)

    def _compact_motion_loop_panel(self) -> None:
        layout = getattr(self.ui, "gridLayout_11", None)
        if layout is None:
            return

        placement = {
            "Axis_choice": (0, 0),
            "direction_choice": (0, 1),
            "distanceSpinBox_2": (1, 0),
            "Gap_time": (1, 1),
            "Circle_times": (2, 0),
            "label_13": (2, 1),
            "Forward_circle": (3, 0),
            "Speed_Setting_val": (3, 1),
            "Backward_circle": (4, 0),
        }

        for object_name, position in placement.items():
            widget = getattr(self.ui, object_name, None)
            if widget is None:
                continue
            layout.removeWidget(widget)
            layout.addWidget(widget, *position)

        stop_button = getattr(self.ui, "Emergency_Stop", None)
        if stop_button is not None:
            layout.removeWidget(stop_button)
            layout.addWidget(stop_button, 5, 0, 1, 2)

        speed_label = getattr(self.ui, "label_13", None)
        if speed_label is not None and hasattr(speed_label, "setVisible"):
            speed_label.setVisible(True)

        for row in range(9):
            if hasattr(layout, "setRowMinimumHeight"):
                layout.setRowMinimumHeight(row, 0)
            if hasattr(layout, "setRowStretch"):
                layout.setRowStretch(row, 1 if row == 6 else 0)

        for column in range(2):
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

    def _set_fixed_width(self, widget_name: str, width: int) -> None:
        self._set_min_width(widget_name, width)
        self._set_max_width(widget_name, width)

    def _select_combo_text(self, widget_name: str, text: str) -> None:
        widget = getattr(self.ui, widget_name, None)
        if widget is None or not hasattr(widget, "findText") or not hasattr(widget, "setCurrentIndex"):
            return

        index = widget.findText(text)
        if index >= 0:
            widget.setCurrentIndex(index)

    def _set_spinbox_value(self, widget_name: str, value: int) -> None:
        widget = getattr(self.ui, widget_name, None)
        if widget is not None and hasattr(widget, "setValue"):
            widget.setValue(value)
