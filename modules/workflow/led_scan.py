from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
import time

from modules.app_runtime import RuntimeStatus, ni_resource
from modules.daq.device_catalog import selected_device_name
from modules.workflow.scan_analysis import build_spatial_scan_analysis
from utils.log import log


class ScanWorkflowState(str, Enum):
    IDLE = "idle"
    PREPARING = "preparing"
    RUNNING = "running"
    SAVING = "saving"


@dataclass(frozen=True)
class ScanPlan:
    axis: str
    direction: int
    led_count: int
    led_size_mm: float
    distance_mm: float
    speed_mm_s: float
    sample_rate_hz: int
    samples_per_led: float
    ramp_distance_mm: float
    constant_speed_distance_mm: float
    triangular_expected: bool
    motion_telemetry_interval_ms: int
    estimated_motion_samples_per_led: float

    @classmethod
    def build(
        cls,
        axis,
        direction,
        led_count,
        led_size_mm,
        speed_mm_s,
        sample_rate_hz,
        profile,
        pulses_per_mm,
    ):
        if float(speed_mm_s) <= 0:
            raise ValueError("Scan speed must be greater than zero")
        distance_mm = int(led_count) * float(led_size_mm)
        target_speed = profile.vt / pulses_per_mm
        start_speed = profile.vo / pulses_per_mm
        ramp_time_s = (profile.acc_time + profile.dec_time) / 1000.0
        ramp_distance = (start_speed + target_speed) * ramp_time_s / 2.0
        constant_distance = max(0.0, distance_mm - ramp_distance)
        led_traversal_ms = (
            float(led_size_mm) / float(speed_mm_s) * 1000.0
        )
        telemetry_interval_ms = max(
            2,
            min(10, max(1, int(led_traversal_ms / 4.0))),
        )
        return cls(
            axis=str(axis),
            direction=1 if int(direction) >= 0 else -1,
            led_count=int(led_count),
            led_size_mm=float(led_size_mm),
            distance_mm=distance_mm,
            speed_mm_s=float(speed_mm_s),
            sample_rate_hz=int(sample_rate_hz),
            samples_per_led=(
                float(sample_rate_hz) * float(led_size_mm) / float(speed_mm_s)
            ),
            ramp_distance_mm=ramp_distance,
            constant_speed_distance_mm=constant_distance,
            triangular_expected=constant_distance <= 0.0,
            motion_telemetry_interval_ms=telemetry_interval_ms,
            estimated_motion_samples_per_led=(
                led_traversal_ms / telemetry_interval_ms
            ),
        )


@dataclass(frozen=True)
class ScanReadiness:
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def can_start(self) -> bool:
        return not self.blockers


@dataclass(frozen=True)
class ScanResult:
    outcome: str
    group_id: int
    file_count: int
    save_dir: str
    paths: dict[str, str]
    led_bins_covered: int = 0
    led_bins_expected: int = 0
    minimum_samples_per_led: int = 0
    maximum_samples_per_led: int = 0
    constant_speed_fraction: float = 0.0
    capture_duration_s: float = 0.0
    scan_id: str = ""
    operator_name: str = ""
    missing_streams: tuple[str, ...] = ()
    detail: str = ""


class LedScanWorkflow:
    MIN_SAMPLES_PER_LED = 20.0
    MIN_MOTION_SAMPLES_PER_LED = 2.0
    PREPARE_TIMEOUT_S = 6.0
    EXPECTED_STREAMS = ("daq", "force")
    ACTIVE_PHASES = {
        ScanWorkflowState.PREPARING,
        ScanWorkflowState.RUNNING,
        ScanWorkflowState.SAVING,
    }
    INTERLOCK_WIDGETS = (
        "Axis_choice",
        "direction_choice",
        "Circle_times",
        "Gap_time",
        "Speed_Setting_val",
        "sampleRateSpinBox",
        "daqDeviceComboBox",
        "startStopButton",
        "recorderStartButton",
        "recorderStopButton",
        "aoChannelComboBox",
        "aoVoltageSpinBox",
        "aoControlButton",
        "ivModeComboBox",
        "ivStartSpinBox",
        "ivStopSpinBox",
        "ivStepSpinBox",
        "ivRepeatSpinBox",
        "ivControlButton",
        "forceModeComboBox",
        "forceDeviceComboBox",
        "forceSampleRateSpinBox",
        "forceTerminalConfigComboBox",
        "forceVoltageRangeComboBox",
        "forceFullScaleSpinBox",
        "forceStartButton",
        "forceZeroButton",
        "scanLoadConfirmButton",
        "distanceSpinBox",
        "xPosButton",
        "xNegButton",
        "yPosButton",
        "yNegButton",
        "zPosButton",
        "zNegButton",
        "RPosButton",
        "RNegButton",
        "Forward_circle",
        "Backward_circle",
    )

    def __init__(
        self,
        ui,
        motion_controller,
        daq_controller,
        force_controller,
        recorder,
        config,
        runtime=None,
        translator=None,
    ):
        self.ui = ui
        self.motion = motion_controller
        self.daq = daq_controller
        self.force = force_controller
        self.recorder = recorder
        self.config = config
        self.runtime = runtime
        self.translator = translator
        self.state = ScanWorkflowState.IDLE
        self._prepare_deadline = 0.0
        self._started_daq = False
        self._active_plan = None
        self._control_enabled_snapshot = {}
        self._controls_locked = False
        self._progress_origin = None
        self._progress_percent = 0.0
        self._last_progress_update = 0.0
        self._capture_started = False
        self._abort_requested = False
        self._last_result = None
        self._last_failure = None
        self._last_preflight = ScanReadiness()
        self._confirmed_force_n = None
        self._load_confirmed_at = ""
        self._save_worker = None
        self._save_bridge = None
        self._save_started_at = 0.0
        self._configure_inputs()
        self._connect_inputs()
        self.update_preview()

    @property
    def running(self):
        return self.state is not ScanWorkflowState.IDLE

    def retranslate_ui(self):
        if self.state is ScanWorkflowState.PREPARING:
            self._set_feedback(self._t("scan.preparing"), warning=False)
        elif self.state is ScanWorkflowState.RUNNING:
            self._show_running_progress()
        elif self.state is ScanWorkflowState.SAVING:
            self._show_saving_progress()
        elif self._last_result is not None:
            self._show_result(self._last_result)
        else:
            self._last_failure = None
            self._set_runtime_scan(RuntimeStatus.READY)
            self.refresh_readiness(preserve_result=False)
        self._update_action_text()

    def toggle_scan(self):
        if self.state is ScanWorkflowState.PREPARING:
            self._fail(
                self._t("scan.cancelled_preparation"),
                runtime_status=RuntimeStatus.WARNING,
            )
            return
        if self.state is ScanWorkflowState.RUNNING:
            self.motion.emergency_stop()
            return
        if self.state is ScanWorkflowState.SAVING:
            return
        self.start_scan()

    def wait_for_save(self):
        worker = getattr(self, "_save_worker", None)
        if worker is not None and worker.isRunning():
            worker.wait()

    def start_scan(self):
        if self.running:
            return

        self._started_daq = False
        self._active_plan = None
        try:
            plan = self.current_plan()
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
            self._reject_start(self._t("scan.invalid_plan", detail=str(exc)))
            return

        readiness = self._evaluate_readiness(plan)
        self._last_preflight = readiness
        if not readiness.can_start:
            self._reject_start(readiness.blockers[0])
            return

        try:
            save_dir = getattr(self.config, "data_save_dir", "data")
            set_save_dir = getattr(self.recorder, "set_save_dir", None)
            if set_save_dir is not None and not set_save_dir(save_dir):
                self._reject_start(self._t("scan.recording_active"))
                return
        except OSError as exc:
            self._reject_start(
                self._t("scan.output_dir_unavailable", detail=str(exc))
            )
            return

        self._last_result = None
        self._last_failure = None
        self._active_plan = plan
        self._capture_started = False
        self._abort_requested = False
        self.state = ScanWorkflowState.PREPARING
        self._started_daq = self.daq.thread is None
        self._set_controls_locked(True)
        self._set_phase("preparing")
        self._set_feedback(self._t("scan.preparing"), warning=False)
        self._update_action_text()
        self._set_runtime_scan(RuntimeStatus.CONNECTING, "preparing")

        if self.daq.thread is None:
            self.daq.start()
            if self.daq.thread is None:
                self._fail(self._t("scan.daq_start_failed"))
                return
        self._prepare_deadline = time.perf_counter() + self.PREPARE_TIMEOUT_S
        self._single_shot(30, self._poll_prepare)

    def current_plan(self):
        axis = self.ui.Axis_choice.currentText()
        direction = self._direction()
        led_count = self.ui.Circle_times.value()
        led_size = self.ui.Gap_time.value()
        speed = self.motion._clamp_speed_mm_s(self.ui.Speed_Setting_val.value())
        sample_rate = self.ui.sampleRateSpinBox.value()
        config = self.motion.AXIS_CONFIG[axis]
        profile = self.motion._build_motion_profile(
            speed_mm_s=speed,
            pulses_per_mm=config["pulses_per_mm"],
            accel_mm_s2=config["accel_mm_s2"],
        )
        return ScanPlan.build(
            axis=axis,
            direction=direction,
            led_count=led_count,
            led_size_mm=led_size,
            speed_mm_s=speed,
            sample_rate_hz=sample_rate,
            profile=profile,
            pulses_per_mm=config["pulses_per_mm"],
        )

    def update_preview(self, *_args):
        if self.running:
            return
        self._last_result = None
        self._last_failure = None
        self.ui.scanQualityLabel.setToolTip("")
        self._set_runtime_scan(RuntimeStatus.READY)
        self.refresh_readiness(preserve_result=False)

    def refresh_readiness(self, preserve_result=True):
        if self.running:
            self._monitor_active_streams()
            return self._last_preflight

        try:
            plan = self.current_plan()
            self.ui.distanceSpinBox_2.setValue(plan.distance_mm)
            readiness = self._evaluate_readiness(plan)
            configured = bool(
                plan.distance_mm > 0
                and plan.led_count > 0
                and self._selected_daq_channels()
                and self._daq_device_name()
            )
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
            plan = None
            readiness = ScanReadiness(
                blockers=(self._t("scan.invalid_plan", detail=str(exc)),)
            )
            configured = False

        self._last_preflight = readiness
        force_ready = bool(
            self.force.running and self.force.latest_vals is not None
        )
        confirm_button = getattr(self.ui, "scanLoadConfirmButton", None)
        if confirm_button is not None:
            if not force_ready and confirm_button.isChecked():
                confirm_button.setChecked(False)
            confirm_button.setEnabled(force_ready)
        load_confirmed = bool(force_ready and self._load_confirmed())
        self.ui.scanPlanConfigured = configured
        self.ui.scanForceReady = force_ready
        self.ui.scanLoadConfirmed = load_confirmed
        self.ui.scanPreflightReady = readiness.can_start
        self.ui.scanPreflightWarning = bool(readiness.warnings)
        self.ui.Forward_circle.setEnabled(readiness.can_start)
        tooltip_lines = [*readiness.blockers, *readiness.warnings]
        self.ui.Forward_circle.setToolTip("\n".join(tooltip_lines))
        self.ui.scanQualityLabel.setToolTip("\n".join(tooltip_lines))

        if preserve_result and self._last_result is not None:
            self._show_result(self._last_result)
            return readiness
        if preserve_result and self._last_failure:
            self._set_phase("error")
            self._set_feedback(self._last_failure, warning=True)
            return readiness

        self._set_phase("idle")
        if readiness.blockers:
            self._set_feedback(
                self._short_blocker_text(readiness.blockers[0]),
                warning=True,
                summary=readiness.blockers[0],
            )
        elif readiness.warnings:
            if plan is not None and plan.triangular_expected:
                short_warning = self._t("scan.triangular_short")
            elif (
                plan is not None
                and plan.samples_per_led < self.MIN_SAMPLES_PER_LED
            ):
                short_warning = self._t("scan.low_resolution_short")
            else:
                short_warning = self._t("scan.low_motion_resolution_short")
            self._set_feedback(
                short_warning,
                warning=True,
                summary=readiness.warnings[0],
            )
        elif plan is not None:
            self._set_feedback(
                self._t(
                    "scan.ready",
                    distance=plan.distance_mm,
                    samples=plan.samples_per_led,
                ),
                warning=False,
            )
        self._update_action_text()
        return readiness

    def _short_blocker_text(self, message):
        fixed_messages = {
            self._t("scan.recording_active"): "scan.recording_active_short",
            self._t("scan.motion_busy"): "scan.motion_busy_short",
            self._t("scan.force_required"): "scan.force_required_short",
            self._t("scan.force_waiting"): "scan.force_waiting_short",
            self._t("scan.load_confirmation_required"): (
                "scan.load_confirmation_required_short"
            ),
            self._t("scan.channels_required"): "scan.channels_required_short",
            self._t("scan.device_required"): "scan.device_required_short",
            self._t("scan.invalid_dimensions"): "scan.invalid_dimensions_short",
        }
        key = fixed_messages.get(message, "scan.not_ready_short")
        return self._t(key)

    def _evaluate_readiness(self, plan):
        blockers = []
        warnings = []

        if self.recorder.recording:
            blockers.append(self._t("scan.recording_active"))
        if self.motion.scan_running:
            blockers.append(self._t("scan.motion_busy"))
        if not self.force.running:
            blockers.append(self._t("scan.force_required"))
        elif self.force.latest_vals is None:
            blockers.append(self._t("scan.force_waiting"))
        elif not self._load_confirmed():
            blockers.append(self._t("scan.load_confirmation_required"))
        if not self._selected_daq_channels():
            blockers.append(self._t("scan.channels_required"))
        if not self._daq_device_name():
            blockers.append(self._t("scan.device_required"))

        resource_conflict = self._daq_resource_conflict()
        if resource_conflict:
            blockers.append(
                self._t("scan.resource_busy", detail=resource_conflict)
            )
        if plan.distance_mm <= 0 or plan.led_count <= 0:
            blockers.append(self._t("scan.invalid_dimensions"))
        if plan.triangular_expected:
            warnings.append(self._t("scan.triangular"))
        if plan.samples_per_led < self.MIN_SAMPLES_PER_LED:
            warnings.append(
                self._t("scan.low_resolution", samples=plan.samples_per_led)
            )
        if (
            plan.estimated_motion_samples_per_led
            < self.MIN_MOTION_SAMPLES_PER_LED
        ):
            warnings.append(
                self._t(
                    "scan.low_motion_resolution",
                    samples=plan.estimated_motion_samples_per_led,
                )
            )
        return ScanReadiness(tuple(blockers), tuple(warnings))

    def _daq_resource_conflict(self):
        resources = getattr(self.daq, "resources", None)
        if resources is None or not hasattr(resources, "snapshot"):
            return ""
        resource = ni_resource(self._daq_device_name(), "ai")
        owner = resources.snapshot().get(resource)
        if owner in (None, "daq"):
            return ""
        return f"{resource} is in use by {owner}"

    def _poll_prepare(self):
        if self.state is not ScanWorkflowState.PREPARING:
            return
        if self.daq.thread is None:
            self._fail(self._t("scan.daq_lost"))
            return
        if not self.force.running:
            self._fail(self._t("scan.force_lost"))
            return
        daq_ready = (
            self.daq.thread is not None
            and self.daq.thread.sample_clock_origin is not None
        )
        if daq_ready and self.force.running:
            self._begin_motion()
            return
        if time.perf_counter() >= self._prepare_deadline:
            self._fail(self._t("scan.prepare_timeout"))
            return
        self._single_shot(30, self._poll_prepare)

    def _begin_motion(self):
        plan = self._active_plan
        self.state = ScanWorkflowState.RUNNING
        self._progress_origin = None
        self._progress_percent = 0.0
        self._last_progress_update = 0.0
        self._set_phase("running")
        self._show_running_progress()
        self._update_action_text()
        self._set_runtime_scan(RuntimeStatus.RUNNING, "running")
        metadata = self._scan_metadata(plan)

        def capture_start(clock):
            self.recorder.start(metadata=metadata, start_monotonic=clock)
            if not self.recorder.recording:
                raise RuntimeError(self._t("scan.recording_start_failed"))
            self._capture_started = True
            if self.runtime is not None:
                self.runtime.set("recording", RuntimeStatus.RUNNING)

        started = self.motion.start_scan(
            axis_name=plan.axis,
            direction=plan.direction,
            distance_mm=plan.distance_mm,
            telemetry_interval_ms=plan.motion_telemetry_interval_ms,
            on_capture_start=capture_start,
            on_telemetry=self.recorder.add_motion_sample,
            on_capture_end=self.recorder.set_capture_end,
            on_finished=self._on_motion_finished,
        )
        if not started:
            self._fail(self._t("scan.motion_busy"))
            return

        if plan.triangular_expected:
            log(
                "[Scan] Warning: no constant-speed segment is expected; "
                "the controller may automatically reduce speed",
                "warning",
            )
        if plan.samples_per_led < self.MIN_SAMPLES_PER_LED:
            log(
                f"[Scan] Warning: only {plan.samples_per_led:.1f} samples per LED",
                "warning",
            )

    def _scan_metadata(self, plan):
        started_at = datetime.now().astimezone()
        scan_id = (
            started_at.strftime("R%y%m%d-%H%M%S-")
            + f"{started_at.microsecond // 1000:03d}"
        )
        metadata = asdict(plan)
        metadata.update(
            {
                "workflow": "single_led_scan",
                "scan_id": scan_id,
                "started_at": started_at.isoformat(timespec="milliseconds"),
                "operator_name": getattr(self.config, "operator_name", "") or "",
                "output_directory": str(Path(self.recorder.save_dir).resolve()),
                "interface_language": getattr(self.translator, "language", "en"),
                "daq_device": self._daq_device_name(),
                "daq_channels": self._selected_daq_channels(),
                "force_mode": self.force.active_mode,
                "force_device": self.force._force_device(),
                "minimum_samples_per_led": self.MIN_SAMPLES_PER_LED,
                "operator_load_confirmed": self._load_confirmed(),
                "confirmed_total_force_n": self._confirmed_force_n,
                "load_confirmed_at": self._load_confirmed_at,
            }
        )
        device_info = self._daq_device_info()
        if device_info is not None:
            metadata.update(
                {
                    "daq_product_type": device_info.product_type,
                    "daq_device_simulated": device_info.is_simulated,
                    "daq_simultaneous_sampling": device_info.simultaneous_sampling,
                    "daq_ai_rate_limit_hz": device_info.ai_rate_limit(
                        len(metadata["daq_channels"])
                    ),
                }
            )
        daq_snapshot = getattr(
            getattr(self, "daq", None),
            "active_configuration_metadata",
            None,
        )
        if callable(daq_snapshot):
            metadata.update(daq_snapshot())
        force_snapshot = getattr(self.force, "active_configuration_metadata", None)
        if callable(force_snapshot):
            metadata.update(force_snapshot())
        return metadata

    def _monitor_active_streams(self):
        if (
            self.state is not ScanWorkflowState.RUNNING
            or self._abort_requested
        ):
            return

        if self.daq.thread is None:
            detail = self._t("scan.daq_lost")
        elif not self.force.running:
            detail = self._t("scan.force_lost")
        elif self._capture_started and not self.recorder.recording:
            detail = self._t("scan.recording_lost")
        else:
            return

        self._abort_requested = True
        self._set_feedback(detail, warning=True)
        self._set_runtime_scan(RuntimeStatus.WARNING, "stream_lost")
        log(f"[Scan] {detail}; requesting emergency stop", "error")
        self.motion.emergency_stop()

    def _on_motion_progress(self, state):
        if self.state is not ScanWorkflowState.RUNNING or self._active_plan is None:
            return
        if self._progress_origin is None:
            self._progress_origin = int(state.position)

        pulses_per_mm = self.motion.AXIS_CONFIG[self._active_plan.axis][
            "pulses_per_mm"
        ]
        target_pulses = max(
            1,
            round(self._active_plan.distance_mm * pulses_per_mm),
        )
        travelled = abs(int(state.position) - self._progress_origin)
        self._progress_percent = min(99.0, travelled * 100.0 / target_pulses)
        now = time.perf_counter()
        if now - self._last_progress_update >= 0.1:
            self._last_progress_update = now
            self._show_running_progress()

    def _show_running_progress(self):
        text = self._t("scan.progress", progress=self._progress_percent)
        self._set_feedback(text, warning=False)

    def _on_motion_finished(self, completed, detail):
        if self.state is not ScanWorkflowState.RUNNING:
            return
        self.state = ScanWorkflowState.SAVING
        self._progress_percent = 100.0 if completed else self._progress_percent
        self._set_controls_locked(True)
        self._set_phase("saving")
        self._set_feedback(self._t("scan.saving"), warning=False)
        self._update_action_text()
        self._set_runtime_scan(RuntimeStatus.STOPPING, "saving")
        self._save_started_at = time.perf_counter()
        self._poll_save_status()
        drain_ms = round(self.config.daq_chunk_interval_s * 1000) + 80
        self._single_shot(
            drain_ms,
            lambda: self._finalize(bool(completed), str(detail)),
        )

    def _show_saving_progress(self):
        elapsed = max(0.0, time.perf_counter() - self._save_started_at)
        self._set_feedback(
            self._t("scan.saving_elapsed", seconds=elapsed),
            warning=False,
        )

    def _poll_save_status(self):
        if self.state is not ScanWorkflowState.SAVING:
            return
        self._show_saving_progress()
        self._single_shot(250, self._poll_save_status)

    def _finalize(self, completed, detail):
        seal = getattr(self.recorder, "seal", None)
        save_sealed = getattr(self.recorder, "save_sealed", None)
        if not callable(seal) or not callable(save_sealed):
            self._finalize_legacy(completed, detail)
            return
        if getattr(self, "_save_worker", None) is not None:
            return

        try:
            if not seal():
                raise RuntimeError("recording was not active when saving started")
            self._capture_started = False
            if self.runtime is not None:
                self.runtime.set("recording", RuntimeStatus.STOPPING)
            self._stop_started_daq_for_save()
        except Exception as exc:
            self._handle_async_save_failure(exc)
            return

        operation = lambda: self._prepare_sealed_save(completed, detail)
        if self._start_save_worker(operation):
            return
        try:
            payload = operation()
        except Exception as exc:
            self._handle_async_save_failure(exc)
            return
        self._complete_sealed_save(payload)

    def _start_save_worker(self, operation):
        try:
            from PySide6.QtCore import QCoreApplication, Qt

            if QCoreApplication.instance() is None:
                return False
            from modules.workflow.scan_save_worker import (
                ScanSaveBridge,
                ScanSaveWorker,
            )
        except (ImportError, RuntimeError):
            return False

        worker = ScanSaveWorker(operation)
        bridge = ScanSaveBridge(
            self._complete_sealed_save,
            self._handle_async_save_failure,
            lambda: self._release_save_worker(worker),
        )
        self._save_worker = worker
        self._save_bridge = bridge
        worker.succeeded.connect(bridge.deliver_success, Qt.QueuedConnection)
        worker.failed.connect(bridge.deliver_failure, Qt.QueuedConnection)
        worker.finished.connect(bridge.deliver_finished, Qt.QueuedConnection)
        worker.start()
        return True

    def _release_save_worker(self, worker):
        if self._save_worker is worker:
            self._save_worker = None
            self._save_bridge = None

    def _stop_started_daq_for_save(self):
        if (
            getattr(self, "_started_daq", False)
            and getattr(getattr(self, "daq", None), "thread", None) is not None
        ):
            self.daq.stop()
        self._started_daq = False

    def _prepare_sealed_save(self, completed, detail):
        quality = self._actual_motion_quality(detail)
        try:
            spatial_analysis = self._spatial_scan_analysis()
            self.recorder.set_spatial_scan(spatial_analysis)
            quality.update(spatial_analysis.metadata)
        except Exception as exc:
            quality.update(
                {
                    "spatial_mapping_available": False,
                    "spatial_mapping_warning": True,
                    "spatial_mapping_detail": (
                        f"spatial mapping failed: {type(exc).__name__}: {exc}"
                    ),
                    "spatial_leds_distinguishable": False,
                }
            )
            log(quality["spatial_mapping_detail"], "error")

        warning_details = []
        if quality.get("motion_quality_warning"):
            warning_details.append(quality.get("motion_quality_detail", ""))
        if quality.get("spatial_mapping_warning"):
            warning_details.append(quality.get("spatial_mapping_detail", ""))
        quality["scan_quality_warning"] = bool(warning_details)
        quality["scan_quality_detail"] = (
            "; ".join(value for value in warning_details if value) or "ok"
        )
        quality.update(
            {
                "scan_completed": bool(completed),
                "scan_completion_detail": str(detail),
                **self._capture_summary_metadata(),
            }
        )
        self.recorder.update_metadata(quality)
        paths = self.recorder.save_sealed() or {}
        return bool(completed), str(detail), quality, dict(paths)

    def _complete_sealed_save(self, payload):
        completed, detail, quality, paths = payload
        if self.runtime is not None:
            self.runtime.set("recording", RuntimeStatus.READY)
        self._finish_session()

        quality_warning = bool(quality["scan_quality_warning"])
        missing_streams = tuple(
            stream for stream in self.EXPECTED_STREAMS if stream not in paths
        )
        if missing_streams:
            outcome = "error"
        elif not completed or quality_warning:
            outcome = "warning"
        else:
            outcome = "completed"

        result = ScanResult(
            outcome=outcome,
            group_id=int(self.recorder.group_id),
            file_count=len(paths),
            save_dir=str(Path(self.recorder.save_dir).resolve()),
            paths=dict(paths),
            led_bins_covered=int(quality.get("led_bins_covered", 0)),
            led_bins_expected=int(quality.get("led_bins_expected", 0)),
            minimum_samples_per_led=int(
                quality.get("minimum_samples_per_led_actual", 0)
            ),
            maximum_samples_per_led=int(
                quality.get("maximum_samples_per_led_actual", 0)
            ),
            constant_speed_fraction=float(
                quality.get("measured_constant_speed_fraction", 0.0)
            ),
            capture_duration_s=float(quality.get("capture_duration_s") or 0.0),
            scan_id=str(getattr(self.recorder, "metadata", {}).get("scan_id", "")),
            operator_name=str(
                getattr(self.recorder, "metadata", {}).get("operator_name", "")
            ),
            missing_streams=missing_streams,
            detail=(
                quality["scan_quality_detail"]
                if quality_warning
                else str(detail)
            ),
        )
        self._last_result = result
        self._last_failure = None
        self.ui.scanLastSavedPaths = dict(paths)
        self._show_result(result)
        self.refresh_readiness(preserve_result=True)

        runtime_status = {
            "completed": RuntimeStatus.READY,
            "warning": RuntimeStatus.WARNING,
            "error": RuntimeStatus.ERROR,
        }[outcome]
        self._set_runtime_scan(runtime_status, outcome)

        if outcome == "completed":
            log(f"[Scan] Completed; saved {len(paths)} files to {result.save_dir}")
        elif missing_streams:
            missing_text = ", ".join(missing_streams)
            log(
                f"[Scan] Incomplete data set; missing {missing_text}; "
                f"saved to {result.save_dir}",
                "error",
            )
        elif completed:
            log(f"[Scan] Saved with motion warning: {result.detail}", "warning")
        else:
            log(f"[Scan] Stopped: {detail}; partial data saved", "warning")

    def _handle_async_save_failure(self, exc):
        cancel_save = getattr(self.recorder, "cancel_save", None)
        if callable(cancel_save):
            cancel_save()
        self._finish_session()
        if self.runtime is not None:
            self.runtime.set("recording", RuntimeStatus.ERROR, str(exc))
        self._set_runtime_scan(RuntimeStatus.ERROR, "save_failed")
        self._set_phase("error")
        self._last_failure = self._t("scan.save_failed", detail=str(exc))
        self._set_feedback(self._last_failure, warning=True)
        log(f"[Scan] Save failed: {type(exc).__name__}: {exc}", "error")

    def _finalize_legacy(self, completed, detail):
        quality = self._actual_motion_quality(detail)
        try:
            spatial_analysis = self._spatial_scan_analysis()
            self.recorder.set_spatial_scan(spatial_analysis)
            quality.update(spatial_analysis.metadata)
        except Exception as exc:
            quality.update(
                {
                    "spatial_mapping_available": False,
                    "spatial_mapping_warning": True,
                    "spatial_mapping_detail": (
                        f"spatial mapping failed: {type(exc).__name__}: {exc}"
                    ),
                    "spatial_leds_distinguishable": False,
                }
            )
            log(quality["spatial_mapping_detail"], "error")

        warning_details = []
        if quality.get("motion_quality_warning"):
            warning_details.append(quality.get("motion_quality_detail", ""))
        if quality.get("spatial_mapping_warning"):
            warning_details.append(quality.get("spatial_mapping_detail", ""))
        quality["scan_quality_warning"] = bool(warning_details)
        quality["scan_quality_detail"] = (
            "; ".join(detail for detail in warning_details if detail) or "ok"
        )
        quality.update(
            {
                "scan_completed": bool(completed),
                "scan_completion_detail": str(detail),
                **self._capture_summary_metadata(),
            }
        )
        try:
            self.recorder.update_metadata(quality)
            paths = self.recorder.stop() or {}
        except Exception as exc:
            self._finish_session()
            if self.runtime is not None:
                self.runtime.set("recording", RuntimeStatus.ERROR, str(exc))
            self._set_runtime_scan(RuntimeStatus.ERROR, "save_failed")
            self._set_phase("error")
            self._last_failure = self._t("scan.save_failed", detail=str(exc))
            self._set_feedback(self._last_failure, warning=True)
            log(f"[Scan] Save failed: {type(exc).__name__}: {exc}", "error")
            return

        if self.runtime is not None:
            self.runtime.set("recording", RuntimeStatus.READY)
        self._finish_session()

        quality_warning = bool(quality["scan_quality_warning"])
        missing_streams = tuple(
            stream for stream in self.EXPECTED_STREAMS if stream not in paths
        )
        if missing_streams:
            outcome = "error"
        elif not completed or quality_warning:
            outcome = "warning"
        else:
            outcome = "completed"

        result = ScanResult(
            outcome=outcome,
            group_id=int(self.recorder.group_id),
            file_count=len(paths),
            save_dir=str(Path(self.recorder.save_dir).resolve()),
            paths=dict(paths),
            led_bins_covered=int(quality.get("led_bins_covered", 0)),
            led_bins_expected=int(quality.get("led_bins_expected", 0)),
            minimum_samples_per_led=int(
                quality.get("minimum_samples_per_led_actual", 0)
            ),
            maximum_samples_per_led=int(
                quality.get("maximum_samples_per_led_actual", 0)
            ),
            constant_speed_fraction=float(
                quality.get("measured_constant_speed_fraction", 0.0)
            ),
            capture_duration_s=float(quality.get("capture_duration_s") or 0.0),
            scan_id=str(getattr(self.recorder, "metadata", {}).get("scan_id", "")),
            operator_name=str(
                getattr(self.recorder, "metadata", {}).get("operator_name", "")
            ),
            missing_streams=missing_streams,
            detail=(
                quality["scan_quality_detail"]
                if quality_warning
                else str(detail)
            ),
        )
        self._last_result = result
        self._last_failure = None
        self.ui.scanLastSavedPaths = dict(paths)
        self._show_result(result)
        self.refresh_readiness(preserve_result=True)

        runtime_status = {
            "completed": RuntimeStatus.READY,
            "warning": RuntimeStatus.WARNING,
            "error": RuntimeStatus.ERROR,
        }[outcome]
        self._set_runtime_scan(runtime_status, outcome)

        if outcome == "completed":
            log(f"[Scan] Completed; saved {len(paths)} files to {result.save_dir}")
        elif missing_streams:
            missing_text = ", ".join(missing_streams)
            log(
                f"[Scan] Incomplete data set; missing {missing_text}; "
                f"saved to {result.save_dir}",
                "error",
            )
        elif completed:
            log(f"[Scan] Saved with motion warning: {result.detail}", "warning")
        else:
            log(f"[Scan] Stopped: {detail}; partial data saved", "warning")

    def _actual_motion_quality(self, detail):
        plan = self._active_plan
        pulses_per_mm = self.motion.AXIS_CONFIG[plan.axis]["pulses_per_mm"]
        rows = list(self.recorder.motion_buffer)
        moving = [row for row in rows if row[3] in (2, 3, 4)]
        constant = [row for row in moving if row[3] == 3]
        speeds = [row[2] / pulses_per_mm for row in moving]
        constant_speeds = [row[2] / pulses_per_mm for row in constant]
        constant_fraction = len(constant) / len(moving) if moving else 0.0
        max_speed = max(speeds, default=0.0)
        mean_constant_speed = (
            sum(constant_speeds) / len(constant_speeds)
            if constant_speeds
            else 0.0
        )
        warning_reasons = []
        if detail == "triangular" or not constant:
            warning_reasons.append("no measured constant-speed segment")
        if max_speed < plan.speed_mm_s * 0.9:
            warning_reasons.append(
                f"peak speed {max_speed:.2f} mm/s below command {plan.speed_mm_s:.2f} mm/s"
            )
        return {
            "motion_result": detail,
            "measured_motion_samples": len(moving),
            "measured_constant_speed_samples": len(constant),
            "measured_constant_speed_fraction": constant_fraction,
            "measured_peak_speed_mm_s": max_speed,
            "measured_mean_constant_speed_mm_s": mean_constant_speed,
            "motion_quality_warning": bool(warning_reasons),
            "motion_quality_detail": "; ".join(warning_reasons) or "ok",
        }

    def _capture_summary_metadata(self):
        start_clock = getattr(self.recorder, "start_time", None)
        end_clock = getattr(self.recorder, "capture_end_clock", None)
        duration = None
        if start_clock is not None and end_clock is not None:
            duration = max(0.0, float(end_clock) - float(start_clock))
        return {
            "capture_duration_s": duration,
            "data_rows": {
                "daq": len(getattr(self.recorder, "daq_buffer", ())),
                "force": len(getattr(self.recorder, "force_buffer", ())),
                "motion": len(getattr(self.recorder, "motion_buffer", ())),
                "spatial": len(getattr(self.recorder, "spatial_buffer", ())),
                "led_summary": len(
                    getattr(self.recorder, "led_summary_buffer", ())
                ),
            },
            "expected_streams": list(self.EXPECTED_STREAMS),
        }

    def _spatial_scan_analysis(self):
        plan = self._active_plan
        pulses_per_mm = self.motion.AXIS_CONFIG[plan.axis]["pulses_per_mm"]
        return build_spatial_scan_analysis(
            daq_rows=getattr(self.recorder, "daq_buffer", ()),
            motion_rows=getattr(self.recorder, "motion_buffer", ()),
            daq_channels=getattr(self.recorder, "daq_channels", ()),
            led_count=plan.led_count,
            led_size_mm=plan.led_size_mm,
            pulses_per_mm=pulses_per_mm,
            direction=plan.direction,
            minimum_samples_per_led=self.MIN_SAMPLES_PER_LED,
        )

    def _fail(self, detail, runtime_status=RuntimeStatus.ERROR):
        save_error = None
        if self.recorder.recording:
            try:
                self.recorder.set_capture_end(time.perf_counter())
                self.recorder.stop()
            except Exception as exc:
                save_error = exc
        if self.runtime is not None:
            self.runtime.set(
                "recording",
                RuntimeStatus.ERROR if save_error else RuntimeStatus.READY,
                str(save_error or ""),
            )
        self._finish_session()
        self._last_result = None
        self._last_failure = self._t("scan.failed", detail=detail)
        self._set_phase("error")
        self._set_feedback(self._last_failure, warning=True)
        self._set_runtime_scan(runtime_status, str(detail))
        log(f"[Scan] {detail}", "warning")
        if save_error is not None:
            log(
                f"[Scan] Cleanup save failed: {type(save_error).__name__}: "
                f"{save_error}",
                "error",
            )

    def _reject_start(self, detail):
        self.state = ScanWorkflowState.IDLE
        self._set_phase("idle")
        self._set_feedback(detail, warning=True)
        self._update_action_text()
        log(f"[Scan] Start blocked: {detail}", "warning")

    def _finish_session(self):
        if self._started_daq and self.daq.thread is not None:
            self.daq.stop()
        self._started_daq = False
        self._capture_started = False
        self._abort_requested = False
        self.state = ScanWorkflowState.IDLE
        self._set_controls_locked(False)
        self._reset_load_confirmation()
        self._update_action_text()

    def _configure_inputs(self):
        self.ui.Circle_times.setRange(1, 10000)
        self.ui.Gap_time.setRange(0.001, 100.0)
        self.ui.Gap_time.setDecimals(3)
        if self.ui.Gap_time.value() <= 0.001:
            self.ui.Gap_time.setValue(1.0)
        self.ui.Gap_time.setSuffix(" mm")
        self.ui.distanceSpinBox_2.setRange(0.001, 10000.0)
        self.ui.distanceSpinBox_2.setReadOnly(True)
        self.ui.distanceSpinBox_2.setSuffix(" mm")
        self.ui.Speed_Setting_val.setRange(
            self.motion.MIN_SPEED_MM_S,
            self.motion.MAX_SPEED_MM_S,
        )
        self.ui.Speed_Setting_val.setSuffix(" mm/s")
        self.ui.distanceSpinBox_2.setButtonSymbols(
            self.ui.distanceSpinBox_2.ButtonSymbols.NoButtons
        )

    def _connect_inputs(self):
        self.ui.Forward_circle.clicked.connect(self.toggle_scan)
        self.ui.Emergency_Stop.clicked.connect(self._on_emergency_clicked)
        progress_signal = getattr(
            getattr(self.motion, "motion_worker", None),
            "scan_progress",
            None,
        )
        if progress_signal is not None and hasattr(progress_signal, "connect"):
            progress_signal.connect(self._on_motion_progress)
        confirm_button = getattr(self.ui, "scanLoadConfirmButton", None)
        confirm_signal = getattr(confirm_button, "toggled", None)
        if confirm_signal is not None:
            confirm_signal.connect(self._on_load_confirmation_changed)
        for widget in (
            self.ui.Axis_choice,
            self.ui.direction_choice,
            self.ui.Circle_times,
            self.ui.Gap_time,
            self.ui.Speed_Setting_val,
            self.ui.sampleRateSpinBox,
        ):
            signal = getattr(widget, "currentIndexChanged", None)
            if signal is None:
                signal = getattr(widget, "valueChanged", None)
            if signal is not None:
                signal.connect(self.update_preview)

        for index in range(16):
            checkbox = getattr(self.ui, f"ai{index}CheckBox", None)
            signal = getattr(checkbox, "stateChanged", None)
            if signal is not None:
                signal.connect(self.update_preview)

    def _on_emergency_clicked(self):
        if self.state is ScanWorkflowState.PREPARING:
            self._fail(
                self._t("scan.emergency_preparation"),
                runtime_status=RuntimeStatus.WARNING,
            )

    def _on_load_confirmation_changed(self, checked):
        if self.running:
            return
        if checked:
            self._confirmed_force_n = float(
                getattr(self.force, "latest_force", 0.0)
            )
            self._load_confirmed_at = datetime.now().astimezone().isoformat(
                timespec="seconds"
            )
        else:
            self._confirmed_force_n = None
            self._load_confirmed_at = ""
        self._last_result = None
        self._last_failure = None
        self.ui.scanLoadConfirmed = bool(checked)
        self._set_runtime_scan(RuntimeStatus.READY)
        self.refresh_readiness(preserve_result=False)

    def _set_controls_locked(self, locked):
        widget_names = [*self.INTERLOCK_WIDGETS]
        widget_names.extend(f"ai{index}CheckBox" for index in range(16))

        if locked:
            if not self._controls_locked:
                self._control_enabled_snapshot = {}
                for widget_name in widget_names:
                    widget = getattr(self.ui, widget_name, None)
                    if widget is not None and hasattr(widget, "isEnabled"):
                        self._control_enabled_snapshot[widget_name] = widget.isEnabled()
                self._controls_locked = True
            for widget_name in widget_names:
                widget = getattr(self.ui, widget_name, None)
                if widget is not None and hasattr(widget, "setEnabled"):
                    widget.setEnabled(False)
        else:
            for widget_name, enabled in self._control_enabled_snapshot.items():
                widget = getattr(self.ui, widget_name, None)
                if widget is not None and hasattr(widget, "setEnabled"):
                    widget.setEnabled(enabled)
            self._control_enabled_snapshot = {}
            self._controls_locked = False

        stop_button = getattr(self.ui, "Emergency_Stop", None)
        if stop_button is not None and hasattr(stop_button, "setEnabled"):
            stop_button.setEnabled(True)

    def _update_action_text(self):
        key = {
            ScanWorkflowState.IDLE: "button.scan.start",
            ScanWorkflowState.PREPARING: "button.scan.preparing",
            ScanWorkflowState.RUNNING: "button.scan.running",
            ScanWorkflowState.SAVING: "button.scan.saving",
        }[self.state]
        self.ui.Forward_circle.setText(self._t(key))

    def _set_feedback(self, text, warning, summary=None):
        self.ui.scanReadinessSummaryText = summary or text
        self._set_quality_text(text, warning)

    def _set_quality_text(self, text, warning):
        self.ui.scanQualityLabel.setText(text)
        color = "#F5A623" if warning else "#9CA3AF"
        self.ui.scanQualityLabel.setStyleSheet(f"color: {color};")

    def _set_phase(self, phase):
        self.ui.scanWorkflowPhase = str(phase)

    def _show_result(self, result):
        is_new_result = getattr(self.ui, "scanLastResult", None) is not result
        self.ui.scanLastResult = result
        if is_new_result:
            results_page = getattr(self.ui, "scanResultsPage", None)
            tabs = getattr(self.ui, "tabWidget_3", None)
            if (
                results_page is not None
                and tabs is not None
                and hasattr(tabs, "setCurrentWidget")
            ):
                tabs.setCurrentWidget(results_page)
        tooltip_lines = []
        if result.detail:
            tooltip_lines.append(f"Quality: {result.detail}")
        tooltip_lines.extend(
            f"{name}: {path}" for name, path in sorted(result.paths.items())
        )
        tooltip = "\n".join(tooltip_lines)
        self.ui.scanQualityLabel.setToolTip(tooltip)

        if result.missing_streams:
            missing = ", ".join(result.missing_streams)
            self._set_phase("error")
            self._set_feedback(
                self._t("scan.saved_incomplete_short"),
                warning=True,
                summary=self._t(
                    "scan.saved_incomplete_summary",
                    group=result.group_id,
                    streams=missing,
                    folder=result.save_dir,
                ),
            )
        elif result.outcome == "warning":
            self._set_phase("warning")
            summary_key = (
                "scan.saved_spatial_warning_summary"
                if result.led_bins_expected
                else "scan.saved_warning_summary"
            )
            self._set_feedback(
                self._t("scan.saved_warning_short", group=result.group_id),
                warning=True,
                summary=self._t(
                    summary_key,
                    group=result.group_id,
                    files=result.file_count,
                    covered=result.led_bins_covered,
                    expected=result.led_bins_expected,
                    samples=result.minimum_samples_per_led,
                    folder=result.save_dir,
                ),
            )
        else:
            self._set_phase("completed")
            summary_key = (
                "scan.saved_spatial_summary"
                if result.led_bins_expected
                else "scan.saved_summary"
            )
            self._set_feedback(
                self._t("scan.saved_short", group=result.group_id),
                warning=False,
                summary=self._t(
                    summary_key,
                    group=result.group_id,
                    files=result.file_count,
                    covered=result.led_bins_covered,
                    expected=result.led_bins_expected,
                    samples=result.minimum_samples_per_led,
                    folder=result.save_dir,
                ),
            )

    def _set_runtime_scan(self, status, detail=""):
        if self.runtime is not None:
            self.runtime.set("scan", status, detail)

    def _direction(self):
        if hasattr(self.ui.direction_choice, "currentData"):
            value = self.ui.direction_choice.currentData()
            if value in (-1, 1):
                return value
        return -1 if "reverse" in self.ui.direction_choice.currentText().lower() else 1

    def _load_confirmed(self):
        button = getattr(self.ui, "scanLoadConfirmButton", None)
        return bool(
            button is not None
            and hasattr(button, "isChecked")
            and button.isChecked()
        )

    def _reset_load_confirmation(self):
        button = getattr(self.ui, "scanLoadConfirmButton", None)
        if button is not None and hasattr(button, "setChecked"):
            previous = None
            if hasattr(button, "blockSignals"):
                previous = button.blockSignals(True)
            button.setChecked(False)
            if previous is not None:
                button.blockSignals(previous)
        self.ui.scanLoadConfirmed = False
        self._confirmed_force_n = None
        self._load_confirmed_at = ""

    def _selected_daq_channels(self):
        return [
            f"ai{index}"
            for index in range(16)
            if hasattr(self.ui, f"ai{index}CheckBox")
            and getattr(self.ui, f"ai{index}CheckBox").isChecked()
        ]

    def _daq_device_name(self):
        daq = getattr(self, "daq", None)
        getter = getattr(daq, "selected_device_name", None)
        if callable(getter):
            return getter()
        return selected_device_name(getattr(self.ui, "daqDeviceComboBox", None))

    def _daq_device_info(self):
        getter = getattr(getattr(self, "daq", None), "selected_device_info", None)
        return getter() if callable(getter) else None

    def _t(self, key, **values):
        if self.translator is None:
            return key.format(**values) if values else key
        return self.translator(key, **values)

    @staticmethod
    def _single_shot(delay_ms, callback):
        from PySide6.QtCore import QTimer

        QTimer.singleShot(delay_ms, callback)
