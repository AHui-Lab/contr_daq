from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QWidget,
)

from modules.app_state import AppState
from modules.app_runtime import RuntimeStatus
from modules.ui.i18n import Translator
from modules.ui.theme import (
    STATUS_PILL_ERROR_STYLE,
    STATUS_PILL_RUNNING_STYLE,
    STATUS_PILL_STYLE,
    STATUS_PILL_WARNING_STYLE,
)


class ViewBinder:
    STATUS_KEYS = ("daq", "camera", "motion", "force", "recording")

    def __init__(self, ui, state_provider: Callable[[], AppState], translator=None, runtime=None):
        self.ui = ui
        self.state_provider = state_provider
        self.translator = translator or Translator("en")
        self.runtime = runtime
        self.status_labels: dict[str, QLabel] = {}
        self.workspace = None

    def setup(self) -> None:
        self._apply_window_metadata()
        self._clear_legacy_inline_styles()
        self._remove_placeholder_tabs()
        self._name_workbench_sections()
        self._set_force_acquisition_defaults()
        self._tune_layout_density()
        self._build_stage_two_shell()
        self._build_status_bar()
        self.update_status()

    def refresh_static_text(self) -> None:
        self._apply_window_metadata()
        self._name_workbench_sections()
        status_bar = self.ui.statusBar()
        status_bar.showMessage(self.translator("status.ready_message"))
        if self.workspace is not None:
            self.workspace.retranslate()
        self.update_status()

    def update_status(self) -> None:
        state = self.state_provider()
        for key in self.STATUS_KEYS:
            label = self.status_labels.get(key)
            if label is not None:
                label.setText(
                    f"{self.translator(f'status.{key}')}: {self._status_text(key, state)}"
                )
                label.setStyleSheet(self._status_style(key, state))
                if self.runtime is not None and key != "camera":
                    entry = self.runtime.get(key)
                    if hasattr(label, "setToolTip"):
                        label.setToolTip(entry.detail or label.text())
        self._update_action_text(state)
        if self.workspace is not None:
            self.workspace.update(state, self.runtime)

    def _apply_window_metadata(self) -> None:
        self.ui.setWindowTitle(self.translator("app.title"))
        self.ui.setMinimumSize(1180, 800)

    def _name_workbench_sections(self) -> None:
        t = self.translator
        self._set_tab_text("tabWidget", {0: t("tab.camera_1"), 1: t("tab.camera_2")})
        self._set_tab_text("tabWidget_2", {0: t("tab.acquisition")})
        self._set_tab_text("tabWidget_3", {0: t("tab.motion")})
        self._set_tab_text("tabWidget_4", {0: t("tab.daq"), 1: t("tab.iv")})

        self._set_title("groupBox", t("group.acquisition"))
        self._set_title("groupBox_2", t("group.ai_channels"))
        self._set_title("groupBox_4", t("group.force"))
        self._set_title("groupBox_5", t("group.manual_jog"))
        self._set_title("groupBox_6", t("group.led_scan"))
        self._set_title("groupBox_7", t("group.channel_activity"))

        text_map = {
            "startStopButton": t("button.daq.start"),
            "aoControlButton": t("button.ao.start"),
            "ivControlButton": t("button.iv.start"),
            "recorderStartButton": t("button.record.start"),
            "recorderStopButton": t("button.record.stop"),
            "forceStartButton": t("button.force.start"),
            "forceZeroButton": t("button.force.zero"),
            "forceModeLabel": t("label.mode"),
            "forceDeviceLabel": t("label.device"),
            "forceSampleRateLabel": t("label.rate_hz"),
            "forceTerminalConfigLabel": t("label.input"),
            "forceVoltageRangeLabel": t("label.range"),
            "forceFullScaleLabel": t("label.scale"),
            "Forward_circle": t("button.scan.start"),
            "Backward_circle": t("button.scan.cancel"),
            "Emergency_Stop": t("button.motion.stop"),
            "autoRangeCheckBox": t("label.auto_y"),
            "label_6": t("label.window"),
            "label_8": t("label.y_min"),
            "label_10": t("label.y_max"),
            "label_12": t("label.ao_voltage"),
            "label_13": t("label.speed"),
            "scanAxisLabel": t("label.scan_axis"),
            "scanDirectionLabel": t("label.scan_direction"),
            "scanLedCountLabel": t("label.led_count"),
            "scanLedSizeLabel": t("label.led_size"),
            "scanDistanceLabel": t("label.scan_distance"),
            "forceHoldEnableCheckBox": t("force_hold.enable"),
            "forceHoldToleranceLabel": t("force_hold.tolerance"),
            "forceHoldStepLabel": t("force_hold.z_step"),
            "label_2": t("label.device"),
            "label": t("label.rate_hz"),
            "label_3": t("label.repeat"),
            "label_9": t("label.start_voltage"),
            "label_5": t("label.step_voltage"),
            "label_4": t("label.stop_voltage"),
            "ivModeLabel": t("label.iv_mode"),
            "totalForceLabel": t("force.total", value="0.00"),
            "Force1_Label": t("force.point", index=1, value="0.00"),
            "Force2_Label": t("force.point", index=2, value="0.00"),
            "Force3_Label": t("force.point", index=3, value="0.00"),
            "Force4_Label": t("force.point", index=4, value="0.00"),
        }
        for object_name, text in text_map.items():
            widget = getattr(self.ui, object_name, None)
            if widget is not None and hasattr(widget, "setText"):
                widget.setText(text)

        self._apply_iv_compact_text()

        self._translate_combo_items(
            "ivModeComboBox",
            (
                ("Forward", "mode.iv.forward"),
                ("Reverse", "mode.iv.reverse"),
                ("Forward-Backward", "mode.iv.forward_backward"),
            ),
        )
        self._translate_combo_items(
            "forceModeComboBox",
            (("serial", "mode.force.serial"), ("analog", "mode.force.analog")),
        )
        self._translate_combo_items(
            "direction_choice",
            ((1, "mode.motion.forward"), (-1, "mode.motion.reverse")),
        )

    def _set_force_acquisition_defaults(self) -> None:
        self._select_combo_text("forceModeComboBox", self.translator("mode.force.analog"))
        self._select_combo_text("forceTerminalConfigComboBox", "DIFFERENTIAL")
        self._set_spinbox_value("forceSampleRateSpinBox", 2000)
        full_scale = getattr(self.ui, "forceFullScaleSpinBox", None)
        if full_scale is not None and hasattr(full_scale, "setDecimals"):
            full_scale.setDecimals(4)
        if full_scale is not None and hasattr(full_scale, "setSuffix"):
            full_scale.setSuffix(" N/ch")
        self._set_spinbox_value("forceFullScaleSpinBox", 98.0665)

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

        self._set_min_height("tabWidget_4", 108)
        self._set_max_height("tabWidget_4", 118)
        self._stabilize_iv_panel()
        self._set_min_height("groupBox_2", 102)
        self._set_max_height("groupBox_2", 106)
        self._set_min_height("widget_5", 68)
        self._set_max_height("widget_5", 68)
        self._compact_force_panel()
        self._set_min_height("groupBox_4", 154)
        self._set_max_height("groupBox_4", 190)
        self._set_min_height("daqPlotWidget", 88)
        self._set_min_height("forcePlotWidget", 168)
        self._set_min_height("groupBox_5", 170)
        self._set_max_height("groupBox_5", 180)
        self._set_min_height("groupBox_6", 380)
        self._set_min_width("forceStartButton", 88)
        self._set_min_width("forceZeroButton", 88)
        self._stabilize_force_value_labels()
        self._configure_scan_panel()
        self._set_min_width("daqDeviceComboBox", 100)
        self._set_min_width("startStopButton", 92)
        self._set_min_width("aoControlButton", 96)
        self._set_min_width("recorderStartButton", 100)
        self._set_min_width("recorderStopButton", 100)
        self._set_min_height("Forward_circle", 24)
        self._set_min_height("Backward_circle", 24)
        self._set_max_height("Emergency_Stop", 42)
        self._set_min_width("tabWidget", 360)
        self._set_min_height("tabWidget", 360)
        self._set_min_height("Camera1", 300)
        self._set_min_height("Camera2", 300)
        self._set_min_height("groupBox_7", 64)
        self._set_max_height("groupBox_7", 72)
        self._set_max_width("tabWidget_3", 430)
        self._set_min_width("tabWidget_3", 300)
        self._set_min_height("tabWidget_3", 420)
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

        for layout_name in ("gridLayout_5", "gridLayout_9", "gridLayout_10", "gridLayout_11"):
            layout = getattr(self.ui, layout_name, None)
            if layout is not None and hasattr(layout, "setContentsMargins"):
                layout.setContentsMargins(8, 8, 8, 8)

        acquisition_layout = getattr(self.ui, "verticalLayout_2", None)
        if acquisition_layout is not None and hasattr(acquisition_layout, "setSpacing"):
            acquisition_layout.setSpacing(6)
        self._compact_acquisition_controls()
        self._stabilize_ai_channel_grid()
        self._compact_scan_controls()

    def _build_stage_two_shell(self) -> None:
        central_widget = getattr(self.ui, "centralWidget", None)
        if not callable(central_widget) or not hasattr(self.ui, "addDockWidget"):
            return
        from modules.ui.workbench_layout import WorkbenchLayout

        self.workspace = WorkbenchLayout(self.ui, self.translator)

    def _build_status_bar(self) -> None:
        status_bar = self.ui.statusBar()
        status_bar.showMessage(self.translator("status.ready_message"))

        for key in self.STATUS_KEYS:
            label = QLabel()
            label.setStyleSheet(STATUS_PILL_STYLE)
            label.setAlignment(Qt.AlignCenter)
            label.setMinimumWidth(84)
            status_bar.addPermanentWidget(label)
            self.status_labels[key] = label

    def _status_text(self, key: str, state: AppState) -> str:
        if key == "camera":
            if state.camera_1_running and state.camera_2_running:
                return self.translator("state.both")
            if state.camera_1_running:
                return "1"
            if state.camera_2_running:
                return "2"
            return self.translator("state.idle")

        if self.runtime is not None:
            entry = self.runtime.get(key)
            return self.translator(f"state.{entry.status.value}")

        running = {
            "daq": state.daq_running,
            "ao": getattr(state, "ao_running", False),
            "iv": getattr(state, "iv_running", False),
            "motion": state.motion_running,
            "force": state.force_running,
            "recording": state.recording,
        }.get(key, False)
        if key == "recording":
            return self.translator("state.on" if running else "state.off")
        return self.translator("state.running" if running else "state.ready")

    def _update_action_text(self, state: AppState) -> None:
        action_map = {
            "startStopButton": ("daq", "button.daq.start", "button.daq.stop"),
            "aoControlButton": ("ao", "button.ao.start", "button.ao.stop"),
            "ivControlButton": ("iv", "button.iv.start", "button.iv.stop"),
            "forceStartButton": ("force", "button.force.start", "button.force.stop"),
        }
        for widget_name, (subsystem, start_key, stop_key) in action_map.items():
            if self.runtime is not None:
                active = self.runtime.get(subsystem).status in (
                    RuntimeStatus.CONNECTING,
                    RuntimeStatus.RUNNING,
                    RuntimeStatus.STOPPING,
                )
            else:
                active = bool(getattr(state, f"{subsystem}_running", False))
            widget = getattr(self.ui, widget_name, None)
            if widget is not None and hasattr(widget, "setText"):
                widget.setText(self.translator(stop_key if active else start_key))

    def _status_style(self, key: str, state: AppState) -> str:
        if self.runtime is not None and key != "camera":
            status = self.runtime.get(key).status
        else:
            running = {
                "daq": state.daq_running,
                "ao": getattr(state, "ao_running", False),
                "iv": getattr(state, "iv_running", False),
                "camera": state.camera_1_running or state.camera_2_running,
                "motion": state.motion_running,
                "force": state.force_running,
                "recording": state.recording,
            }.get(key, False)
            status = RuntimeStatus.RUNNING if running else RuntimeStatus.READY

        if status == RuntimeStatus.ERROR:
            return STATUS_PILL_ERROR_STYLE
        if status == RuntimeStatus.WARNING:
            return STATUS_PILL_WARNING_STYLE
        if status in (RuntimeStatus.CONNECTING, RuntimeStatus.RUNNING, RuntimeStatus.STOPPING):
            return STATUS_PILL_RUNNING_STYLE
        return STATUS_PILL_STYLE

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

    def _stabilize_iv_panel(self) -> None:
        layout = getattr(self.ui, "gridLayout_2", None)
        parent = getattr(self.ui, "tab_8", None)
        if getattr(self.ui, "ivModeLabel", None) is None:
            try:
                self.ui.ivModeLabel = QLabel(parent)
            except TypeError:
                self.ui.ivModeLabel = QLabel()
            if hasattr(self.ui.ivModeLabel, "setObjectName"):
                self.ui.ivModeLabel.setObjectName("ivModeLabel")
        self.ui.ivModeLabel.setText(self.translator("label.iv_mode"))

        if layout is not None:
            placement = {
                "ivModeComboBox": (0, 0),
                "ivRepeatSpinBox": (0, 1),
                "ivStartSpinBox": (1, 0),
                "ivStopSpinBox": (1, 1),
                "ivStepSpinBox": (1, 2),
            }
            for object_name in (
                "ivModeLabel",
                "label_3",
                "label_9",
                "label_4",
                "label_5",
            ):
                widget = getattr(self.ui, object_name, None)
                if widget is not None:
                    layout.removeWidget(widget)
                    if hasattr(widget, "setVisible"):
                        widget.setVisible(False)
            for object_name, position in placement.items():
                widget = getattr(self.ui, object_name, None)
                if widget is not None:
                    layout.removeWidget(widget)
                    layout.addWidget(widget, *position)
            button = getattr(self.ui, "ivControlButton", None)
            if button is not None:
                layout.removeWidget(button)
                layout.addWidget(button, 0, 2)
            if hasattr(layout, "setContentsMargins"):
                layout.setContentsMargins(8, 4, 8, 4)
            if hasattr(layout, "setHorizontalSpacing"):
                layout.setHorizontalSpacing(8)
            if hasattr(layout, "setVerticalSpacing"):
                layout.setVerticalSpacing(4)
            for column in range(3):
                if hasattr(layout, "setColumnStretch"):
                    layout.setColumnStretch(column, 1)

        for widget_name in (
            "ivModeComboBox",
            "ivRepeatSpinBox",
            "ivStartSpinBox",
            "ivStopSpinBox",
            "ivStepSpinBox",
            "ivControlButton",
        ):
            self._set_min_height(widget_name, 24)

        for widget_name in (
            "ivRepeatSpinBox",
            "ivStartSpinBox",
            "ivStopSpinBox",
            "ivStepSpinBox",
        ):
            widget = getattr(self.ui, widget_name, None)
            if widget is not None and hasattr(widget, "setStyleSheet"):
                widget.setStyleSheet("")

        self._set_min_width("ivModeComboBox", 135)
        self._set_min_width("ivRepeatSpinBox", 88)
        self._set_min_width("ivStartSpinBox", 98)
        self._set_min_width("ivStopSpinBox", 98)
        self._set_min_width("ivStepSpinBox", 98)
        self._set_min_width("ivControlButton", 90)
        self._apply_iv_compact_text()

    def _apply_iv_compact_text(self) -> None:
        mode = getattr(self.ui, "ivModeComboBox", None)
        if mode is not None:
            if hasattr(mode, "setToolTip"):
                mode.setToolTip(self.translator("iv.mode_tooltip"))
            if hasattr(mode, "setAccessibleName"):
                mode.setAccessibleName(self.translator("label.iv_mode"))

        affixes = {
            "ivRepeatSpinBox": ("iv.repeat_prefix", ""),
            "ivStartSpinBox": ("iv.start_prefix", " V"),
            "ivStopSpinBox": ("iv.stop_prefix", " V"),
            "ivStepSpinBox": ("iv.step_prefix", " V"),
        }
        for object_name, (prefix_key, suffix) in affixes.items():
            widget = getattr(self.ui, object_name, None)
            if widget is None:
                continue
            if hasattr(widget, "setPrefix"):
                widget.setPrefix(f"{self.translator(prefix_key)} ")
            if hasattr(widget, "setSuffix"):
                widget.setSuffix(suffix)

    def _compact_force_panel(self) -> None:
        layout = getattr(self.ui, "gridLayout_6", None)
        if layout is None:
            return

        placement = {
            "forceModeLabel": (0, 0),
            "forceModeComboBox": (0, 1),
            "forceDeviceLabel": (0, 2),
            "forceDeviceComboBox": (0, 3),
            "forceSampleRateLabel": (0, 4),
            "forceSampleRateSpinBox": (0, 5),
            "forceTerminalConfigLabel": (1, 0),
            "forceTerminalConfigComboBox": (1, 1),
            "forceVoltageRangeLabel": (1, 2),
            "forceVoltageRangeComboBox": (1, 3),
            "forceFullScaleLabel": (1, 4),
            "forceFullScaleSpinBox": (1, 5),
        }

        for object_name, position in placement.items():
            widget = getattr(self.ui, object_name, None)
            if widget is None:
                continue
            layout.removeWidget(widget)
            layout.addWidget(widget, *position)

        start_button = getattr(self.ui, "forceStartButton", None)
        if start_button is not None:
            layout.removeWidget(start_button)
            layout.addWidget(start_button, 2, 0, 1, 3)
        zero_button = getattr(self.ui, "forceZeroButton", None)
        if zero_button is not None:
            layout.removeWidget(zero_button)
            layout.addWidget(zero_button, 2, 3, 1, 3)

        values_row = getattr(self.ui, "forceValuesRow", None)
        if values_row is None:
            parent = getattr(self.ui, "groupBox_4", None)
            values_row = QWidget(parent)
            values_row.setObjectName("forceValuesRow")
            values_layout = QHBoxLayout(values_row)
            values_layout.setContentsMargins(0, 0, 0, 0)
            values_layout.setSpacing(6)
            values_row.forceValuesLayout = values_layout
            self.ui.forceValuesRow = values_row
        values_layout = values_row.forceValuesLayout
        for widget_name in (
            "totalForceLabel",
            "Force1_Label",
            "Force2_Label",
            "Force3_Label",
            "Force4_Label",
        ):
            widget = getattr(self.ui, widget_name, None)
            if widget is not None:
                layout.removeWidget(widget)
                values_layout.removeWidget(widget)
                values_layout.addWidget(widget, 1)
        layout.removeWidget(values_row)
        layout.addWidget(values_row, 3, 0, 1, 6)

        redundant_label = getattr(self.ui, "label_11", None)
        if redundant_label is not None and hasattr(redundant_label, "setVisible"):
            redundant_label.setVisible(False)

        if hasattr(layout, "setContentsMargins"):
            layout.setContentsMargins(8, 4, 8, 4)
        if hasattr(layout, "setSpacing"):
            layout.setSpacing(4)
        for column in range(6):
            if hasattr(layout, "setColumnStretch"):
                layout.setColumnStretch(column, 1)

    def _stabilize_ai_channel_grid(self) -> None:
        layout = getattr(self.ui, "gridLayout_8", None)
        if layout is not None:
            if hasattr(layout, "setSpacing"):
                layout.setSpacing(2)
            if hasattr(layout, "setContentsMargins"):
                layout.setContentsMargins(10, 8, 10, 8)
            for column in range(6):
                if hasattr(layout, "setColumnStretch"):
                    layout.setColumnStretch(column, 1)
            for row in range(3):
                if hasattr(layout, "setRowMinimumHeight"):
                    layout.setRowMinimumHeight(row, 22)

        for index in range(16):
            checkbox = getattr(self.ui, f"ai{index}CheckBox", None)
            if checkbox is None:
                continue
            if layout is not None:
                layout.removeWidget(checkbox)
                layout.addWidget(checkbox, index // 6, index % 6)
            if hasattr(checkbox, "setMinimumWidth"):
                checkbox.setMinimumWidth(50)
            if hasattr(checkbox, "setMaximumWidth"):
                checkbox.setMaximumWidth(16777215)
            if hasattr(checkbox, "setMinimumHeight"):
                checkbox.setMinimumHeight(22)

    def _compact_acquisition_controls(self) -> None:
        layout_margins = {
            "gridLayout_9": (6, 4, 6, 4),
            "gridLayout_10": (8, 4, 8, 4),
        }
        for layout_name, margins in layout_margins.items():
            layout = getattr(self.ui, layout_name, None)
            if layout is not None:
                if hasattr(layout, "setContentsMargins"):
                    layout.setContentsMargins(*margins)
                if hasattr(layout, "setSpacing"):
                    layout.setSpacing(4)

        for widget_name in (
            "daqDeviceComboBox",
            "sampleRateSpinBox",
            "forceHoldToleranceSpinBox",
            "forceHoldStepSpinBox",
            "startStopButton",
            "aoChannelComboBox",
            "aoVoltageSpinBox",
            "aoControlButton",
            "timeWindowSpinBox",
            "yMaxSpinBox",
            "yMinSpinBox",
            "recorderStartButton",
            "recorderStopButton",
        ):
            self._set_max_height(widget_name, 30)

    def _compact_scan_controls(self) -> None:
        layout = getattr(self.ui, "gridLayout_11", None)
        if layout is not None:
            if hasattr(layout, "setContentsMargins"):
                layout.setContentsMargins(8, 2, 8, 2)
            if hasattr(layout, "setSpacing"):
                layout.setSpacing(2)
            if hasattr(layout, "setHorizontalSpacing"):
                layout.setHorizontalSpacing(6)

        for widget_name in (
            "Axis_choice",
            "direction_choice",
            "Circle_times",
            "Gap_time",
            "distanceSpinBox_2",
            "Speed_Setting_val",
            "sampleRateSpinBox",
        ):
            widget = getattr(self.ui, widget_name, None)
            if widget is not None and hasattr(widget, "setStyleSheet"):
                widget.setStyleSheet("")
            self._set_max_height(widget_name, 24)

        self._set_min_height("scanQualityLabel", 16)
        self._set_max_height("scanQualityLabel", 18)
        self._set_min_height("forceHoldStatusLabel", 16)
        self._set_max_height("forceHoldStatusLabel", 34)
        self._set_min_height("Forward_circle", 24)
        self._set_max_height("Forward_circle", 28)
        self._set_min_height("Emergency_Stop", 26)
        self._set_max_height("Emergency_Stop", 30)

    def _stabilize_force_value_labels(self) -> None:
        for widget_name in (
            "totalForceLabel",
            "Force1_Label",
            "Force2_Label",
            "Force3_Label",
            "Force4_Label",
        ):
            widget = getattr(self.ui, widget_name, None)
            self._set_min_width(widget_name, 92)
            self._set_max_width(widget_name, 16777215)
            self._set_min_height(widget_name, 24)
            if widget is not None and hasattr(widget, "setAlignment"):
                widget.setAlignment(Qt.AlignCenter)

    def _configure_scan_panel(self) -> None:
        layout = getattr(self.ui, "gridLayout_11", None)
        if layout is None:
            return

        for object_name in (
            "scanAxisLabel",
            "scanDirectionLabel",
            "scanLedCountLabel",
            "scanLedSizeLabel",
            "scanDistanceLabel",
            "scanQualityLabel",
            "forceHoldStatusLabel",
            "forceHoldToleranceLabel",
            "forceHoldStepLabel",
        ):
            if getattr(self.ui, object_name, None) is None:
                parent = getattr(self.ui, "groupBox_6", None)
                try:
                    label = QLabel(parent)
                except TypeError:
                    label = QLabel()
                if hasattr(label, "setObjectName"):
                    label.setObjectName(object_name)
                setattr(self.ui, object_name, label)

        parent = getattr(self.ui, "groupBox_6", None)
        if getattr(self.ui, "forceHoldEnableCheckBox", None) is None:
            checkbox = QCheckBox(parent)
            checkbox.setObjectName("forceHoldEnableCheckBox")
            checkbox.setChecked(False)
            self.ui.forceHoldEnableCheckBox = checkbox
        for object_name in (
            "forceHoldToleranceSpinBox",
            "forceHoldStepSpinBox",
        ):
            if getattr(self.ui, object_name, None) is None:
                spinbox = QDoubleSpinBox(parent)
                spinbox.setObjectName(object_name)
                spinbox.setKeyboardTracking(False)
                setattr(self.ui, object_name, spinbox)

        tolerance = self.ui.forceHoldToleranceSpinBox
        tolerance.setRange(0.01, 10.0)
        tolerance.setDecimals(2)
        tolerance.setSingleStep(0.05)
        tolerance.setValue(0.20)
        tolerance.setSuffix(" N")
        step = self.ui.forceHoldStepSpinBox
        step.setRange(0.0001, 0.0100)
        step.setDecimals(4)
        step.setSingleStep(0.0005)
        step.setValue(0.0020)
        step.setSuffix(" mm")

        t = self.translator
        self.ui.scanAxisLabel.setText(t("label.scan_axis"))
        self.ui.scanDirectionLabel.setText(t("label.scan_direction"))
        self.ui.scanLedCountLabel.setText(t("label.led_count"))
        self.ui.scanLedSizeLabel.setText(t("label.led_size"))
        self.ui.scanDistanceLabel.setText(t("label.scan_distance"))
        self.ui.forceHoldEnableCheckBox.setText(t("force_hold.enable"))
        self.ui.forceHoldToleranceLabel.setText(t("force_hold.tolerance"))
        self.ui.forceHoldStepLabel.setText(t("force_hold.z_step"))
        self.ui.forceHoldEnableCheckBox.setToolTip(t("force_hold.tooltip"))
        self.ui.forceHoldStatusLabel.setText(t("force_hold.status_off"))
        self.ui.forceHoldStatusLabel.setToolTip(t("force_hold.workflow"))
        self.ui.forceHoldStatusLabel.setWordWrap(True)
        self.ui.scanQualityLabel.setText("")

        placement = {
            "scanAxisLabel": (0, 0),
            "Axis_choice": (0, 1),
            "scanDirectionLabel": (1, 0),
            "direction_choice": (1, 1),
            "scanLedCountLabel": (2, 0),
            "Circle_times": (2, 1),
            "scanLedSizeLabel": (3, 0),
            "Gap_time": (3, 1),
            "scanDistanceLabel": (4, 0),
            "distanceSpinBox_2": (4, 1),
            "label_13": (5, 0),
            "Speed_Setting_val": (5, 1),
            "label": (6, 0),
            "sampleRateSpinBox": (6, 1),
            "forceHoldToleranceLabel": (8, 0),
            "forceHoldToleranceSpinBox": (8, 1),
            "forceHoldStepLabel": (9, 0),
            "forceHoldStepSpinBox": (9, 1),
        }

        for object_name, position in placement.items():
            widget = getattr(self.ui, object_name, None)
            if widget is None:
                continue
            layout.removeWidget(widget)
            layout.addWidget(widget, *position)

        force_hold_enable = getattr(self.ui, "forceHoldEnableCheckBox", None)
        if force_hold_enable is not None:
            layout.removeWidget(force_hold_enable)
            layout.addWidget(force_hold_enable, 7, 0, 1, 2)

        quality_label = getattr(self.ui, "scanQualityLabel", None)
        force_hold_status = getattr(self.ui, "forceHoldStatusLabel", None)
        if force_hold_status is not None:
            layout.removeWidget(force_hold_status)
            layout.addWidget(force_hold_status, 10, 0, 1, 2)

        if quality_label is not None:
            layout.removeWidget(quality_label)
            layout.addWidget(quality_label, 11, 0, 1, 2)

        start_button = getattr(self.ui, "Forward_circle", None)
        if start_button is not None:
            layout.removeWidget(start_button)
            layout.addWidget(start_button, 12, 0, 1, 2)

        cancel_button = getattr(self.ui, "Backward_circle", None)
        if cancel_button is not None and hasattr(cancel_button, "setVisible"):
            cancel_button.setVisible(False)

        stop_button = getattr(self.ui, "Emergency_Stop", None)
        if stop_button is not None:
            layout.removeWidget(stop_button)
            layout.addWidget(stop_button, 13, 0, 1, 2)

        daq_layout = getattr(self.ui, "gridLayout_9", None)
        if daq_layout is not None:
            daq_button = getattr(self.ui, "startStopButton", None)
            if daq_button is not None:
                daq_layout.removeWidget(daq_button)
                daq_layout.addWidget(daq_button, 0, 2, 1, 3)

        speed_label = getattr(self.ui, "label_13", None)
        if speed_label is not None and hasattr(speed_label, "setVisible"):
            speed_label.setVisible(True)

        for row in range(14):
            if hasattr(layout, "setRowMinimumHeight"):
                layout.setRowMinimumHeight(row, 0)
            if hasattr(layout, "setRowStretch"):
                layout.setRowStretch(row, 1 if row == 11 else 0)

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

    def _translate_combo_items(self, widget_name: str, items) -> None:
        widget = getattr(self.ui, widget_name, None)
        required = ("count", "setItemData", "setItemText")
        if widget is None or not all(hasattr(widget, name) for name in required):
            return
        for index, (value, key) in enumerate(items):
            if index >= widget.count():
                break
            widget.setItemData(index, value)
            widget.setItemText(index, self.translator(key))
