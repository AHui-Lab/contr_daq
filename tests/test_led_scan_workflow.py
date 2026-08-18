import pytest
import re

from modules.motion.net_amc4xer import MotionProfile
from modules.app_runtime import RuntimeStateStore, RuntimeStatus
from modules.recorder.data_recorder import DataRecorder
from modules.workflow.force_hold import ForceHoldConfig, ForceHoldController
from modules.workflow.led_scan import (
    LedScanWorkflow,
    ScanPlan,
    ScanResult,
    ScanWorkflowState,
)


def test_scan_plan_calculates_spatial_resolution_and_constant_speed_distance():
    plan = ScanPlan.build(
        axis="X",
        direction=1,
        led_count=10,
        led_size_mm=1.0,
        speed_mm_s=5.0,
        sample_rate_hz=1000,
        profile=MotionProfile(vo=1000, vt=10000, acc_time=100, dec_time=100),
        pulses_per_mm=2000,
    )

    assert plan.distance_mm == pytest.approx(10.0)
    assert plan.samples_per_led == pytest.approx(200.0)
    assert plan.ramp_distance_mm == pytest.approx(0.55)
    assert plan.constant_speed_distance_mm == pytest.approx(9.45)
    assert plan.triangular_expected is False
    assert plan.motion_telemetry_interval_ms == 10
    assert plan.estimated_motion_samples_per_led == pytest.approx(20.0)


def test_scan_plan_flags_short_high_speed_scan_without_constant_segment():
    plan = ScanPlan.build(
        axis="X",
        direction=-1,
        led_count=5,
        led_size_mm=0.5,
        speed_mm_s=100.0,
        sample_rate_hz=1000,
        profile=MotionProfile(vo=20000, vt=200000, acc_time=1000, dec_time=1000),
        pulses_per_mm=2000,
    )

    assert plan.samples_per_led == pytest.approx(5.0)
    assert plan.triangular_expected is True
    assert plan.constant_speed_distance_mm == 0.0
    assert plan.motion_telemetry_interval_ms == 2
    assert plan.estimated_motion_samples_per_led == pytest.approx(2.5)


def test_actual_motion_quality_flags_missing_constant_speed_segment():
    workflow = object.__new__(LedScanWorkflow)
    workflow._active_plan = ScanPlan.build(
        axis="X",
        direction=1,
        led_count=2,
        led_size_mm=1.0,
        speed_mm_s=10.0,
        sample_rate_hz=1000,
        profile=MotionProfile(vo=2000, vt=20000, acc_time=100, dec_time=100),
        pulses_per_mm=2000,
    )
    workflow.motion = type(
        "Motion",
        (),
        {"AXIS_CONFIG": {"X": {"pulses_per_mm": 2000}}},
    )()
    workflow.recorder = type(
        "Recorder",
        (),
        {"motion_buffer": [[0.0, 0, 2000, 2, 0, 0], [0.01, 10, 0, 4, 0, 0]]},
    )()

    quality = workflow._actual_motion_quality("triangular")

    assert quality["motion_quality_warning"] is True
    assert quality["measured_constant_speed_samples"] == 0
    assert "no measured constant-speed segment" in quality["motion_quality_detail"]


class DummyCheckBox:
    def __init__(self, checked=False, enabled=True):
        self.checked = checked
        self.enabled = enabled
        self.signals_blocked = False

    def isChecked(self):
        return self.checked

    def setChecked(self, checked):
        self.checked = checked

    def isEnabled(self):
        return self.enabled

    def setEnabled(self, enabled):
        self.enabled = enabled

    def blockSignals(self, blocked):
        previous = self.signals_blocked
        self.signals_blocked = blocked
        return previous


class DummyTextControl:
    def __init__(self, text="", enabled=True):
        self._text = text
        self._enabled = enabled
        self.tooltip = ""
        self.style = ""

    def currentText(self):
        return self._text

    def isEnabled(self):
        return self._enabled

    def setEnabled(self, enabled):
        self._enabled = enabled

    def setText(self, text):
        self._text = text

    def setToolTip(self, text):
        self.tooltip = text

    def setStyleSheet(self, style):
        self.style = style


class DummyValueControl(DummyTextControl):
    def __init__(self, value, enabled=True):
        super().__init__(enabled=enabled)
        self._value = value

    def value(self):
        return self._value


def _translator(key, **values):
    if not values:
        return key
    rendered = ",".join(f"{name}={value}" for name, value in sorted(values.items()))
    return f"{key}({rendered})"


def _ready_workflow(plan):
    workflow = object.__new__(LedScanWorkflow)
    workflow.translator = _translator
    workflow.recorder = type("Recorder", (), {"recording": False})()
    workflow.motion = type("Motion", (), {"scan_running": False})()
    workflow.force = type(
        "Force",
        (),
        {"running": True, "latest_vals": [1.0, 1.0, 1.0, 1.0]},
    )()
    workflow.daq = type("DAQ", (), {"resources": None})()
    workflow.ui = type("UI", (), {})()
    workflow.ui.daqDeviceComboBox = DummyTextControl("Dev3")
    workflow.ui.ai0CheckBox = DummyCheckBox(True)
    workflow.ui.scanLoadConfirmButton = DummyCheckBox(True)
    return workflow


def test_preflight_blocks_missing_force_and_channels_before_hardware_start():
    plan = ScanPlan.build(
        axis="X",
        direction=1,
        led_count=10,
        led_size_mm=1.0,
        speed_mm_s=5.0,
        sample_rate_hz=1000,
        profile=MotionProfile(vo=1000, vt=10000, acc_time=100, dec_time=100),
        pulses_per_mm=2000,
    )
    workflow = _ready_workflow(plan)
    workflow.force.running = False
    workflow.force.latest_vals = None
    workflow.ui.ai0CheckBox.checked = False

    readiness = workflow._evaluate_readiness(plan)

    assert readiness.can_start is False
    assert "scan.force_required" in readiness.blockers
    assert "scan.channels_required" in readiness.blockers


def test_preflight_allows_warning_plan_when_required_streams_are_ready():
    plan = ScanPlan.build(
        axis="X",
        direction=1,
        led_count=2,
        led_size_mm=0.5,
        speed_mm_s=100.0,
        sample_rate_hz=1000,
        profile=MotionProfile(vo=20000, vt=200000, acc_time=1000, dec_time=1000),
        pulses_per_mm=2000,
    )
    workflow = _ready_workflow(plan)

    readiness = workflow._evaluate_readiness(plan)

    assert readiness.can_start is True
    assert "scan.triangular" in readiness.warnings
    assert any(message.startswith("scan.low_resolution") for message in readiness.warnings)


def test_preflight_warns_when_motion_position_resolution_is_too_low():
    plan = ScanPlan.build(
        axis="X",
        direction=1,
        led_count=10,
        led_size_mm=0.1,
        speed_mm_s=100.0,
        sample_rate_hz=100000,
        profile=MotionProfile(vo=20000, vt=200000, acc_time=1000, dec_time=1000),
        pulses_per_mm=2000,
    )
    workflow = _ready_workflow(plan)

    readiness = workflow._evaluate_readiness(plan)

    assert plan.estimated_motion_samples_per_led == pytest.approx(0.5)
    assert any(
        message.startswith("scan.low_motion_resolution")
        for message in readiness.warnings
    )


def test_preflight_requires_explicit_operator_load_confirmation():
    plan = ScanPlan.build(
        axis="X",
        direction=1,
        led_count=10,
        led_size_mm=1.0,
        speed_mm_s=5.0,
        sample_rate_hz=1000,
        profile=MotionProfile(vo=1000, vt=10000, acc_time=100, dec_time=100),
        pulses_per_mm=2000,
    )
    workflow = _ready_workflow(plan)
    workflow.ui.scanLoadConfirmButton.checked = False

    readiness = workflow._evaluate_readiness(plan)

    assert readiness.can_start is False
    assert "scan.load_confirmation_required" in readiness.blockers


def test_force_hold_preflight_blocks_z_scan_axis(monkeypatch):
    plan = ScanPlan.build(
        axis="Z",
        direction=1,
        led_count=10,
        led_size_mm=0.1,
        speed_mm_s=1.0,
        sample_rate_hz=1000,
        profile=MotionProfile(vo=100, vt=1000, acc_time=100, dec_time=100),
        pulses_per_mm=1000,
    )
    workflow = _ready_workflow(plan)
    workflow.ui.forceHoldEnableCheckBox = DummyCheckBox(True)
    workflow.ui.forceHoldToleranceSpinBox = DummyValueControl(0.2)
    workflow.ui.forceHoldStepSpinBox = DummyValueControl(0.002)
    workflow._confirmed_force_n = 10.0
    workflow.force.latest_force = 10.0
    workflow.force.force_control_snapshot = lambda window_s: (10.0, 5.0)
    monkeypatch.setattr("modules.workflow.led_scan.time.perf_counter", lambda: 5.0)

    readiness = workflow._evaluate_readiness(plan)

    assert "scan.force_hold_z_axis" in readiness.blockers


def test_force_hold_accepts_negative_individual_channels_when_total_is_positive(
    monkeypatch,
):
    plan = ScanPlan.build(
        axis="Y",
        direction=1,
        led_count=10,
        led_size_mm=1.0,
        speed_mm_s=5.0,
        sample_rate_hz=1000,
        profile=MotionProfile(vo=1000, vt=10000, acc_time=100, dec_time=100),
        pulses_per_mm=2000,
    )
    workflow = _ready_workflow(plan)
    workflow.ui.forceHoldEnableCheckBox = DummyCheckBox(True)
    workflow.ui.forceHoldToleranceSpinBox = DummyValueControl(0.2)
    workflow.ui.forceHoldStepSpinBox = DummyValueControl(0.002)
    workflow.force.latest_vals = [-2.0, 4.0, -1.0, 9.0]
    workflow.force.latest_force = 10.0
    workflow.force.force_control_snapshot = lambda window_s: (10.0, 5.0)
    workflow._confirmed_force_n = 10.0
    monkeypatch.setattr("modules.workflow.led_scan.time.perf_counter", lambda: 5.0)

    readiness = workflow._evaluate_readiness(plan)

    assert readiness.can_start is True
    assert readiness.blockers == ()


def test_force_derivative_ui_builds_fixed_period_config_and_force_window():
    workflow = object.__new__(LedScanWorkflow)
    workflow.ui = type("UI", (), {})()
    workflow.ui.forceHoldEnableCheckBox = DummyCheckBox(True)
    workflow.ui.forceHoldIntervalSpinBox = DummyValueControl(0.05)
    workflow.ui.forceHoldToleranceSpinBox = DummyValueControl(1.5)
    workflow.ui.forceHoldStepSpinBox = DummyValueControl(0.004)
    workflow.config = type(
        "Config",
        (),
        {
            "force_derivative_measurement_window_s": 0.02,
            "force_derivative_max_offset_mm": 0.05,
            "force_derivative_max_error_n": 2.0,
        },
    )()
    workflow._force_hold = ForceHoldController()
    requested_windows = []
    workflow.force = type(
        "Force",
        (),
        {
            "latest_force": 10.0,
            "force_control_snapshot": lambda self, window_s: (
                requested_windows.append(window_s) or (10.0, 5.0)
            ),
        },
    )()

    config = workflow._force_hold_config()
    measured, sample_time = workflow._force_snapshot()

    assert config.derivative_interval_s == pytest.approx(0.05)
    assert config.derivative_deadband_n_s == pytest.approx(1.5)
    assert config.z_step_mm == pytest.approx(0.004)
    assert config.measurement_window_s == pytest.approx(0.02)
    assert config.signal_timeout_s == pytest.approx(0.15)
    assert config.max_offset_mm == pytest.approx(0.05)
    assert config.hard_error_n == pytest.approx(2.0)
    assert requested_windows == pytest.approx([0.02])
    assert (measured, sample_time) == pytest.approx((10.0, 5.0))


def test_force_hold_status_explains_each_enablement_step():
    workflow = object.__new__(LedScanWorkflow)
    workflow.translator = _translator
    workflow._force_hold = ForceHoldController()
    workflow._confirmed_force_n = None
    workflow.ui = type("UI", (), {})()
    workflow.ui.forceHoldStatusLabel = DummyTextControl()
    workflow.ui.forceHoldEnableCheckBox = DummyCheckBox(True)
    workflow.ui.forceHoldIntervalSpinBox = DummyValueControl(0.1)
    workflow.ui.forceHoldToleranceSpinBox = DummyValueControl(0.2)
    workflow.ui.forceHoldStepSpinBox = DummyValueControl(0.002)
    workflow.ui.scanLoadConfirmButton = DummyCheckBox(False)
    workflow.force = type(
        "Force",
        (),
        {"running": False, "latest_vals": None, "latest_force": 0.0},
    )()

    workflow._update_force_hold_status()
    assert workflow.ui.forceHoldStatus == "waiting_force"
    assert workflow.ui.forceHoldStatusLabel._text == "force_hold.status_start_force"

    workflow.force.running = True
    workflow.force.latest_vals = [2.5, 2.5, 2.5, 2.5]
    workflow._update_force_hold_status()
    assert workflow.ui.forceHoldStatus == "waiting_confirmation"
    assert workflow.ui.forceHoldStatusLabel._text == "force_hold.status_confirm"

    workflow.ui.scanLoadConfirmButton.checked = True
    workflow._confirmed_force_n = 10.0
    workflow.force.latest_force = 10.0
    workflow._update_force_hold_status()
    assert workflow.ui.forceHoldStatus == "ready"
    assert workflow.ui.forceHoldStatusLabel._text.startswith(
        "force_hold.status_ready"
    )


def test_force_hold_tick_applies_derivative_direction_and_records_event():
    workflow = object.__new__(LedScanWorkflow)
    workflow.translator = _translator
    workflow._force_hold = ForceHoldController()
    workflow._force_hold.arm(
        ForceHoldConfig(enabled=True),
        target_force_n=10.0,
        now=1.0,
    )
    force_clock = [1.20]
    force_value = [9.5]
    workflow._force_snapshot = lambda: (force_value[0], force_clock[0])
    moves = []
    workflow.motion = type(
        "Motion",
        (),
        {
            "apply_force_hold_z_step": lambda self, direction, step: (
                moves.append((direction, step)) or (True, "applied", 1234)
            ),
            "stop_force_hold_z": lambda self: None,
        },
    )()
    events = []
    workflow.recorder = type(
        "Recorder",
        (),
        {"add_force_hold_event": lambda self, **values: events.append(values)},
    )()

    workflow._on_force_hold_tick(1.20)
    force_clock[0] = 1.30
    force_value[0] = 9.7
    workflow._on_force_hold_tick(1.30)

    assert moves == [(-1, pytest.approx(0.0005))]
    assert events[0]["status"] == "applied"
    assert events[0]["derivative_n_s"] == pytest.approx(2.0)
    assert events[0]["accumulated_z_mm"] == pytest.approx(-0.0005)


def test_force_hold_tick_aborts_scan_when_force_signal_is_stale():
    workflow = object.__new__(LedScanWorkflow)
    workflow.translator = _translator
    workflow._force_hold = ForceHoldController()
    workflow._force_hold.arm(
        ForceHoldConfig(enabled=True),
        target_force_n=10.0,
        now=1.0,
    )
    workflow._force_snapshot = lambda: (10.0, 1.0)
    stops = []
    workflow.motion = type(
        "Motion",
        (),
        {"stop_force_hold_z": lambda self: stops.append(True)},
    )()
    events = []
    workflow.recorder = type(
        "Recorder",
        (),
        {"add_force_hold_event": lambda self, **values: events.append(values)},
    )()

    with pytest.raises(RuntimeError, match="scan.force_hold_abort"):
        workflow._on_force_hold_tick(1.5)

    assert stops == [True]
    assert events[0]["status"] == "abort:stale_signal"


def test_scan_interlock_restores_previous_enabled_states_and_keeps_stop_live():
    workflow = object.__new__(LedScanWorkflow)
    workflow._control_enabled_snapshot = {}
    workflow._controls_locked = False
    workflow.ui = type("UI", (), {})()
    workflow.ui.Axis_choice = DummyTextControl(enabled=True)
    workflow.ui.startStopButton = DummyTextControl(enabled=False)
    workflow.ui.Forward_circle = DummyTextControl(enabled=True)
    workflow.ui.Emergency_Stop = DummyTextControl(enabled=True)
    workflow.ui.ai0CheckBox = DummyTextControl(enabled=True)

    workflow._set_controls_locked(True)

    assert workflow.ui.Axis_choice.isEnabled() is False
    assert workflow.ui.startStopButton.isEnabled() is False
    assert workflow.ui.Forward_circle.isEnabled() is False
    assert workflow.ui.ai0CheckBox.isEnabled() is False
    assert workflow.ui.Emergency_Stop.isEnabled() is True

    workflow.ui.Axis_choice.setEnabled(True)
    workflow._set_controls_locked(True)
    assert workflow.ui.Axis_choice.isEnabled() is False

    workflow._set_controls_locked(False)
    assert workflow.ui.Axis_choice.isEnabled() is True
    assert workflow.ui.startStopButton.isEnabled() is False
    assert workflow.ui.Forward_circle.isEnabled() is True


def test_incomplete_saved_result_is_reported_as_error():
    workflow = object.__new__(LedScanWorkflow)
    workflow.translator = _translator
    workflow.runtime = RuntimeStateStore()
    workflow.ui = type("UI", (), {})()
    workflow.ui.scanQualityLabel = DummyTextControl()
    workflow.recorder = type(
        "Recorder",
        (),
        {
            "group_id": 7,
            "save_dir": "data",
            "update_metadata": lambda self, values: None,
            "stop": lambda self: {"daq": "data/group7_daq.csv"},
        },
    )()
    workflow._actual_motion_quality = lambda detail: {
        "motion_quality_warning": False,
        "motion_quality_detail": "ok",
    }
    workflow._finish_session = lambda: None
    workflow.refresh_readiness = lambda preserve_result=True: None
    workflow._last_result = None
    workflow._last_failure = None

    workflow._finalize(True, "completed")

    assert isinstance(workflow._last_result, ScanResult)
    assert workflow._last_result.outcome == "error"
    assert workflow._last_result.missing_streams == ("force",)
    assert workflow.ui.scanWorkflowPhase == "error"
    assert workflow.runtime.get("scan").status is RuntimeStatus.ERROR


def test_save_failure_releases_session_and_keeps_actionable_error():
    workflow = object.__new__(LedScanWorkflow)
    workflow.translator = _translator
    workflow.runtime = RuntimeStateStore()
    workflow.ui = type("UI", (), {})()
    workflow.ui.scanQualityLabel = DummyTextControl()
    workflow.recorder = type(
        "Recorder",
        (),
        {
            "update_metadata": lambda self, values: None,
            "stop": lambda self: (_ for _ in ()).throw(PermissionError("read-only")),
        },
    )()
    workflow._actual_motion_quality = lambda detail: {
        "motion_quality_warning": False,
        "motion_quality_detail": "ok",
    }
    finished = []
    workflow._finish_session = lambda: finished.append(True)
    workflow._last_failure = None

    workflow._finalize(True, "completed")

    assert finished == [True]
    assert workflow.ui.scanWorkflowPhase == "error"
    assert "scan.save_failed" in workflow._last_failure
    assert workflow.runtime.get("scan").status is RuntimeStatus.ERROR
    assert workflow.runtime.get("recording").status is RuntimeStatus.ERROR


def test_running_scan_requests_emergency_stop_when_daq_stream_is_lost():
    workflow = object.__new__(LedScanWorkflow)
    workflow.translator = _translator
    workflow.runtime = RuntimeStateStore()
    workflow.state = ScanWorkflowState.RUNNING
    workflow._abort_requested = False
    workflow._capture_started = True
    workflow.ui = type("UI", (), {})()
    workflow.ui.scanQualityLabel = DummyTextControl()
    workflow.daq = type("DAQ", (), {"thread": None})()
    workflow.force = type("Force", (), {"running": True})()
    workflow.recorder = type("Recorder", (), {"recording": True})()
    stops = []
    workflow.motion = type(
        "Motion",
        (),
        {"emergency_stop": lambda self: stops.append(True)},
    )()

    workflow._monitor_active_streams()
    workflow._monitor_active_streams()

    assert stops == [True]
    assert workflow._abort_requested is True
    assert "scan.daq_lost" in workflow.ui.scanReadinessSummaryText
    assert workflow.runtime.get("scan").status is RuntimeStatus.WARNING


def test_duplicate_motion_finished_signal_is_ignored_while_saving():
    workflow = object.__new__(LedScanWorkflow)
    workflow.state = ScanWorkflowState.SAVING
    scheduled = []
    workflow._single_shot = lambda delay, callback: scheduled.append((delay, callback))

    workflow._on_motion_finished(True, "completed")

    assert scheduled == []


def test_capture_summary_metadata_records_duration_and_stream_rows():
    workflow = object.__new__(LedScanWorkflow)
    workflow.recorder = type(
        "Recorder",
        (),
        {
            "start_time": 10.0,
            "capture_end_clock": 12.5,
            "daq_buffer": [1, 2, 3],
            "force_buffer": [1, 2],
            "motion_buffer": [1],
        },
    )()

    metadata = workflow._capture_summary_metadata()

    assert metadata["capture_duration_s"] == pytest.approx(2.5)
    assert metadata["data_rows"] == {
        "daq": 3,
        "force": 2,
        "force_hold": 0,
        "motion": 1,
        "spatial": 0,
        "led_summary": 0,
    }
    assert metadata["expected_streams"] == ["daq", "force"]


def test_load_confirmation_is_reset_for_the_next_scan():
    workflow = object.__new__(LedScanWorkflow)
    workflow.ui = type("UI", (), {})()
    workflow.ui.scanLoadConfirmButton = DummyCheckBox(True)
    workflow._confirmed_force_n = 8.5
    workflow._load_confirmed_at = "2026-07-14T12:00:00+08:00"

    workflow._reset_load_confirmation()

    assert workflow.ui.scanLoadConfirmButton.isChecked() is False
    assert workflow.ui.scanLoadConfirmed is False
    assert workflow._confirmed_force_n is None
    assert workflow._load_confirmed_at == ""


def test_load_confirmation_uses_filtered_force_snapshot():
    workflow = object.__new__(LedScanWorkflow)
    workflow.state = ScanWorkflowState.IDLE
    workflow.force = type("Force", (), {"latest_force": 99.0})()
    workflow.ui = type("UI", (), {})()
    workflow._force_snapshot = lambda: (8.25, 12.0)
    workflow._set_runtime_scan = lambda status: None
    workflow.refresh_readiness = lambda preserve_result: None

    workflow._on_load_confirmation_changed(True)

    assert workflow._confirmed_force_n == pytest.approx(8.25)
    assert workflow.ui.scanLoadConfirmed is True


def test_finalize_saves_position_mapped_led_outputs(tmp_path):
    class State:
        def __init__(self, position, speed, run_state):
            self.position = position
            self.speed = speed
            self.run_state = run_state
            self.io_state = 0
            self.emergency = 0

    recorder = DataRecorder(save_dir=tmp_path)
    recorder.start(start_monotonic=10.0)
    recorder.add_daq_chunk(
        rows=[[float(index)] for index in range(101)],
        sample_rate=100,
        channels=["ai0"],
        source_start_monotonic=10.0,
    )
    recorder.add_force_chunk(
        rows=[[1.0, 1.0, 1.0, 1.0] for _ in range(11)],
        sample_rate=10,
        source_start_monotonic=10.0,
    )
    for index in range(11):
        recorder.add_motion_sample(
            10.0 + index / 10.0,
            State(
                position=index * 100,
                speed=1000 if 0 < index < 10 else 0,
                run_state=3 if 0 < index < 10 else 0,
            ),
        )
    recorder.set_capture_end(11.0)

    workflow = object.__new__(LedScanWorkflow)
    workflow.translator = _translator
    workflow.runtime = RuntimeStateStore()
    workflow.ui = type("UI", (), {})()
    workflow.ui.scanQualityLabel = DummyTextControl()
    workflow.recorder = recorder
    workflow.motion = type(
        "Motion",
        (),
        {"AXIS_CONFIG": {"X": {"pulses_per_mm": 1000}}},
    )()
    workflow._active_plan = ScanPlan.build(
        axis="X",
        direction=1,
        led_count=2,
        led_size_mm=0.5,
        speed_mm_s=1.0,
        sample_rate_hz=100,
        profile=MotionProfile(vo=500, vt=1000, acc_time=100, dec_time=100),
        pulses_per_mm=1000,
    )
    workflow._finish_session = lambda: None
    workflow.refresh_readiness = lambda preserve_result=True: None
    workflow._last_result = None
    workflow._last_failure = None

    workflow._finalize(True, "completed")

    assert workflow._last_result.outcome == "completed"
    assert workflow._last_result.led_bins_covered == 2
    assert workflow._last_result.led_bins_expected == 2
    assert workflow._last_result.minimum_samples_per_led >= 50
    assert "spatial" in workflow._last_result.paths
    assert "led_summary" in workflow._last_result.paths


def test_scan_metadata_contains_run_identity_and_operator(tmp_path):
    plan = ScanPlan.build(
        axis="X",
        direction=1,
        led_count=2,
        led_size_mm=0.5,
        speed_mm_s=1.0,
        sample_rate_hz=100,
        profile=MotionProfile(vo=500, vt=1000, acc_time=100, dec_time=100),
        pulses_per_mm=1000,
    )
    workflow = object.__new__(LedScanWorkflow)
    workflow.config = type(
        "Config",
        (),
        {"operator_name": "Operator A"},
    )()
    workflow.translator = type("Translator", (), {"language": "en"})()
    workflow.recorder = type("Recorder", (), {"save_dir": str(tmp_path)})()
    workflow.ui = type("UI", (), {})()
    workflow.ui.daqDeviceComboBox = DummyTextControl("Dev3")
    workflow.ui.ai0CheckBox = DummyCheckBox(True)
    workflow.ui.scanLoadConfirmButton = DummyCheckBox(True)
    workflow.force = type(
        "Force",
        (),
        {
            "active_mode": "analog",
            "_force_device": lambda self: "Dev4",
        },
    )()
    workflow._confirmed_force_n = 8.5
    workflow._load_confirmed_at = "2026-07-15T00:00:00+08:00"

    metadata = workflow._scan_metadata(plan)

    assert re.fullmatch(r"R\d{6}-\d{6}-\d{3}", metadata["scan_id"])
    assert metadata["operator_name"] == "Operator A"
    assert metadata["output_directory"] == str(tmp_path.resolve())
    assert metadata["daq_device"] == "Dev3"
    assert metadata["daq_channels"] == ["ai0"]
    assert metadata["force_device"] == "Dev4"
    assert metadata["operator_load_confirmed"] is True


def test_scan_metadata_prefers_active_acquisition_snapshots(tmp_path):
    plan = ScanPlan.build(
        axis="X",
        direction=1,
        led_count=1,
        led_size_mm=1.0,
        speed_mm_s=1.0,
        sample_rate_hz=500,
        profile=MotionProfile(vo=500, vt=1000, acc_time=100, dec_time=100),
        pulses_per_mm=1000,
    )
    workflow = object.__new__(LedScanWorkflow)
    workflow.config = type("Config", (), {"operator_name": ""})()
    workflow.translator = type("Translator", (), {"language": "en"})()
    workflow.recorder = type("Recorder", (), {"save_dir": str(tmp_path)})()
    workflow.ui = type("UI", (), {})()
    workflow.ui.daqDeviceComboBox = DummyTextControl("DevUi")
    workflow.ui.ai0CheckBox = DummyCheckBox(True)
    workflow.ui.scanLoadConfirmButton = DummyCheckBox(True)
    workflow.daq = type(
        "DAQ",
        (),
        {
            "active_configuration_metadata": lambda self: {
                "daq_device": "DevActive",
                "daq_channels": ["ai0", "ai1"],
                "daq_sample_rate_hz": 5000,
            }
        },
    )()
    workflow.force = type(
        "Force",
        (),
        {
            "active_mode": "analog",
            "_force_device": lambda self: "DevForceUi",
            "active_configuration_metadata": lambda self: {
                "force_device": "DevForceActive",
                "force_sample_rate_hz": 2000,
            },
        },
    )()
    workflow._confirmed_force_n = 5.0
    workflow._load_confirmed_at = "2026-07-15T00:00:00+08:00"

    metadata = workflow._scan_metadata(plan)

    assert metadata["daq_device"] == "DevActive"
    assert metadata["daq_channels"] == ["ai0", "ai1"]
    assert metadata["daq_sample_rate_hz"] == 5000
    assert metadata["force_device"] == "DevForceActive"
    assert metadata["force_sample_rate_hz"] == 2000
