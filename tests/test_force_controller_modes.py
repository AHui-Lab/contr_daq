import sys
import types

import pytest


qtcore = types.ModuleType("PySide6.QtCore")


class DummySignal:
    def __init__(self):
        self.callback = None

    def connect(self, callback):
        self.callback = callback


class DummyThread:
    CHANNEL_COUNT = 4
    created = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.data_ready = DummySignal()
        self.chunk_ready = DummySignal()
        self.started_ok = DummySignal()
        self.started = False
        self.stopped = False
        DummyThread.created.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def isRunning(self):
        return self.started and not self.stopped


qtcore.QThread = object
qtcore.QObject = object
qtcore.Signal = lambda *args, **kwargs: DummySignal()

pyside6 = types.ModuleType("PySide6")
pyside6.QtCore = qtcore
sys.modules.setdefault("PySide6", pyside6)
sys.modules.setdefault("PySide6.QtCore", qtcore)

force_thread_module = types.ModuleType("modules.force.force_thread")
force_thread_module.ForceThread = DummyThread
sys.modules["modules.force.force_thread"] = force_thread_module

force_plot_module = types.ModuleType("modules.force.force_plot")


class DummyForcePlot:
    def __init__(self, *args, **kwargs):
        self.points = []
        self.samples = []

    def clear(self):
        self.points.clear()

    def add_point(self, point):
        self.points.append(point)

    def add_samples(self, points, sample_rate):
        self.samples.append((list(points), sample_rate))


force_plot_module.ForcePlot = DummyForcePlot
sys.modules["modules.force.force_plot"] = force_plot_module

from modules.force.force_controller import ForceController


class DummyButton:
    def __init__(self):
        self.clicked = DummySignal()
        self.text = ""

    def setText(self, text):
        self.text = text


class DummyComboBox:
    def __init__(self, text):
        self.text = text

    def currentText(self):
        return self.text


class DummySpinBox:
    def __init__(self, value):
        self._value = value

    def value(self):
        return self._value

    def setValue(self, value):
        self._value = value


class DummyLabel:
    def __init__(self):
        self.text = ""

    def setText(self, text):
        self.text = text


class DummyPlotWidget:
    def layout(self):
        return None


class DummyUi:
    def __init__(self):
        self.forceStartButton = DummyButton()
        self.forceZeroButton = DummyButton()
        self.recorderStartButton = DummyButton()
        self.recorderStopButton = DummyButton()
        self.forcePlotWidget = DummyPlotWidget()
        self.totalForceLabel = DummyLabel()
        self.Force1_Label = DummyLabel()
        self.Force2_Label = DummyLabel()
        self.Force3_Label = DummyLabel()
        self.Force4_Label = DummyLabel()
        self.forceModeComboBox = DummyComboBox("Analog Voltage")
        self.forceDeviceComboBox = DummyComboBox("DevForce")
        self.forceSampleRateSpinBox = DummySpinBox(2000)
        self.forceTerminalConfigComboBox = DummyComboBox("DIFFERENTIAL")
        self.forceVoltageRangeComboBox = DummyComboBox("0-10V")
        self.forceFullScaleSpinBox = DummySpinBox(98.0665)


class DummyRecorder:
    def __init__(self):
        self.recording = True
        self.force_chunks = []

    def add_force_chunk(self, rows, sample_rate):
        self.force_chunks.append((rows.tolist(), sample_rate))


def test_start_analog_force_uses_independent_force_device_settings(monkeypatch):
    DummyThread.created = []
    monkeypatch.setattr("modules.force.force_controller.AnalogForceThread", DummyThread)

    controller = ForceController(DummyUi())
    controller.start()

    assert DummyThread.created[0].kwargs == {
        "device": "DevForce",
        "sample_rate": 2000,
        "terminal_config": "DIFFERENTIAL",
        "force_config": controller._analog_config(),
        "output_rate": 400,
        "median_window": 3,
        "average_window_ms": 20,
        "force_rows_callback": controller._on_analog_force_chunk_from_thread,
    }


def test_analog_force_data_is_converted_from_voltage_to_newtons(monkeypatch):
    DummyThread.created = []
    monkeypatch.setattr("modules.force.force_controller.AnalogForceThread", DummyThread)
    ui = DummyUi()
    controller = ForceController(ui)
    controller.start()

    controller.on_data(0.0, [1.0, 2.0, 3.0, 4.0])

    assert controller.latest_vals.tolist() == pytest.approx(
        [9.80665, 19.6133, 29.41995, 39.2266]
    )
    assert controller.latest_force == pytest.approx(98.0665)


def test_analog_force_chunk_records_converted_newtons(monkeypatch):
    DummyThread.created = []
    monkeypatch.setattr("modules.force.force_controller.AnalogForceThread", DummyThread)
    recorder = DummyRecorder()
    controller = ForceController(DummyUi(), recorder=recorder)
    controller.start()

    controller.on_analog_chunk(
        [
            [1.0, 2.0, 3.0, 4.0],
            [1.0, 2.0, 3.0, 4.0],
            [1.0, 2.0, 3.0, 4.0],
            [1.0, 2.0, 3.0, 4.0],
            [1.0, 2.0, 3.0, 4.0],
        ]
    )

    rows, sample_rate = recorder.force_chunks[0]
    assert rows[0] == pytest.approx([9.80665, 19.6133, 29.41995, 39.2266])
    assert sample_rate == 400
    assert controller.latest_vals.tolist() == pytest.approx(
        [9.80665, 19.6133, 29.41995, 39.2266]
    )
    assert controller.latest_force == pytest.approx(98.0665)


def test_analog_force_chunk_filters_spike_before_400hz_output(monkeypatch):
    DummyThread.created = []
    monkeypatch.setattr("modules.force.force_controller.AnalogForceThread", DummyThread)
    recorder = DummyRecorder()
    controller = ForceController(DummyUi(), recorder=recorder)
    controller.start()

    controller.on_analog_chunk(
        [
            [1.0, 1.0, 1.0, 1.0],
            [1.0, 1.0, 1.0, 1.0],
            [10.0, 10.0, 10.0, 10.0],
            [1.0, 1.0, 1.0, 1.0],
            [1.0, 1.0, 1.0, 1.0],
        ]
    )

    rows, sample_rate = recorder.force_chunks[0]
    assert rows[0] == pytest.approx([9.80665, 9.80665, 9.80665, 9.80665])
    assert sample_rate == 400
