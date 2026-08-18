import sys
import types
import importlib

import numpy as np
import pytest
from modules.ui.i18n import Translator


class DummyCurve:
    def __init__(self):
        self.data_calls = []
        self.data_kwargs = []

    def setData(self, x, y, **kwargs):
        self.data_calls.append((list(x), list(y)))
        self.data_kwargs.append(kwargs)

    def clear(self):
        self.data_calls.append(([], []))


class DummyPlotWidget:
    last_curve = None

    def __init__(self):
        self.label_calls = []

    def setLabel(self, *args, **kwargs):
        self.label_calls.append((args, kwargs))

    def showGrid(self, *args, **kwargs):
        pass

    def plot(self, *args, **kwargs):
        DummyPlotWidget.last_curve = DummyCurve()
        return DummyPlotWidget.last_curve


class DummyLayout:
    def setContentsMargins(self, *args):
        pass

    def addWidget(self, widget):
        pass


class DummyParent:
    def layout(self):
        return DummyLayout()


pyqtgraph = types.ModuleType("pyqtgraph")
pyqtgraph.PlotWidget = DummyPlotWidget
pyqtgraph.mkPen = lambda *args, **kwargs: (args, kwargs)
sys.modules["pyqtgraph"] = pyqtgraph

qtwidgets = types.ModuleType("PySide6.QtWidgets")
qtwidgets.QVBoxLayout = lambda parent: DummyLayout()
pyside6 = types.ModuleType("PySide6")
pyside6.QtWidgets = qtwidgets
sys.modules["PySide6"] = pyside6
sys.modules["PySide6.QtWidgets"] = qtwidgets

sys.modules.pop("modules.force.force_plot", None)
ForcePlot = importlib.import_module("modules.force.force_plot").ForcePlot


def test_add_samples_plots_continuous_force_chunk_with_sample_timing():
    plot = ForcePlot(DummyParent(), time_window=1.0)

    plot.add_samples([10.0, 20.0, 30.0], sample_rate=10.0)

    x, y = DummyPlotWidget.last_curve.data_calls[-1]
    assert x == pytest.approx([0.0, 0.1, 0.2])
    assert y == pytest.approx([10.0, 20.0, 30.0])


def test_add_samples_prunes_old_points_by_time_window():
    plot = ForcePlot(DummyParent(), time_window=0.25)

    plot.add_samples([1.0, 2.0, 3.0, 4.0], sample_rate=10.0)

    x, y = DummyPlotWidget.last_curve.data_calls[-1]
    assert x == pytest.approx([0.1, 0.2, 0.3])
    assert y == pytest.approx([2.0, 3.0, 4.0])


def test_add_samples_limits_display_points():
    plot = ForcePlot(DummyParent(), time_window=10.0, max_display_points=50)

    plot.add_samples(range(1000), sample_rate=1000.0)

    x, y = DummyPlotWidget.last_curve.data_calls[-1]
    assert len(x) <= 50
    assert len(y) <= 50


def test_add_timed_samples_preserves_explicit_time_axis():
    plot = ForcePlot(DummyParent(), time_window=10.0)

    plot.add_timed_samples([0.0, 1.0, 2.0], [10.0, 20.0, 30.0])
    plot.add_timed_samples([5.0, 6.0], [40.0, 50.0])

    x, y = DummyPlotWidget.last_curve.data_calls[-1]
    assert x == pytest.approx([0.0, 1.0, 2.0, 5.0, 6.0])
    assert y == pytest.approx([10.0, 20.0, 30.0, 40.0, 50.0])


def test_add_timed_samples_breaks_the_curve_across_missing_data():
    plot = ForcePlot(DummyParent(), time_window=10.0)

    plot.add_timed_samples([0.00, 0.01, 0.02], [10.0, 20.0, 30.0])
    plot.add_timed_samples([0.10, 0.11], [40.0, 50.0])

    x, y = DummyPlotWidget.last_curve.data_calls[-1]
    gap_index = next(index for index, value in enumerate(y) if np.isnan(value))
    assert x[gap_index] == pytest.approx(0.03)
    assert DummyPlotWidget.last_curve.data_kwargs[-1]["connect"] == "finite"


def test_force_plot_retranslates_axis_labels():
    plot = ForcePlot(DummyParent(), translator=Translator("zh_CN"))

    plot.retranslate_ui()

    assert any(args[:2] == ("bottom", "时间") for args, _ in plot.plot.label_calls)
    assert any(args[:2] == ("left", "合力") for args, _ in plot.plot.label_calls)
