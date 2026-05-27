import sys
import types


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
        self.loop_finished = DummySignal()
        self.moves = []
        self.loops = []
        self.stopped = False
        self.started = False
        DummyMotionWorker.created.append(self)

    def start(self):
        self.started = True

    def isRunning(self):
        return self.started

    def submit_move(self, axis, direction, length_pulse, speed):
        self.moves.append((axis, direction, length_pulse, speed))

    def submit_loop(self, axis, direction, length_pulse, speed, times, gap):
        self.loops.append((axis, direction, length_pulse, speed, times, gap))

    def stop_loop(self):
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
        self.Speed_Setting_val = DummySpinBox(3)
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
    assert DummyMotionWorker.created[0].moves == [(1, +1, 4000, 3)]
    assert DummyMotionWorker.created[0].started is True


def test_loop_motion_uses_same_background_worker(monkeypatch):
    DummyMotionWorker.created = []
    monkeypatch.setattr("modules.motion.motion_controller.NetAMC4XER", DummyMotion)
    monkeypatch.setattr("modules.motion.motion_controller.MotionCommandThread", DummyMotionWorker)

    controller = MotionController(DummyUi())
    controller.start_loop(+1)

    assert len(DummyMotionWorker.created) == 1
    assert DummyMotionWorker.created[0].loops == [(1, +1, 8000, 3, 2, 1)]
