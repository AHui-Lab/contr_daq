import sys
import types

import pytest

from modules.app_config import AppConfig


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
        self.force_chunk_starts = []
        self.force_voltage_chunks = []
        self.start_calls = []
        self.metadata = {}

    def start(self, metadata=None, start_monotonic=None):
        self.start_calls.append((metadata, start_monotonic))
        self.recording = True
        return True

    def stop(self):
        self.recording = False

    def update_metadata(self, values):
        self.metadata.update(values)

    def add_force_chunk(self, rows, sample_rate, source_start_monotonic=None):
        self.force_chunks.append((rows.tolist(), sample_rate))
        self.force_chunk_starts.append(source_start_monotonic)

    def add_force_voltage_chunk(self, rows, sample_rate, source_start_monotonic=None):
        self.force_voltage_chunks.append(
            (rows.tolist(), sample_rate, source_start_monotonic)
        )


def test_start_analog_force_uses_independent_force_device_settings(monkeypatch):
    DummyThread.created = []
    monkeypatch.setattr("modules.force.force_controller.AnalogForceThread", DummyThread)

    controller = ForceController(DummyUi())
    controller.start()

    assert DummyThread.created[0].kwargs == {
        "device": "DevForce",
        "channels": ["ai0", "ai1", "ai2", "ai3"],
        "sample_rate": 2000,
        "terminal_config": "DIFFERENTIAL",
        "input_min_voltage": -10.0,
        "input_max_voltage": 10.0,
        "force_config": controller._analog_config(),
        "output_rate": 400,
        "median_window": 3,
        "average_window_ms": 5,
        "force_rows_callback": controller._on_analog_force_chunk_from_thread,
        "voltage_rows_callback": controller._on_analog_voltage_chunk_from_thread,
    }


def test_serial_force_uses_port_and_baud_from_settings():
    DummyThread.created = []
    ui = DummyUi()
    ui.forceModeComboBox.text = "Serial Modbus"
    config = AppConfig(force_serial_port="COM7", force_serial_baudrate=19200)

    controller = ForceController(ui, config=config)
    controller.start()

    assert DummyThread.created[0].kwargs == {"port": "COM7", "baudrate": 19200}
    assert controller.active_config.serial_port == "COM7"
    assert controller.active_config.baud_rate == 19200


def test_manual_recording_uses_monotonic_clock_and_force_metadata(monkeypatch):
    DummyThread.created = []
    monkeypatch.setattr("modules.force.force_controller.AnalogForceThread", DummyThread)
    monkeypatch.setattr("modules.force.force_controller.time.perf_counter", lambda: 42.5)
    recorder = DummyRecorder()
    recorder.recording = False
    controller = ForceController(DummyUi(), recorder=recorder)
    controller.start()

    controller.start_record()

    assert recorder.start_calls == [(None, 42.5)]
    assert recorder.metadata["force_voltage_range"] == "0-10V"
    assert recorder.metadata["force_daq_input_min_v"] == -10.0
    assert recorder.metadata["force_daq_input_max_v"] == 10.0


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


def test_running_force_conversion_uses_the_immutable_start_snapshot(monkeypatch):
    DummyThread.created = []
    monkeypatch.setattr("modules.force.force_controller.AnalogForceThread", DummyThread)
    ui = DummyUi()
    controller = ForceController(ui)
    controller.start()

    ui.forceVoltageRangeComboBox.text = "0-5V"
    ui.forceFullScaleSpinBox.setValue(10.0)
    controller.on_data(0.0, [1.0, 1.0, 1.0, 1.0])

    assert controller.active_config.voltage_range == "0-10V"
    assert controller.active_config.full_scale_force_n == pytest.approx(98.0665)
    assert controller.latest_vals.tolist() == pytest.approx([9.80665] * 4)


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


def test_analog_force_chunk_uses_thread_sample_clock_timing(monkeypatch):
    DummyThread.created = []
    monkeypatch.setattr("modules.force.force_controller.AnalogForceThread", DummyThread)
    recorder = DummyRecorder()
    controller = ForceController(DummyUi(), recorder=recorder)
    controller.start()
    controller.thread.force_output_sample_rate = 400.0
    controller.thread.force_chunk_start_monotonic = 123.25

    controller._on_analog_force_chunk_from_thread([[1.0, 2.0, 3.0, 4.0]])

    assert recorder.force_chunks[0][1] == 400.0
    assert recorder.force_chunk_starts[0] == 123.25


def test_raw_force_voltage_is_kept_for_calibration(monkeypatch):
    DummyThread.created = []
    monkeypatch.setattr("modules.force.force_controller.AnalogForceThread", DummyThread)
    recorder = DummyRecorder()
    controller = ForceController(DummyUi(), recorder=recorder)
    controller.start()
    controller.thread.sample_rate = 2000
    controller.thread.voltage_chunk_start_monotonic = 321.5

    controller._on_analog_voltage_chunk_from_thread(
        [[0.1, 0.2, 0.3, 0.4], [0.2, 0.3, 0.4, 0.5]]
    )

    assert controller.latest_voltage_vals.tolist() == [0.2, 0.3, 0.4, 0.5]
    assert recorder.force_voltage_chunks[0] == (
        [[0.1, 0.2, 0.3, 0.4], [0.2, 0.3, 0.4, 0.5]],
        2000.0,
        321.5,
    )


def test_force_voltage_diagnostic_flags_range_and_clipping_risks():
    config = ForceController(DummyUi())._analog_config()

    assert ForceController._voltage_warning_for_rows([[0.0, 1.0, 2.0, 3.0]], config) == ""
    assert "outside the selected transmitter range" in (
        ForceController._voltage_warning_for_rows([[-0.5, 1.0, 2.0, 3.0]], config)
    )
    assert "clipping may occur" in (
        ForceController._voltage_warning_for_rows([[9.9, 1.0, 2.0, 3.0]], config)
    )


def test_force_control_snapshot_uses_recent_median(monkeypatch):
    DummyThread.created = []
    monkeypatch.setattr("modules.force.force_controller.AnalogForceThread", DummyThread)
    recorder = DummyRecorder()
    controller = ForceController(DummyUi(), recorder=recorder)
    controller.start()
    controller.thread.force_output_sample_rate = 100.0
    controller.thread.force_chunk_start_monotonic = 10.0

    controller._on_analog_force_chunk_from_thread(
        [
            [1.0, 1.0, 1.0, 1.0],
            [1.0, 1.0, 1.0, 1.0],
            [10.0, 10.0, 10.0, 10.0],
        ]
    )

    measured, sample_time = controller.force_control_snapshot(window_s=0.05)

    assert measured == pytest.approx(4.0)
    assert sample_time == pytest.approx(10.02)


def test_force_value_format_keeps_units_readable_for_large_values():
    assert ForceController._format_force_value(1.23456) == "1.235"
    assert ForceController._format_force_value(12345.67) == "12345.7"
    assert ForceController._format_force_value(1234567.0) == "1.235e+06"
