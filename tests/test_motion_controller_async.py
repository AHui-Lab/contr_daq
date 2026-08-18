import sys
import types

import pytest


class DummySignal:
    def __init__(self, *args, **kwargs):
        self.callback = None

    def connect(self, callback):
        self.callback = callback

    def emit(self, *args, **kwargs):
        if self.callback:
            self.callback(*args, **kwargs)


class DummyQThread:
    def __init__(self, *args, **kwargs):
        self.started = False

    def start(self):
        self.started = True

    def isRunning(self):
        return self.started

    def wait(self, *args, **kwargs):
        pass


qtcore = types.ModuleType("PySide6.QtCore")
qtcore.QThread = DummyQThread
qtcore.QObject = object
qtcore.Signal = DummySignal
pyside6 = types.ModuleType("PySide6")
pyside6.QtCore = qtcore
sys.modules.setdefault("PySide6", pyside6)
sys.modules.setdefault("PySide6.QtCore", qtcore)

from modules.motion.motion_controller import MotionController
from modules.motion.motion_command_thread import MotionCommandThread
from modules.motion.net_amc4xer import MotionProfile, MotionState


class DummyButton:
    def __init__(self):
        self.clicked = DummySignal()
        self.enabled = True

    def setEnabled(self, value):
        self.enabled = value


class DummySpinBox:
    def __init__(self, value):
        self._value = value
        self.enabled = True

    def value(self):
        return self._value

    def setEnabled(self, value):
        self.enabled = value


class DummyComboBox:
    def __init__(self, text):
        self.text = text
        self.enabled = True

    def currentText(self):
        return self.text

    def setEnabled(self, value):
        self.enabled = value


class DummyMotion:
    def __init__(self, *args, **kwargs):
        self.calls = []

    def enable_axis(self, axis):
        self.calls.append(("enable", axis))

    def move_relative(self, axis, direction, length, speed):
        self.calls.append(("move", axis, direction, length, speed))

    def stop_axis(self, axis):
        self.calls.append(("stop", axis))


class DummyMotionWorker:
    created = []

    def __init__(self, motion):
        self.motion = motion
        self.scan_finished = DummySignal()
        self.moves = []
        self.scans = []
        self.stopped = False
        self.started = False
        DummyMotionWorker.created.append(self)

    def start(self):
        self.started = True

    def isRunning(self):
        return self.started

    def submit_move(self, axis, direction, length_pulse, profile):
        self.moves.append((axis, direction, length_pulse, profile))

    def submit_scan(self, *args):
        self.scans.append(args)

    def stop_scan(self):
        self.stopped = True

    def stop_all_axes(self, axes):
        self.stop_axes = list(axes)

    def shutdown(self):
        self.shutdown_called = True


class DummyUi:
    def __init__(self):
        self.xPosButton = DummyButton()
        self.xNegButton = DummyButton()
        self.yPosButton = DummyButton()
        self.yNegButton = DummyButton()
        self.zPosButton = DummyButton()
        self.zNegButton = DummyButton()
        self.RPosButton = DummyButton()
        self.RNegButton = DummyButton()
        self.Forward_circle = DummyButton()
        self.Backward_circle = DummyButton()
        self.Emergency_Stop = DummyButton()
        self.distanceSpinBox = DummySpinBox(2)
        self.Speed_Setting_val = DummySpinBox(3.0)
        self.Axis_choice = DummyComboBox("X")
        self.Circle_times = DummySpinBox(2)
        self.distanceSpinBox_2 = DummySpinBox(4)
        self.Gap_time = DummySpinBox(1)


def test_single_axis_move_runs_in_background_thread(monkeypatch):
    DummyMotionWorker.created = []
    monkeypatch.setattr("modules.motion.motion_controller.NetAMC4XER", DummyMotion)
    monkeypatch.setattr("modules.motion.motion_controller.MotionCommandThread", DummyMotionWorker)

    controller = MotionController(DummyUi())
    controller.move("X", +1)

    assert controller.motion.calls == []
    assert len(DummyMotionWorker.created) == 1
    assert DummyMotionWorker.created[0].moves == [
        (1, +1, 4000, MotionProfile(vo=600, vt=6000, acc_time=135, dec_time=135))
    ]
    assert DummyMotionWorker.created[0].started is True


def test_led_scan_uses_same_background_worker(monkeypatch):
    DummyMotionWorker.created = []
    monkeypatch.setattr("modules.motion.motion_controller.NetAMC4XER", DummyMotion)
    monkeypatch.setattr("modules.motion.motion_controller.MotionCommandThread", DummyMotionWorker)

    controller = MotionController(DummyUi())
    controller.start_scan("X", +1, 4.0)

    assert len(DummyMotionWorker.created) == 1
    scan = DummyMotionWorker.created[0].scans[0]
    assert scan[:4] == (
        1,
        +1,
        8000,
        MotionProfile(vo=600, vt=6000, acc_time=135, dec_time=135),
    )
    assert scan[5] == 10


def test_scan_records_initial_position_before_motion_command():
    class MotionSequence:
        def __init__(self):
            self.states = [
                MotionState(100, 0, 0, 0, 0),
                MotionState(300, 0, 0, 0, 0),
            ]

        def enable_axis(self, axis):
            return 0

        def read_axis_state(self, axis):
            return self.states.pop(0)

        def move_relative(self, axis, direction, length, profile):
            return 0

        def stop_axis(self, axis):
            return 0

    motion = MotionSequence()
    worker = MotionCommandThread(motion)
    worker._scan_running = True
    capture_starts = []
    telemetry = []
    capture_ends = []

    worker._execute_scan(
        axis=1,
        direction=1,
        length_pulse=200,
        profile=MotionProfile(vo=100, vt=1000, acc_time=100, dec_time=100),
        timeout_s=1.0,
        telemetry_interval_ms=2,
        on_capture_start=capture_starts.append,
        on_telemetry=lambda clock, state: telemetry.append((clock, state)),
        on_capture_end=capture_ends.append,
    )

    assert len(capture_starts) == 1
    assert telemetry[0][0] == capture_starts[0]
    assert telemetry[0][1].position == 100
    assert telemetry[-1][1].position == 300
    assert len(capture_ends) == 1


def test_force_hold_z_step_uses_small_positive_relative_move():
    class ForceHoldMotion:
        def __init__(self):
            self.calls = []

        def read_axis_state(self, axis):
            self.calls.append(("read", axis))
            return MotionState(500, 0, 0, 0, 0)

        def enable_axis(self, axis):
            self.calls.append(("enable", axis))
            return 0

        def move_relative(self, axis, direction, length, profile):
            self.calls.append(("move", axis, direction, length, profile))
            return -2

    controller = object.__new__(MotionController)
    controller.motion = ForceHoldMotion()

    applied, detail, position = controller.apply_force_hold_z_step(+1, 0.002)

    assert (applied, detail, position) == (True, "applied", 500)
    move = controller.motion.calls[-1]
    assert move[:4] == ("move", 3, 0, 22)
    assert move[4].vt == pytest.approx(1096)


def test_force_hold_z_step_waits_while_z_axis_is_busy():
    class BusyMotion:
        def read_axis_state(self, axis):
            return MotionState(500, 3, 0, 0, 100)

    controller = object.__new__(MotionController)
    controller.motion = BusyMotion()

    assert controller.apply_force_hold_z_step(-1, 0.002) == (False, "busy", 500)


def test_force_verification_move_has_separate_larger_travel_limit():
    controller = object.__new__(MotionController)
    controller.motion_worker = DummyMotionWorker(None)

    controller.queue_force_verification_z_move(+1, 0.03)

    move = controller.motion_worker.moves[-1]
    assert move[:3] == (3, +1, 329)

    with pytest.raises(ValueError, match="0.05 mm"):
        controller.queue_force_verification_z_move(+1, 0.051)


def test_background_move_finishes_only_after_axis_reports_completion():
    class CompletingMotion:
        def __init__(self):
            self.states = [
                MotionState(100, 0, 0, 0, 0),
                MotionState(100, 1, 0, 0, 0),
                MotionState(122, 0, 0, 0, 0),
            ]

        def read_axis_state(self, axis):
            return self.states.pop(0)

        def enable_axis(self, axis):
            return 0

        def move_relative(self, axis, direction, length, profile):
            return 0

        def stop_axis(self, axis):
            return 0

    worker = MotionCommandThread(CompletingMotion())
    worker._running = True
    worker.msleep = lambda _milliseconds: None
    outcomes = []
    worker.move_finished.connect(lambda ok, detail: outcomes.append((ok, detail)))

    worker._execute_move(
        axis=3,
        direction=1,
        length_pulse=22,
        profile=MotionProfile(vo=100, vt=1000, acc_time=100, dec_time=100),
    )

    assert outcomes == [(True, "move completed")]
