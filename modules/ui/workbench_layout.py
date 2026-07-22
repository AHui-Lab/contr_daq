"""Stage-two workbench shell for the operator-facing LED scan UI."""

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from modules.app_runtime import RuntimeStatus


STEP_PENDING_STYLE = """
    background-color: #111a22;
    border: 1px solid #344958;
    border-radius: 4px;
    color: #9fb0bd;
    padding: 2px 5px;
    font-weight: 600;
"""

STEP_ACTIVE_STYLE = """
    background-color: #203141;
    border: 1px solid #4ca9d4;
    border-radius: 4px;
    color: #a9e5ff;
    padding: 2px 5px;
    font-weight: 700;
"""

STEP_COMPLETE_STYLE = """
    background-color: #183326;
    border: 1px solid #2f8652;
    border-radius: 4px;
    color: #8ff0b5;
    padding: 2px 5px;
    font-weight: 700;
"""

STEP_WARNING_STYLE = """
    background-color: #3b2b16;
    border: 1px solid #b97822;
    border-radius: 4px;
    color: #ffd28a;
    padding: 2px 5px;
    font-weight: 700;
"""

STEP_ERROR_STYLE = """
    background-color: #421d20;
    border: 1px solid #c94b55;
    border-radius: 4px;
    color: #ffabb2;
    padding: 2px 5px;
    font-weight: 700;
"""

HEADER_IDLE_STYLE = """
    background-color: #17242d;
    border: 1px solid #385366;
    border-radius: 4px;
    color: #b9c9d4;
    padding: 5px 10px;
    font-weight: 700;
"""

HEADER_RUNNING_STYLE = """
    background-color: #183326;
    border: 1px solid #2f8652;
    border-radius: 4px;
    color: #8ff0b5;
    padding: 5px 10px;
    font-weight: 700;
"""

HEADER_WARNING_STYLE = """
    background-color: #3b2b16;
    border: 1px solid #b97822;
    border-radius: 4px;
    color: #ffd28a;
    padding: 5px 10px;
    font-weight: 700;
"""

HEADER_ERROR_STYLE = """
    background-color: #421d20;
    border: 1px solid #c94b55;
    border-radius: 4px;
    color: #ffabb2;
    padding: 5px 10px;
    font-weight: 700;
"""


class WorkbenchLayout:
    """Recompose the legacy Designer form into a resizable operator workspace."""

    def __init__(self, ui, translator):
        self.ui = ui
        self.translator = translator
        self._last_state = None
        self._last_runtime = None
        self._rendered_result = None
        self.step_labels: list[QWidget] = []

        self._build_header()
        self._build_workspace()
        self._build_readiness_card()
        self._build_results_page()
        self._build_event_log_dock()
        self.retranslate()

    def _build_header(self) -> None:
        central = self.ui.centralWidget()
        self.header = QFrame(central)
        self.header.setObjectName("workbenchHeader")
        self.header.setMinimumHeight(54)
        self.header.setMaximumHeight(62)

        layout = QHBoxLayout(self.header)
        layout.setContentsMargins(14, 7, 12, 7)
        layout.setSpacing(12)

        title_block = QVBoxLayout()
        title_block.setContentsMargins(0, 0, 0, 0)
        title_block.setSpacing(1)
        self.title_label = QLabel(self.header)
        self.title_label.setObjectName("workspaceTitle")
        self.subtitle_label = QLabel(self.header)
        self.subtitle_label.setObjectName("workspaceSubtitle")
        title_block.addWidget(self.title_label)
        title_block.addWidget(self.subtitle_label)
        layout.addLayout(title_block)
        layout.addStretch(1)

        self.mode_label = QLabel(self.header)
        self.mode_label.setObjectName("workspaceModePill")
        self.mode_label.setAlignment(Qt.AlignCenter)
        self.health_label = QLabel(self.header)
        self.health_label.setObjectName("workspaceHealthPill")
        self.health_label.setAlignment(Qt.AlignCenter)
        self.health_label.setMinimumWidth(110)
        self.health_label.setStyleSheet(HEADER_IDLE_STYLE)
        layout.addWidget(self.mode_label)
        layout.addWidget(self.health_label)

    def _build_workspace(self) -> None:
        central = self.ui.centralWidget()
        root = self.ui.gridLayout_3

        for widget in (
            self.ui.tabWidget_2,
            self.ui.tabWidget,
            self.ui.tabWidget_3,
            self.ui.groupBox_7,
            self.ui.logTextEdit,
        ):
            root.removeWidget(widget)

        acquisition_layout = self.ui.verticalLayout_2
        acquisition_layout.removeWidget(self.ui.forcePlotWidget)
        acquisition_layout.removeWidget(self.ui.groupBox_4)

        self.left_pane, left_layout = self._pane(central, "acquisitionPane")
        self.center_pane, center_layout = self._pane(central, "observationPane")
        self.right_pane, right_layout = self._pane(central, "motionPane")
        left_layout.addWidget(self.ui.tabWidget_2)
        center_layout.addWidget(self.ui.tabWidget, 1)
        center_layout.addWidget(self.ui.groupBox_7, 0)
        right_layout.addWidget(self.ui.tabWidget_3)

        self.splitter = QSplitter(Qt.Horizontal, central)
        self.splitter.setObjectName("workspaceSplitter")
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(5)
        self.left_pane.setMinimumWidth(420)
        self.center_pane.setMinimumWidth(360)
        self.right_pane.setMinimumWidth(300)
        self.splitter.addWidget(self.left_pane)
        self.splitter.addWidget(self.center_pane)
        self.splitter.addWidget(self.right_pane)
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 4)
        self.splitter.setStretchFactor(2, 3)
        self.splitter.setSizes([520, 560, 360])

        self.force_band = QFrame(central)
        self.force_band.setObjectName("forceMonitoringBand")
        self.force_band.setMinimumHeight(176)
        self.force_band.setMaximumHeight(216)
        force_layout = QHBoxLayout(self.force_band)
        force_layout.setContentsMargins(0, 0, 0, 0)
        force_layout.setSpacing(10)
        force_layout.addWidget(self.ui.forcePlotWidget, 1)
        force_layout.addWidget(self.ui.groupBox_4, 1)

        root.addWidget(self.header, 0, 0, 1, 3)
        root.addWidget(self.splitter, 1, 0, 1, 3)
        root.addWidget(self.force_band, 2, 0, 1, 3)
        root.setRowStretch(0, 0)
        root.setRowStretch(1, 1)
        root.setRowStretch(2, 0)
        root.setColumnStretch(0, 1)
        root.setColumnStretch(1, 0)
        root.setColumnStretch(2, 0)

        self.ui.workspaceHeader = self.header
        self.ui.workspaceSplitter = self.splitter
        self.ui.forceMonitoringBand = self.force_band

    @staticmethod
    def _pane(parent, object_name):
        frame = QFrame(parent)
        frame.setObjectName(object_name)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        return frame, layout

    def _build_readiness_card(self) -> None:
        parent = self.ui.groupBox_6.parentWidget()
        self.readiness_card = QFrame(parent)
        self.readiness_card.setObjectName("scanReadinessCard")
        self.readiness_card.setMinimumHeight(108)
        self.readiness_card.setMaximumHeight(118)

        layout = QVBoxLayout(self.readiness_card)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(3)
        self.readiness_title = QLabel(self.readiness_card)
        self.readiness_title.setObjectName("readinessTitle")
        self.readiness_title.setMinimumHeight(14)
        layout.addWidget(self.readiness_title)

        step_layout = QGridLayout()
        step_layout.setContentsMargins(0, 0, 0, 0)
        step_layout.setHorizontalSpacing(6)
        step_layout.setVerticalSpacing(4)
        for index in range(4):
            if index == 1:
                label = QPushButton(self.readiness_card)
                label.setObjectName("scanLoadConfirmButton")
                label.setCheckable(True)
                label.setEnabled(False)
                self.ui.scanLoadConfirmButton = label
            else:
                label = QLabel(self.readiness_card)
            if hasattr(label, "setAlignment"):
                label.setAlignment(Qt.AlignCenter)
            label.setMinimumHeight(22)
            label.setMaximumHeight(24)
            label.setStyleSheet(STEP_PENDING_STYLE)
            step_layout.addWidget(label, index // 2, index % 2)
            self.step_labels.append(label)
        layout.addLayout(step_layout)

        self.readiness_summary = QLabel(self.readiness_card)
        self.readiness_summary.setObjectName("readinessSummary")
        self.readiness_summary.setMinimumHeight(22)
        self.readiness_summary.setMaximumHeight(28)
        self.readiness_summary.setWordWrap(True)
        layout.addWidget(self.readiness_summary)

        motion_layout = self.ui.gridLayout_4
        motion_layout.removeWidget(self.ui.groupBox_5)
        motion_layout.removeWidget(self.ui.groupBox_6)

        scan_form_layout = self.ui.gridLayout_11
        scan_form_layout.removeWidget(self.ui.Forward_circle)
        scan_form_layout.removeWidget(self.ui.Emergency_Stop)
        self.ui.groupBox_6.setMinimumHeight(300)
        self.ui.groupBox_6.setMaximumHeight(302)

        self.scan_scroll = QScrollArea(parent)
        self.scan_scroll.setObjectName("scanConfigScroll")
        self.scan_scroll.setWidgetResizable(True)
        self.scan_scroll.setFrameShape(QFrame.NoFrame)
        self.scan_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scan_scroll_content = QWidget(self.scan_scroll)
        scroll_layout = QVBoxLayout(self.scan_scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(0)
        scroll_layout.addWidget(self.ui.groupBox_6)
        self.scan_scroll.setWidget(self.scan_scroll_content)

        self.scan_action_bar = QFrame(parent)
        self.scan_action_bar.setObjectName("scanActionBar")
        action_layout = QVBoxLayout(self.scan_action_bar)
        action_layout.setContentsMargins(0, 0, 0, 0)
        action_layout.setSpacing(4)
        action_layout.addWidget(self.ui.Forward_circle)
        action_layout.addWidget(self.ui.Emergency_Stop)

        motion_layout.addWidget(self.readiness_card, 0, 0)
        motion_layout.addWidget(self.scan_scroll, 1, 0)
        motion_layout.addWidget(self.scan_action_bar, 2, 0)
        motion_layout.setRowStretch(0, 0)
        motion_layout.setRowStretch(1, 1)
        motion_layout.setRowStretch(2, 0)

        self.manual_page = QWidget(self.ui.tabWidget_3)
        self.manual_page.setObjectName("manualMotionPage")
        manual_layout = QVBoxLayout(self.manual_page)
        manual_layout.setContentsMargins(8, 8, 8, 8)
        manual_layout.addWidget(self.ui.groupBox_5)
        manual_layout.addStretch(1)
        self.ui.tabWidget_3.addTab(self.manual_page, "")
        self.ui.tabWidget_3.setCurrentIndex(0)
        self.ui.scanReadinessCard = self.readiness_card
        self.ui.scanConfigScroll = self.scan_scroll
        self.ui.scanActionBar = self.scan_action_bar

    def _build_results_page(self) -> None:
        self.results_page = QWidget(self.ui.tabWidget_3)
        self.results_page.setObjectName("scanResultsPage")
        root_layout = QVBoxLayout(self.results_page)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)

        self.result_status = QLabel(self.results_page)
        self.result_status.setObjectName("scanResultStatus")
        self.result_status.setAlignment(Qt.AlignCenter)
        self.result_status.setMinimumHeight(30)
        root_layout.addWidget(self.result_status)

        self.result_scroll = QScrollArea(self.results_page)
        self.result_scroll.setObjectName("scanResultsScroll")
        self.result_scroll.setWidgetResizable(True)
        self.result_scroll.setFrameShape(QFrame.NoFrame)
        self.result_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.result_scroll_content = QWidget(self.result_scroll)
        self.result_scroll_content.setMinimumHeight(540)
        layout = QVBoxLayout(self.result_scroll_content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.result_metrics = QFrame(self.results_page)
        self.result_metrics.setObjectName("scanResultsMetrics")
        metrics_layout = QGridLayout(self.result_metrics)
        metrics_layout.setContentsMargins(8, 8, 8, 8)
        metrics_layout.setHorizontalSpacing(10)
        metrics_layout.setVerticalSpacing(6)
        self.result_metric_titles = {}
        self.result_metric_values = {}
        for row, key in enumerate(
            (
                "run_id",
                "operator",
                "coverage",
                "samples",
                "constant",
                "duration",
                "force_hold",
            )
        ):
            title = QLabel(self.result_metrics)
            title.setObjectName("scanResultMetricTitle")
            value = QLabel(self.result_metrics)
            value.setObjectName("scanResultMetricValue")
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextSelectableByMouse)
            metrics_layout.addWidget(title, row, 0)
            metrics_layout.addWidget(value, row, 1)
            self.result_metric_titles[key] = title
            self.result_metric_values[key] = value
        metrics_layout.setColumnStretch(1, 1)
        layout.addWidget(self.result_metrics)

        self.result_quality_title = QLabel(self.results_page)
        self.result_quality_title.setObjectName("scanResultSectionTitle")
        self.result_quality_value = QLabel(self.results_page)
        self.result_quality_value.setObjectName("scanResultQuality")
        self.result_quality_value.setWordWrap(True)
        self.result_quality_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.result_quality_title)
        layout.addWidget(self.result_quality_value)

        self.result_interpretation_title = QLabel(self.results_page)
        self.result_interpretation_title.setObjectName("scanResultSectionTitle")
        self.result_interpretation_value = QLabel(self.results_page)
        self.result_interpretation_value.setObjectName("scanResultInterpretation")
        self.result_interpretation_value.setWordWrap(True)
        self.result_interpretation_value.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        layout.addWidget(self.result_interpretation_title)
        layout.addWidget(self.result_interpretation_value)

        self.result_files_title = QLabel(self.results_page)
        self.result_files_title.setObjectName("scanResultSectionTitle")
        self.result_files_value = QLabel(self.results_page)
        self.result_files_value.setObjectName("scanResultFiles")
        self.result_files_value.setWordWrap(True)
        self.result_files_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.result_files_title)
        layout.addWidget(self.result_files_value)

        self.result_folder_title = QLabel(self.results_page)
        self.result_folder_title.setObjectName("scanResultSectionTitle")
        self.result_folder_value = QLabel(self.results_page)
        self.result_folder_value.setObjectName("scanResultFolder")
        self.result_folder_value.setWordWrap(True)
        self.result_folder_value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.result_folder_title)
        layout.addWidget(self.result_folder_value)
        layout.addStretch(1)

        self.result_scroll.setWidget(self.result_scroll_content)
        root_layout.addWidget(self.result_scroll, 1)

        button_layout = QHBoxLayout()
        self.open_result_folder_button = QPushButton(self.results_page)
        self.open_result_folder_button.setObjectName("openResultFolderButton")
        self.open_result_folder_button.clicked.connect(self._open_result_folder)
        self.copy_result_paths_button = QPushButton(self.results_page)
        self.copy_result_paths_button.setObjectName("copyResultPathsButton")
        self.copy_result_paths_button.clicked.connect(self._copy_result_paths)
        button_layout.addWidget(self.open_result_folder_button)
        button_layout.addWidget(self.copy_result_paths_button)
        root_layout.addLayout(button_layout)

        self.ui.tabWidget_3.insertTab(1, self.results_page, "")
        self.ui.scanResultsPage = self.results_page
        self.ui.scanResultsScroll = self.result_scroll
        self.ui.scanLastResult = None
        self._render_result(None)

    def _build_event_log_dock(self) -> None:
        self.event_log_dock = QDockWidget(self.ui)
        self.event_log_dock.setObjectName("eventLogDock")
        self.event_log_dock.setAllowedAreas(Qt.BottomDockWidgetArea | Qt.RightDockWidgetArea)
        self.event_log_dock.setFeatures(
            QDockWidget.DockWidgetClosable
            | QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
        )
        self.event_log_dock.setWidget(self.ui.logTextEdit)
        self.ui.addDockWidget(Qt.BottomDockWidgetArea, self.event_log_dock)
        self.event_log_dock.hide()

        self.view_menu = self.ui.menuBar().addMenu("")
        self.event_log_action = self.event_log_dock.toggleViewAction()
        self.view_menu.addAction(self.event_log_action)
        self.ui.eventLogDock = self.event_log_dock

    def retranslate(self) -> None:
        t = self.translator
        self.title_label.setText(t("workspace.title"))
        self.subtitle_label.setText(t("workspace.subtitle"))
        self.mode_label.setText(t("workspace.operator_mode"))
        self.ui.tabWidget_3.setTabText(0, t("tab.scan"))
        self.ui.tabWidget_3.setTabText(1, t("tab.results"))
        self.ui.tabWidget_3.setTabText(2, t("tab.manual"))
        self.readiness_title.setText(t("readiness.title"))
        for index, label in enumerate(self.step_labels, start=1):
            label.setText(t(f"readiness.step_{index}"))
        confirm_button = getattr(self.ui, "scanLoadConfirmButton", None)
        if confirm_button is not None:
            confirm_button.setToolTip(t("readiness.confirm_load_tooltip"))
        self.view_menu.setTitle(t("menu.view"))
        self.event_log_dock.setWindowTitle(t("log.title"))
        self.event_log_action.setText(t("log.show"))
        for key, title in self.result_metric_titles.items():
            title.setText(t(f"results.{key}"))
        self.result_quality_title.setText(t("results.quality"))
        self.result_interpretation_title.setText(t("results.interpretation"))
        self.result_files_title.setText(t("results.files"))
        self.result_folder_title.setText(t("results.folder"))
        self.open_result_folder_button.setText(t("results.open_folder"))
        self.copy_result_paths_button.setText(t("results.copy_paths"))
        self._render_result(getattr(self.ui, "scanLastResult", None), force=True)
        if self._last_state is not None:
            self.update(self._last_state, self._last_runtime)
        else:
            self.health_label.setText(t("workspace.idle"))
            self.readiness_summary.setText(t("readiness.align_first"))

    def update(self, state, runtime=None) -> None:
        self._last_state = state
        self._last_runtime = runtime
        statuses = runtime.snapshot().values() if runtime is not None else ()
        status_values = [entry.status for entry in statuses]
        phase = str(getattr(self.ui, "scanWorkflowPhase", "idle"))
        active_phase = phase in ("preparing", "running", "saving")
        scanning = bool(state.motion_running or state.recording or active_phase)
        force_live = bool(
            getattr(self.ui, "scanForceReady", state.force_running)
        )
        load_confirmed = bool(
            getattr(self.ui, "scanLoadConfirmed", False)
        )
        configured = bool(
            getattr(self.ui, "scanPlanConfigured", self._scan_is_configured())
        )
        readiness_summary = str(
            getattr(self.ui, "scanReadinessSummaryText", "") or ""
        )
        result = getattr(self.ui, "scanLastResult", None)
        if result is not self._rendered_result:
            self._render_result(result)

        if phase == "error":
            health_key = "workspace.action_required"
            health_style = HEADER_ERROR_STYLE
        elif phase == "warning":
            health_key = "workspace.warning"
            health_style = HEADER_WARNING_STYLE
        elif phase == "preparing":
            health_key = "workspace.preparing"
            health_style = HEADER_RUNNING_STYLE
        elif phase == "saving":
            health_key = "workspace.saving"
            health_style = HEADER_RUNNING_STYLE
        elif phase == "completed":
            health_key = "workspace.saved"
            health_style = HEADER_RUNNING_STYLE
        elif RuntimeStatus.ERROR in status_values:
            health_key = "workspace.action_required"
            health_style = HEADER_ERROR_STYLE
        elif RuntimeStatus.WARNING in status_values:
            health_key = "workspace.warning"
            health_style = HEADER_WARNING_STYLE
        elif scanning or phase == "running":
            health_key = "workspace.scanning"
            health_style = HEADER_RUNNING_STYLE
        elif force_live:
            health_key = "workspace.monitoring"
            health_style = HEADER_RUNNING_STYLE
        else:
            health_key = "workspace.idle"
            health_style = HEADER_IDLE_STYLE
        self.health_label.setText(self.translator(health_key))
        self.health_label.setStyleSheet(health_style)

        if readiness_summary:
            self.readiness_summary.setText(readiness_summary)
        elif scanning:
            summary_key = "readiness.scan_active"
            self.readiness_summary.setText(self.translator(summary_key))
        elif force_live:
            summary_key = "readiness.force_live"
            self.readiness_summary.setText(self.translator(summary_key))
        else:
            summary_key = "readiness.align_first"
            self.readiness_summary.setText(self.translator(summary_key))

        if active_phase or phase == "running":
            step_styles = (
                STEP_COMPLETE_STYLE,
                STEP_COMPLETE_STYLE,
                STEP_COMPLETE_STYLE,
                STEP_ACTIVE_STYLE,
            )
        elif phase == "completed":
            step_styles = (STEP_COMPLETE_STYLE,) * 4
        elif phase == "warning":
            step_styles = (
                STEP_COMPLETE_STYLE,
                STEP_COMPLETE_STYLE,
                STEP_COMPLETE_STYLE,
                STEP_WARNING_STYLE,
            )
        elif phase == "error":
            step_styles = (
                STEP_COMPLETE_STYLE if force_live else STEP_ACTIVE_STYLE,
                (
                    STEP_COMPLETE_STYLE
                    if load_confirmed
                    else STEP_ACTIVE_STYLE
                    if force_live
                    else STEP_PENDING_STYLE
                ),
                STEP_COMPLETE_STYLE if configured else STEP_PENDING_STYLE,
                STEP_ERROR_STYLE,
            )
        else:
            step_styles = (
                STEP_COMPLETE_STYLE if force_live else STEP_ACTIVE_STYLE,
                (
                    STEP_COMPLETE_STYLE
                    if load_confirmed
                    else STEP_ACTIVE_STYLE
                    if force_live
                    else STEP_PENDING_STYLE
                ),
                STEP_COMPLETE_STYLE if configured else STEP_PENDING_STYLE,
                STEP_PENDING_STYLE,
            )
        for label, style in zip(self.step_labels, step_styles):
            label.setStyleSheet(style)

    def _scan_is_configured(self) -> bool:
        try:
            return all(
                value > 0
                for value in (
                    self.ui.Circle_times.value(),
                    self.ui.Gap_time.value(),
                    self.ui.Speed_Setting_val.value(),
                    self.ui.sampleRateSpinBox.value(),
                )
            )
        except (AttributeError, TypeError):
            return False

    def _render_result(self, result, force=False) -> None:
        if not force and result is self._rendered_result:
            return
        self._rendered_result = result
        t = self.translator
        if result is None:
            self.result_status.setText(t("results.none"))
            self.result_status.setStyleSheet(HEADER_IDLE_STYLE)
            for value in self.result_metric_values.values():
                value.setText("—")
            self.result_quality_value.setText(t("results.waiting"))
            self.result_interpretation_value.setText(t("results.metric_help"))
            self.result_files_value.setText(t("results.files_none"))
            self.result_folder_value.setText("—")
            self.open_result_folder_button.setEnabled(False)
            self.copy_result_paths_button.setEnabled(False)
            return

        outcome = str(getattr(result, "outcome", "warning"))
        if outcome == "completed":
            status_key = "results.completed"
            status_style = HEADER_RUNNING_STYLE
        elif outcome == "error":
            status_key = "results.error"
            status_style = HEADER_ERROR_STYLE
        else:
            status_key = "results.warning"
            status_style = HEADER_WARNING_STYLE
        self.result_status.setText(t(status_key))
        self.result_status.setStyleSheet(status_style)

        covered = int(getattr(result, "led_bins_covered", 0))
        expected = int(getattr(result, "led_bins_expected", 0))
        minimum = int(getattr(result, "minimum_samples_per_led", 0))
        maximum = int(getattr(result, "maximum_samples_per_led", 0))
        run_id = str(getattr(result, "scan_id", "")) or f"Group {result.group_id}"
        self.result_metric_values["run_id"].setText(run_id)
        self.result_metric_values["run_id"].setToolTip(run_id)
        self.result_metric_values["operator"].setText(
            str(getattr(result, "operator_name", "")) or t("results.unspecified")
        )
        self.result_metric_values["coverage"].setText(
            f"{covered}/{expected}" if expected else "—"
        )
        self.result_metric_values["samples"].setText(
            f"{minimum}–{maximum}" if expected else "—"
        )
        self.result_metric_values["constant"].setText(
            f"{float(getattr(result, 'constant_speed_fraction', 0.0)) * 100:.1f}%"
        )
        self.result_metric_values["duration"].setText(
            f"{float(getattr(result, 'capture_duration_s', 0.0)):.3f} s"
        )
        if bool(getattr(result, "force_hold_enabled", False)):
            profile = t(
                "force_hold.profile_fast"
                if bool(getattr(result, "force_hold_fast_response", False))
                else "force_hold.profile_standard"
            )
            force_hold_text = t(
                "results.force_hold_on",
                profile=profile,
                corrections=int(
                    getattr(result, "force_hold_correction_count", 0)
                ),
                target=float(getattr(result, "force_hold_target_n", 0.0)),
                offset=float(getattr(result, "force_hold_offset_mm", 0.0)),
            )
        else:
            force_hold_text = t("results.force_hold_off")
        self.result_metric_values["force_hold"].setText(force_hold_text)
        detail = str(getattr(result, "detail", "") or "")
        self.result_quality_value.setText(
            t("results.quality_ok") if detail in ("", "ok", "completed") else detail
        )
        self.result_interpretation_value.setText(
            "\n\n".join(
                (
                    t(f"results.interpretation_{outcome}"),
                    t("results.metric_help"),
                )
            )
        )
        paths = getattr(result, "paths", {}) or {}
        if paths:
            file_lines = [
                f"{name}: {Path(str(path)).name}"
                for name, path in sorted(paths.items())
            ]
            self.result_files_value.setText("\n".join(file_lines))
            self.result_files_value.setToolTip(
                "\n".join(f"{name}: {path}" for name, path in sorted(paths.items()))
            )
        else:
            self.result_files_value.setText(t("results.files_none"))
            self.result_files_value.setToolTip("")
        self.result_folder_value.setText(str(getattr(result, "save_dir", "")))
        self.open_result_folder_button.setEnabled(bool(result.save_dir))
        self.copy_result_paths_button.setEnabled(bool(result.paths))

    def _open_result_folder(self) -> None:
        result = getattr(self.ui, "scanLastResult", None)
        folder = str(getattr(result, "save_dir", "") or "")
        if folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _copy_result_paths(self) -> None:
        result = getattr(self.ui, "scanLastResult", None)
        paths = getattr(result, "paths", {}) or {}
        if paths:
            QApplication.clipboard().setText(
                "\n".join(f"{name}: {path}" for name, path in sorted(paths.items()))
            )
