import importlib
import sys
import types

import numpy as np

from modules.app_config import AppConfig
from modules.ui.i18n import Translator


class DummySignal:
    def connect(self, _callback):
        pass


class DummyCheckBox:
    toggled = DummySignal()

    def isChecked(self):
        return True


class DummySpinBox:
    valueChanged = DummySignal()

    def __init__(self, value=0):
        self._value = value
        self.disabled = False

    def value(self):
        return self._value

    def setDisabled(self, disabled):
        self.disabled = disabled


class DummyCurve:
    def __init__(self):
        self.calls = []

    def setData(self, x, y):
        self.calls.append((list(x), list(y)))


class DummyPlotWidget:
    last_curve = None
    last_plot_args = None
    label_calls = []

    def showGrid(self, *args, **kwargs):
        pass

    def addLegend(self):
        pass

    def setLabel(self, *args, **kwargs):
        self.label_calls.append((args, kwargs))

    def clear(self):
        pass

    def enableAutoRange(self, *args, **kwargs):
        pass

    def setYRange(self, *args, **kwargs):
        pass

    def plot(self, *args, **kwargs):
        DummyPlotWidget.last_plot_args = args
        DummyPlotWidget.last_curve = DummyCurve()
        return DummyPlotWidget.last_curve


class DummyLayout:
    def setContentsMargins(self, *args):
        pass

    def addWidget(self, _widget):
        pass


class DummyParent:
    def layout(self):
        return DummyLayout()


class DummyUi:
    autoRangeCheckBox = DummyCheckBox()
    yMinSpinBox = DummySpinBox()
    yMaxSpinBox = DummySpinBox()


pyqtgraph = types.ModuleType("pyqtgraph")
pyqtgraph.PlotWidget = DummyPlotWidget
pyqtgraph.mkPen = lambda *args, **kwargs: (args, kwargs)
pyqtgraph.mkColor = lambda color: color
pyqtgraph.hsvColor = lambda *args, **kwargs: (args, kwargs)
sys.modules["pyqtgraph"] = pyqtgraph

qtwidgets = types.ModuleType("PySide6.QtWidgets")
qtwidgets.QVBoxLayout = lambda _parent: DummyLayout()
pyside6 = types.ModuleType("PySide6")
pyside6.QtWidgets = qtwidgets
sys.modules["PySide6"] = pyside6
sys.modules["PySide6.QtWidgets"] = qtwidgets

sys.modules.pop("modules.daq.daq_plot", None)
DaqPlot = importlib.import_module("modules.daq.daq_plot").DaqPlot


def test_daq_plot_limits_display_points_without_dropping_input_for_recording_path():
    config = AppConfig(max_display_points=500)
    plot = DaqPlot(DummyParent(), DummyUi(), config=config)

    plot.update({"ai0": np.arange(10000)}, fs=100000, time_window=1.0)

    x, y = DummyPlotWidget.last_plot_args[:2]
    assert len(x) == 500
    assert len(y) == 500
    assert plot.sample_counts["ai0"] == 10000


def test_daq_plot_preserves_explicit_time_axis():
    config = AppConfig(max_display_points=500)
    plot = DaqPlot(DummyParent(), DummyUi(), config=config)

    plot.update({"ai0": (np.array([0.0, 0.1]), np.array([1.0, 2.0]))}, fs=10, time_window=10.0)
    plot.update({"ai0": (np.array([1.0, 1.1]), np.array([3.0, 4.0]))}, fs=10, time_window=10.0)

    x, y = DummyPlotWidget.last_curve.calls[-1]
    assert x == [0.0, 0.1, 1.0, 1.1]
    assert y == [1.0, 2.0, 3.0, 4.0]


def test_daq_plot_retranslates_axis_labels():
    translator = Translator("zh_CN")
    plot = DaqPlot(DummyParent(), DummyUi(), translator=translator)

    plot.retranslate_ui()

    assert any(args[:2] == ("bottom", "时间") for args, _ in plot.plot.label_calls)
    assert any(args[:2] == ("left", "电压") for args, _ in plot.plot.label_calls)
