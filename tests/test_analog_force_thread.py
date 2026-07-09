import sys
import types
import importlib


qtcore = types.ModuleType("PySide6.QtCore")


class DummyQThread:
    def __init__(self, *args, **kwargs):
        pass

    def start(self):
        pass

    def wait(self):
        pass


class DummySignal:
    def __init__(self, *args, **kwargs):
        pass

    def emit(self, *args, **kwargs):
        pass


qtcore.QThread = DummyQThread
qtcore.QObject = object
qtcore.Signal = DummySignal

pyside6 = types.ModuleType("PySide6")
pyside6.QtCore = qtcore
sys.modules.setdefault("PySide6", pyside6)
sys.modules.setdefault("PySide6.QtCore", qtcore)

from modules.force.analog_force_thread import AnalogForceThread


def test_default_analog_force_thread_uses_four_voltage_channels():
    thread = AnalogForceThread(device="Dev2", sample_rate=1000)

    assert thread.device == "Dev2"
    assert thread.channels == ["ai0", "ai1", "ai2", "ai3"]
    assert thread.sample_rate == 1000
    assert thread.terminal_config == "DIFFERENTIAL"
    assert thread.chunk_size == 100


def test_analog_force_thread_accepts_custom_channels_and_terminal_config():
    thread = AnalogForceThread(
        device="Dev3",
        channels=["ai4", "ai5"],
        sample_rate=500,
        terminal_config="DIFFERENTIAL",
        chunk_size=25,
    )

    assert thread.channels == ["ai4", "ai5"]
    assert thread.terminal_config == "DIFFERENTIAL"
    assert thread.chunk_size == 25


def test_analog_force_thread_maps_differential_to_nidaqmx_diff():
    thread = AnalogForceThread(device="Dev1", terminal_config="DIFFERENTIAL")

    assert thread.TERMINAL_CONFIG_ALIASES["DIFFERENTIAL"] == "DIFF"


def test_iv_worker_uses_per_channel_current_conversion_parameters():
    nidaqmx = types.ModuleType("nidaqmx")
    constants = types.ModuleType("nidaqmx.constants")
    constants.AcquisitionType = object
    constants.VoltageUnits = object
    constants.TerminalConfiguration = object
    nidaqmx.constants = constants
    sys.modules.setdefault("nidaqmx", nidaqmx)
    sys.modules.setdefault("nidaqmx.constants", constants)
    active_qtcore = sys.modules["PySide6.QtCore"]
    active_qtcore.QThread = DummyQThread
    active_qtcore.Signal = DummySignal

    sys.modules.pop("modules.daq.iv_worker", None)
    IVWorker = importlib.import_module("modules.daq.iv_worker").IVWorker

    worker = IVWorker(
        device="Dev1",
        ao_channel="Dev1/ao0",
        ai_channels=["ai0", "ai1"],
        voltages=[1.0],
        channel_resistances=[100.0, 200.0] + [100.0] * 14,
        channel_gains=[5.0, 10.0] + [5.0] * 14,
    )

    assert worker._current_mA("ai0", 1.0) == 2.0
    assert worker._current_mA("ai1", 1.0) == 0.5
