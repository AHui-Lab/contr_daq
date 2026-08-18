from datetime import datetime
from pathlib import Path
import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from modules.workflow.force_commissioning import (
    ForceCommissioningLog,
    ForceSafetyConfig,
    ForceSafetySupervisor,
)
from modules.workflow.force_hold import ForceHoldConfig, ForceHoldController
from utils.log import log


class ForceCommissioningDialog(QDialog):
    """Deliberately separate, safety-first force-loop commissioning workspace."""

    UPDATE_INTERVAL_MS = 20
    DIRECTION_TEST_INCREMENT_MM = 0.002

    def __init__(
        self,
        ui,
        force_controller,
        motion_controller,
        config,
        translator,
        on_config_saved=None,
        parent=None,
    ):
        super().__init__(parent)
        self.ui = ui
        self.force = force_controller
        self.motion = motion_controller
        self.config = config
        self.translator = translator
        self.on_config_saved = on_config_saved

        self._active = False
        self._mode = "idle"
        self._direction_verified = False
        self._verification_pending = False
        self._verification_before_n = None
        self._verification_step_mm = 0.0
        self._verification_travel_mm = 0.0
        self._verification_phase = "idle"
        self._verification_result = None
        self._move_pending_until = 0.0
        self._hold_motion_pending = False
        self._last_logged_sample_time = None
        self._session_log = None
        self._safety = ForceSafetySupervisor()
        self._hold = ForceHoldController()

        self.setMinimumSize(1080, 700)
        self.resize(1180, 760)
        self._build_ui()
        self.load_from_config()
        self.retranslate_ui()
        self._set_direction_verified(False)
        self._set_commission_active(False)

        worker = getattr(self.motion, "motion_worker", None)
        if worker is not None and hasattr(worker, "move_finished"):
            worker.move_finished.connect(self._on_move_command_result)

        self._timer = QTimer(self)
        self._timer.setInterval(self.UPDATE_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _build_ui(self):
        root = QVBoxLayout(self)

        self.warning_label = QLabel()
        self.warning_label.setWordWrap(True)
        self.warning_label.setObjectName("forceCommissionWarning")
        root.addWidget(self.warning_label)

        self.live_group = QGroupBox()
        live_grid = QGridLayout(self.live_group)
        self.live_labels = []
        for index in range(5):
            title = QLabel()
            value = QLabel("--")
            value.setMinimumWidth(112)
            value.setStyleSheet("font-size: 16px; font-weight: 600;")
            live_grid.addWidget(title, 0, index)
            live_grid.addWidget(value, 1, index)
            self.live_labels.append((title, value))
        root.addWidget(self.live_group)

        middle = QHBoxLayout()
        self.safety_group = QGroupBox()
        safety_form = QFormLayout(self.safety_group)
        self.total_limit_spin = self._force_spin(0.0, 10000.0, 0.1, " N")
        self.channel_limit_spin = self._force_spin(0.0, 10000.0, 0.1, " N")
        self.imbalance_spin = self._force_spin(0.0, 10000.0, 0.1, " N")
        self.rise_rate_spin = self._force_spin(0.0, 100000.0, 1.0, " N/s")
        self.total_limit_label = QLabel()
        self.channel_limit_label = QLabel()
        self.imbalance_label = QLabel()
        self.rise_rate_label = QLabel()
        safety_form.addRow(self.total_limit_label, self.total_limit_spin)
        safety_form.addRow(self.channel_limit_label, self.channel_limit_spin)
        safety_form.addRow(self.imbalance_label, self.imbalance_spin)
        safety_form.addRow(self.rise_rate_label, self.rise_rate_spin)
        middle.addWidget(self.safety_group, 1)

        self.control_group = QGroupBox()
        control_form = QFormLayout(self.control_group)
        self.target_spin = self._force_spin(0.0, 10000.0, 0.1, " N")
        self.tolerance_spin = self._force_spin(0.0, 10000.0, 0.1, " N/s", 2)
        self.z_step_spin = self._force_spin(0.0001, 0.01, 0.0001, " mm", 4)
        self.interval_spin = self._force_spin(0.02, 5.0, 0.01, " s", 3)
        self.confirm_spin = self._force_spin(0.005, 5.0, 0.005, " s", 3)
        self.max_offset_spin = self._force_spin(0.0001, 1.0, 0.001, " mm", 4)
        self.max_error_spin = self._force_spin(0.1, 10000.0, 0.1, " N", 2)
        self.target_label = QLabel()
        self.tolerance_label = QLabel()
        self.z_step_label = QLabel()
        self.interval_label = QLabel()
        self.confirm_label = QLabel()
        self.max_offset_label = QLabel()
        self.max_error_label = QLabel()
        control_form.addRow(self.target_label, self.target_spin)
        control_form.addRow(self.tolerance_label, self.tolerance_spin)
        control_form.addRow(self.z_step_label, self.z_step_spin)
        control_form.addRow(self.interval_label, self.interval_spin)
        control_form.addRow(self.confirm_label, self.confirm_spin)
        control_form.addRow(self.max_offset_label, self.max_offset_spin)
        control_form.addRow(self.max_error_label, self.max_error_spin)
        middle.addWidget(self.control_group, 1)
        root.addLayout(middle)

        self.verify_group = QGroupBox()
        verify_form = QFormLayout(self.verify_group)
        self.verify_distance_spin = self._force_spin(
            0.0001, 0.05, 0.001, " mm", 4
        )
        self.verify_delta_spin = self._force_spin(
            0.1, 1000.0, 0.1, " N", 1
        )
        self.verify_settle_spin = self._force_spin(
            0.2, 5.0, 0.1, " s", 1
        )
        self.verify_distance_label = QLabel()
        self.verify_delta_label = QLabel()
        self.verify_settle_label = QLabel()
        verify_form.addRow(self.verify_distance_label, self.verify_distance_spin)
        verify_form.addRow(self.verify_delta_label, self.verify_delta_spin)
        verify_form.addRow(self.verify_settle_label, self.verify_settle_spin)

        self.retract_group = QGroupBox()
        retract_form = QFormLayout(self.retract_group)
        self.retract_enabled = QCheckBox()
        self.retract_distance_spin = self._force_spin(
            0.0001, 0.01, 0.0005, " mm", 4
        )
        self.retract_distance_label = QLabel()
        retract_form.addRow(self.retract_enabled)
        retract_form.addRow(self.retract_distance_label, self.retract_distance_spin)
        verification_row = QHBoxLayout()
        verification_row.addWidget(self.verify_group, 1)
        verification_row.addWidget(self.retract_group, 1)
        root.addLayout(verification_row)

        action_grid = QGridLayout()
        self.capture_target_button = QPushButton()
        self.monitor_button = QPushButton()
        self.verify_button = QPushButton()
        self.hold_button = QPushButton()
        self.stop_button = QPushButton()
        self.emergency_button = QPushButton()
        self.emergency_button.setObjectName("dangerButton")
        action_buttons = (
            self.capture_target_button,
            self.monitor_button,
            self.verify_button,
            self.hold_button,
            self.stop_button,
            self.emergency_button,
        )
        for index, button in enumerate(action_buttons):
            button.setMinimumHeight(36)
            action_grid.addWidget(button, index // 3, index % 3)
        root.addLayout(action_grid)

        self.direction_status_label = QLabel()
        self.direction_status_label.setWordWrap(True)
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        root.addWidget(self.direction_status_label)
        root.addWidget(self.status_label)
        root.addStretch(1)

        self.capture_target_button.clicked.connect(self.capture_target)
        self.monitor_button.clicked.connect(self.start_monitor)
        self.verify_button.clicked.connect(self.verify_z_direction)
        self.hold_button.clicked.connect(self.start_static_hold)
        self.stop_button.clicked.connect(self.stop_session)
        self.emergency_button.clicked.connect(self.emergency_stop)
        self.retract_enabled.toggled.connect(self._update_motion_lock)
        main_emergency = getattr(self.ui, "Emergency_Stop", None)
        if main_emergency is not None and hasattr(main_emergency, "clicked"):
            main_emergency.clicked.connect(self._on_external_emergency)

    @staticmethod
    def _force_spin(minimum, maximum, step, suffix, decimals=3):
        spin = QDoubleSpinBox()
        spin.setRange(float(minimum), float(maximum))
        spin.setDecimals(int(decimals))
        spin.setSingleStep(float(step))
        spin.setSuffix(suffix)
        spin.setKeyboardTracking(False)
        return spin

    def load_from_config(self):
        self.total_limit_spin.setValue(self.config.force_safety_total_high_n)
        self.channel_limit_spin.setValue(self.config.force_safety_channel_high_n)
        self.imbalance_spin.setValue(self.config.force_safety_imbalance_n)
        self.rise_rate_spin.setValue(self.config.force_safety_rise_rate_n_s)
        self.retract_enabled.setChecked(self.config.force_safety_retract_enabled)
        self.retract_distance_spin.setValue(self.config.force_safety_retract_mm)
        self.tolerance_spin.setValue(self.config.force_derivative_deadband_n_s)
        self.z_step_spin.setValue(self.config.force_derivative_z_step_mm)
        self.verify_distance_spin.setValue(
            self.config.force_commission_verify_distance_mm
        )
        self.verify_delta_spin.setValue(self.config.force_commission_verify_delta_n)
        self.verify_settle_spin.setValue(self.config.force_commission_verify_settle_s)
        self.interval_spin.setValue(self.config.force_derivative_interval_s)
        self.confirm_spin.setValue(
            self.config.force_derivative_measurement_window_s
        )
        self.max_offset_spin.setValue(self.config.force_derivative_max_offset_mm)
        self.max_error_spin.setValue(self.config.force_derivative_max_error_n)
        self._update_motion_lock()

    def retranslate_ui(self):
        t = self.translator
        self.setWindowTitle(t("force_commission.title"))
        self.warning_label.setText(t("force_commission.warning"))
        self.live_group.setTitle(t("force_commission.live"))
        for (title, _value), key in zip(
            self.live_labels,
            ("total", "p1", "p2", "p3", "p4"),
        ):
            title.setText(t(f"force_commission.{key}"))
        self.safety_group.setTitle(t("force_commission.safety"))
        self.total_limit_label.setText(t("force_commission.total_limit"))
        self.channel_limit_label.setText(t("force_commission.channel_limit"))
        self.imbalance_label.setText(t("force_commission.imbalance_limit"))
        self.rise_rate_label.setText(t("force_commission.rise_rate_limit"))
        self.control_group.setTitle(t("force_commission.control"))
        self.target_label.setText(t("force_commission.target"))
        self.tolerance_label.setText(t("force_commission.tolerance"))
        self.z_step_label.setText(t("force_commission.z_step"))
        self.interval_label.setText(t("force_commission.interval"))
        self.confirm_label.setText(t("force_commission.confirm"))
        self.max_offset_label.setText(t("force_commission.max_offset"))
        self.max_error_label.setText(t("force_commission.max_error"))
        self.verify_group.setTitle(t("force_commission.verify_group"))
        self.verify_distance_label.setText(t("force_commission.verify_distance"))
        self.verify_delta_label.setText(t("force_commission.verify_delta"))
        self.verify_settle_label.setText(t("force_commission.verify_settle"))
        self.verify_distance_spin.setToolTip(
            t("force_commission.verify_distance_help")
        )
        self.verify_delta_spin.setToolTip(t("force_commission.verify_delta_help"))
        self.verify_settle_spin.setToolTip(t("force_commission.verify_settle_help"))
        self.retract_group.setTitle(t("force_commission.retract"))
        self.retract_enabled.setText(t("force_commission.retract_enable"))
        self.retract_distance_label.setText(t("force_commission.retract_distance"))
        retract_help = t("force_commission.retract_distance_help")
        self.retract_distance_label.setToolTip(retract_help)
        self.retract_distance_spin.setToolTip(retract_help)
        self.z_step_spin.setToolTip(t("force_commission.z_step_help"))
        self.capture_target_button.setText(t("force_commission.capture_target"))
        self.monitor_button.setText(t("force_commission.monitor"))
        self.verify_button.setText(t("force_commission.verify"))
        self.hold_button.setText(t("force_commission.hold"))
        self.stop_button.setText(t("force_commission.stop"))
        self.emergency_button.setText(t("force_commission.emergency"))
        self._set_direction_verified(self._direction_verified)
        if not self._active:
            self._set_status("force_commission.status_idle")

    def capture_target(self):
        snapshot = self._snapshot()
        if snapshot[0] is None:
            self._set_status("force_commission.no_signal", warning=True)
            return
        self.target_spin.setValue(max(float(snapshot[0]), 0.0))
        self._set_status("force_commission.target_captured")

    def start_monitor(self):
        if not self._prepare_session("monitor"):
            return
        self._set_status("force_commission.status_monitoring")

    def verify_z_direction(self):
        if self._active or self.motion.scan_running:
            self._set_status("force_commission.motion_busy", warning=True)
            return
        if not self._force_ready(require_analog=True):
            return
        try:
            self._safety.arm(self._safety_config())
        except ValueError as exc:
            self._show_validation(str(exc))
            return
        self._save_settings()
        answer = QMessageBox.question(
            self,
            self.translator("force_commission.verify_title"),
            self.translator(
                "force_commission.verify_prompt",
                distance=self.verify_distance_spin.value(),
                increment=min(
                    self.DIRECTION_TEST_INCREMENT_MM,
                    self.verify_distance_spin.value(),
                ),
                threshold=self.verify_delta_spin.value(),
                settle=self.verify_settle_spin.value(),
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        total, _channels, _sample_time = self._snapshot()
        if total is None:
            self._set_status("force_commission.no_signal", warning=True)
            return
        self._verification_before_n = float(total)
        self._verification_pending = True
        self._verification_travel_mm = 0.0
        self._verification_step_mm = 0.0
        self._verification_phase = "forward"
        self._verification_result = None
        self._mode = "direction_test"
        self._set_commission_active(True)
        self._queue_next_direction_step()

    def start_static_hold(self):
        if not self._direction_verified:
            self._set_status("force_commission.direction_required", warning=True)
            return
        if not self._force_ready(require_analog=True):
            return
        target = self.target_spin.value()
        if target <= 0:
            self._set_status("force_commission.target_required", warning=True)
            return
        if not self._prepare_session("hold"):
            return
        try:
            hold_config = ForceHoldConfig(
                enabled=True,
                derivative_interval_s=self.interval_spin.value(),
                derivative_deadband_n_s=self.tolerance_spin.value(),
                z_step_mm=self.z_step_spin.value(),
                measurement_window_s=self.confirm_spin.value(),
                signal_timeout_s=0.15,
                max_offset_mm=self.max_offset_spin.value(),
                hard_error_n=self.max_error_spin.value(),
                z_positive_increases_force=True,
            )
            self._hold.arm(hold_config, target, time.perf_counter())
        except ValueError as exc:
            self._finish_session("invalid_control", str(exc))
            self._show_validation(str(exc))
            return
        self._set_status("force_commission.status_holding")

    def stop_session(self):
        if self._active:
            stop = getattr(self.motion, "request_force_hold_stop", None)
            if callable(stop):
                stop()
            self._finish_session("stopped", self.translator("force_commission.stopped"))
        else:
            self._set_status("force_commission.status_idle")

    def emergency_stop(self):
        self.motion.emergency_stop()
        self._set_direction_verified(False)
        self._finish_session(
            "emergency_stop", self.translator("force_commission.emergency_stopped")
        )

    def _on_external_emergency(self):
        self._set_direction_verified(False)
        if self._active:
            self._finish_session(
                "emergency_stop",
                self.translator("force_commission.emergency_stopped"),
            )
        else:
            self._set_status("force_commission.emergency_stopped", warning=True)

    def _prepare_session(self, mode):
        if self._active or self.motion.scan_running:
            self._set_status("force_commission.motion_busy", warning=True)
            return False
        if not self._force_ready(require_analog=(mode == "hold")):
            return False
        try:
            self._safety.arm(self._safety_config())
        except ValueError as exc:
            self._show_validation(str(exc))
            return False
        self._save_settings()
        now = time.perf_counter()
        self._session_log = ForceCommissioningLog(now)
        self._last_logged_sample_time = None
        self._mode = str(mode)
        self._set_commission_active(True)
        return True

    def _safety_config(self):
        return ForceSafetyConfig(
            total_high_n=self.total_limit_spin.value(),
            channel_high_n=self.channel_limit_spin.value(),
            imbalance_high_n=self.imbalance_spin.value(),
            rise_rate_high_n_s=self.rise_rate_spin.value(),
            signal_timeout_s=0.15,
            imbalance_confirm_s=0.05,
            rise_rate_confirm_s=0.02,
        )

    def _force_ready(self, require_analog=False):
        if not self.force.running:
            self._set_status("force_commission.force_required", warning=True)
            return False
        if require_analog and self.force.active_mode != "analog":
            self._set_status("force_commission.analog_required", warning=True)
            return False
        if self._snapshot()[0] is None:
            self._set_status("force_commission.no_signal", warning=True)
            return False
        return True

    def _snapshot(self, window_s=0.02):
        getter = getattr(self.force, "force_safety_snapshot", None)
        if getter is None:
            return None, None, None
        return getter(window_s=float(window_s))

    def _tick(self):
        window_s = self.confirm_spin.value() if self._mode == "hold" else 0.02
        total, channels, sample_time = self._snapshot(window_s=window_s)
        self._update_live_values(total, channels)
        if not self._active:
            return
        now = time.perf_counter()
        decision = self._safety.evaluate(total, channels, sample_time, now)
        self._append_log(now, sample_time, total, channels, decision.reason)
        if decision.kind == "trip":
            self._trip(decision)
            return
        if self._mode != "hold" or now < self._move_pending_until:
            return
        hold_decision = self._hold.evaluate(total, sample_time, now)
        if hold_decision.kind == "abort":
            self._trip_detail(hold_decision.reason)
        elif hold_decision.kind == "correct":
            if self._hold_motion_pending:
                self._set_status_text(
                    self.translator("force_commission.motion_settling")
                )
                return
            try:
                self.motion.queue_force_hold_z_step(
                    hold_decision.direction,
                    hold_decision.step_mm,
                )
                self._hold_motion_pending = True
                self._hold.accept(hold_decision)
                self._move_pending_until = now + max(
                    self.interval_spin.value(), 0.08
                )
                self._append_log(
                    now,
                    sample_time,
                    total,
                    channels,
                    "correction_applied",
                    action=(
                        f"z+{hold_decision.step_mm:.4f}"
                        if hold_decision.direction > 0
                        else f"z-{hold_decision.step_mm:.4f}"
                    ),
                )
                self._set_status_text(
                    self.translator(
                        "force_commission.derivative_correction",
                        derivative=hold_decision.derivative_n_s,
                        direction="Z+" if hold_decision.direction > 0 else "Z-",
                        step=hold_decision.step_mm,
                    )
                )
            except Exception as exc:
                self._trip_detail(f"motion_failed: {exc}")
        elif hold_decision.sample_interval_s > 0:
            self._set_status_text(
                self.translator(
                    "force_commission.derivative_live",
                    derivative=hold_decision.derivative_n_s,
                    deadband=self.tolerance_spin.value(),
                )
            )

    def _queue_next_direction_step(self):
        if not self._verification_pending:
            return
        remaining = self.verify_distance_spin.value() - self._verification_travel_mm
        if remaining <= 0.0000001:
            self._complete_direction_measurement(False, self._current_verify_delta())
            return
        step = min(self.DIRECTION_TEST_INCREMENT_MM, remaining)
        self._verification_step_mm = step
        self._verification_phase = "forward"
        try:
            self.motion.queue_force_verification_z_move(+1, step)
        except Exception as exc:
            self._finish_session("direction_test_failed", str(exc))
            return
        self._set_status_text(
            self.translator(
                "force_commission.verify_moving",
                travel=self._verification_travel_mm,
                maximum=self.verify_distance_spin.value(),
            )
        )

    def _evaluate_direction_step(self):
        if not self._verification_pending or self._verification_phase != "settling":
            return
        total, _channels, _sample_time = self._verification_snapshot()
        if total is None:
            self._finish_session("direction_test_failed", "No force signal")
            return
        delta = float(total) - float(self._verification_before_n)
        threshold = self.verify_delta_spin.value()
        if delta >= threshold:
            self._complete_direction_measurement(True, delta)
            return
        if self._verification_travel_mm + 0.0000001 < self.verify_distance_spin.value():
            self._queue_next_direction_step()
            return
        self._complete_direction_measurement(False, delta)

    def _current_verify_delta(self):
        total, _channels, _sample_time = self._verification_snapshot()
        if total is None or self._verification_before_n is None:
            return 0.0
        return float(total) - float(self._verification_before_n)

    def _verification_snapshot(self):
        getter = getattr(self.force, "force_safety_snapshot", None)
        if getter is None:
            return None, None, None
        return getter(window_s=0.2)

    def _complete_direction_measurement(self, verified, delta):
        if not self._verification_pending:
            return
        self._verification_result = (bool(verified), float(delta))
        self._verification_phase = "return"
        travel = self._verification_travel_mm
        if travel <= 0:
            self._finish_direction_return()
            return
        try:
            self.motion.queue_force_verification_z_move(-1, travel)
        except Exception as exc:
            self._finish_session("direction_return_failed", str(exc))
            return
        self._set_status_text(
            self.translator("force_commission.verify_returning", travel=travel)
        )

    def _finish_direction_return(self):
        if not self._verification_pending or self._verification_result is None:
            return
        verified, delta = self._verification_result
        threshold = self.verify_delta_spin.value()
        self._set_direction_verified(verified)
        detail = self.translator(
            "force_commission.verify_passed"
            if verified
            else "force_commission.verify_failed",
            delta=delta,
            threshold=threshold,
        )
        self._finish_session("direction_verified" if verified else "direction_failed", detail)

    def _trip(self, decision):
        self.motion.emergency_stop()
        should_retract = (
            self.retract_enabled.isChecked()
            and self._direction_verified
            and decision.reason in ForceSafetySupervisor.RETRACT_REASONS
        )
        detail = decision.detail or decision.reason
        self._finish_session(decision.reason, detail)
        if should_retract:
            try:
                self.motion.request_force_hold_retract(
                    self.retract_distance_spin.value()
                )
                detail = f"{detail}; controlled Z- retract queued"
            except Exception as exc:
                detail = f"{detail}; retract failed: {exc}"
        self._set_direction_verified(False)
        self._set_status_text(detail, warning=True)

    def _trip_detail(self, detail):
        self.motion.emergency_stop()
        self._set_direction_verified(False)
        self._finish_session("control_abort", str(detail))

    def _finish_session(self, status, detail=""):
        self._verification_pending = False
        self._hold_motion_pending = False
        self._verification_step_mm = 0.0
        self._verification_travel_mm = 0.0
        self._verification_phase = "idle"
        self._verification_result = None
        self._hold.disarm(str(status))
        self._mode = "idle"
        self._set_commission_active(False)
        saved = self._save_log()
        message = str(detail or status)
        if saved is not None:
            message = f"{message} | {saved}"
        self._set_status_text(message, warning=status not in {"stopped", "direction_verified"})

    def _append_log(
        self,
        now,
        sample_time,
        total,
        channels,
        status,
        action=None,
    ):
        if self._session_log is None or sample_time is None or channels is None:
            return
        if action is None and sample_time == self._last_logged_sample_time:
            return
        self._last_logged_sample_time = sample_time
        snapshot = self._hold.snapshot()
        self._session_log.append(
            now=now,
            sample_monotonic=sample_time,
            total_force_n=total,
            channel_forces_n=channels,
            target_force_n=(self.target_spin.value() if self._mode == "hold" else 0.0),
            force_derivative_n_s=float(
                snapshot.get("force_hold_derivative_n_s", 0.0)
            ),
            derivative_interval_s=float(
                snapshot.get("force_hold_derivative_interval_s", 0.0)
            ),
            z_offset_mm=snapshot["force_hold_accumulated_z_mm"],
            action=action or self._mode,
            status=status,
        )

    def _save_log(self):
        session = self._session_log
        self._session_log = None
        if session is None or not session.rows:
            return None
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = (
            Path(self.config.data_save_dir)
            / "force_commissioning"
            / f"force_commissioning_{timestamp}.csv"
        )
        try:
            saved = session.save(path)
            log(f"[Force Commissioning] log saved: {saved}")
            return saved
        except OSError as exc:
            log(f"[Force Commissioning] log save failed: {exc}", "error")
            return None

    def _save_settings(self):
        self.config.force_safety_total_high_n = self.total_limit_spin.value()
        self.config.force_safety_channel_high_n = self.channel_limit_spin.value()
        self.config.force_safety_imbalance_n = self.imbalance_spin.value()
        self.config.force_safety_rise_rate_n_s = self.rise_rate_spin.value()
        self.config.force_safety_retract_enabled = self.retract_enabled.isChecked()
        self.config.force_safety_retract_mm = self.retract_distance_spin.value()
        self.config.force_derivative_deadband_n_s = self.tolerance_spin.value()
        self.config.force_derivative_z_step_mm = self.z_step_spin.value()
        self.config.force_commission_verify_distance_mm = (
            self.verify_distance_spin.value()
        )
        self.config.force_commission_verify_delta_n = self.verify_delta_spin.value()
        self.config.force_commission_verify_settle_s = self.verify_settle_spin.value()
        self.config.force_derivative_interval_s = self.interval_spin.value()
        self.config.force_derivative_measurement_window_s = self.confirm_spin.value()
        self.config.force_derivative_max_offset_mm = self.max_offset_spin.value()
        self.config.force_derivative_max_error_n = self.max_error_spin.value()
        if self.on_config_saved is not None:
            self.on_config_saved()

    def _update_live_values(self, total, channels):
        values = [total]
        values.extend(list(channels or ())[:4])
        values.extend([None] * (5 - len(values)))
        for (_title, label), value in zip(self.live_labels, values):
            label.setText("--" if value is None else f"{float(value):.3f} N")

    def _set_direction_verified(self, verified):
        self._direction_verified = bool(verified)
        self.ui.forceZDirectionVerified = self._direction_verified
        key = (
            "force_commission.direction_verified"
            if self._direction_verified
            else "force_commission.direction_unverified"
        )
        if hasattr(self, "direction_status_label"):
            self.direction_status_label.setText(self.translator(key))
        self._update_motion_lock()

    def _set_commission_active(self, active):
        self._active = bool(active)
        self.ui.forceCommissioningActive = self._active
        self._update_motion_lock()

    def _update_motion_lock(self, *_args):
        if not hasattr(self, "hold_button"):
            return
        self.hold_button.setEnabled(self._direction_verified and not self._active)
        self.verify_button.setEnabled(not self._active)
        self.monitor_button.setEnabled(not self._active)
        self.retract_enabled.setEnabled(not self._active)
        self.retract_distance_spin.setEnabled(
            self.retract_enabled.isChecked() and not self._active
        )
        self.verify_distance_spin.setEnabled(not self._active)
        self.verify_delta_spin.setEnabled(not self._active)
        self.verify_settle_spin.setEnabled(not self._active)
        for widget in (
            self.total_limit_spin,
            self.channel_limit_spin,
            self.imbalance_spin,
            self.rise_rate_spin,
            self.target_spin,
            self.tolerance_spin,
            self.z_step_spin,
            self.interval_spin,
            self.confirm_spin,
            self.max_offset_spin,
            self.max_error_spin,
        ):
            widget.setEnabled(not self._active)
        self.stop_button.setEnabled(self._active)

    def _on_move_command_result(self, ok, detail):
        if not self._active:
            return
        if not ok:
            self._trip_detail(f"motion_failed: {detail}")
            return
        if self._mode == "hold":
            self._hold_motion_pending = False
            return
        if self._mode != "direction_test" or not self._verification_pending:
            return
        if self._verification_phase == "forward":
            self._verification_travel_mm += self._verification_step_mm
            self._verification_phase = "settling"
            settle_ms = max(200, round(self.verify_settle_spin.value() * 1000))
            self._set_status_text(
                self.translator(
                    "force_commission.verify_settling",
                    settle=self.verify_settle_spin.value(),
                    travel=self._verification_travel_mm,
                )
            )
            QTimer.singleShot(settle_ms, self._evaluate_direction_step)
        elif self._verification_phase == "return":
            self._finish_direction_return()

    def _show_validation(self, detail):
        self._set_status_text(str(detail), warning=True)
        QMessageBox.warning(
            self,
            self.translator("force_commission.invalid_title"),
            str(detail),
        )

    def _set_status(self, key, warning=False):
        self._set_status_text(self.translator(key), warning=warning)

    def _set_status_text(self, text, warning=False):
        color = "#b42318" if warning else "#3b6b56"
        self.status_label.setStyleSheet(f"color: {color}; font-weight: 600;")
        self.status_label.setText(str(text))

    def closeEvent(self, event):
        if self._active:
            self.stop_session()
        event.accept()

    def shutdown(self):
        if self._active:
            self.stop_session()
        self._timer.stop()
