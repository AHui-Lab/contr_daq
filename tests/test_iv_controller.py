import sys
import types


qtcore = types.ModuleType("PySide6.QtCore")


class DummySignal:
    def connect(self, _callback):
        return None


class DummyQObject:
    def __init__(self, *args, **kwargs):
        pass


qtcore.QObject = DummyQObject
qtcore.Signal = lambda *args, **kwargs: DummySignal()

pyside6 = types.ModuleType("PySide6")
pyside6.QtCore = qtcore
sys.modules.setdefault("PySide6", pyside6)
sys.modules.setdefault("PySide6.QtCore", qtcore)

iv_worker_module = types.ModuleType("modules.daq.iv_worker")


class DummyIVWorker:
    pass


iv_worker_module.IVWorker = DummyIVWorker
sys.modules.setdefault("modules.daq.iv_worker", iv_worker_module)

from modules.daq.iv_controller import IVController


class DummyButton:
    clicked = DummySignal()

    def setText(self, text):
        self.text = text


class DummyUi:
    ivControlButton = DummyButton()


class DummyPlot:
    def __init__(self):
        self.points = []

    def add_iv_point(self, channel, voltage, current):
        self.points.append((channel, voltage, current))


class DummyLedManager:
    def __init__(self):
        self.currents = None

    def update_from_currents(self, currents):
        self.currents = currents


def test_on_iv_point_updates_plot_and_led_manager():
    plot = DummyPlot()
    led_manager = DummyLedManager()
    controller = IVController(DummyUi(), plot, led_manager)

    controller.on_iv_point("ai0", 1.2, 0.03)

    assert plot.points == [("ai0", 1.2, 0.03)]
    assert led_manager.currents == {"ai0": 0.03}
