# modules/force/force_plot.py
import pyqtgraph as pg
import numpy as np
from PySide6.QtWidgets import QVBoxLayout
from collections import deque
import time
from modules.ui.plot_downsample import downsample_xy
from modules.ui.i18n import Translator


class ForcePlot:
    MAX_DISPLAY_POINTS = 1200
    GAP_FACTOR = 3.0

    def __init__(self, parent_widget, time_window=10.0, max_display_points=None, translator=None):
        self.time_window = time_window
        self.max_display_points = int(max_display_points or self.MAX_DISPLAY_POINTS)
        self.translator = translator or Translator("en")

        if not parent_widget.layout():
            layout = QVBoxLayout(parent_widget)
            layout.setContentsMargins(0, 0, 0, 0)
        else:
            layout = parent_widget.layout()

        self.plot = pg.PlotWidget()
        layout.addWidget(self.plot)

        self.retranslate_ui()
        self.plot.showGrid(x=True, y=True)
        self._enable_plot_optimizations()

        self.curve = self.plot.plot(pen=pg.mkPen("r", width=2))
        self.t0 = time.time()
        self.last_sample_t = None
        self.expected_sample_dt = None

        self.tbuf = deque()
        self.fbuf = deque()

    def retranslate_ui(self):
        self.plot.setLabel("bottom", self.translator("plot.time"), units="s")
        self.plot.setLabel("left", self.translator("plot.total_force"))

    def clear(self):
        self.tbuf.clear()
        self.fbuf.clear()
        self.curve.clear()
        self.t0 = time.time()
        self.last_sample_t = None
        self.expected_sample_dt = None

    def add_point(self, force):
        t = time.time() - self.t0
        self.last_sample_t = t
        self.tbuf.append(t)
        self.fbuf.append(force)

        self._prune(t)
        self._update_curve()

    def add_samples(self, forces, sample_rate):
        forces = np.asarray(forces, dtype=float)
        if forces.size == 0:
            return

        sample_rate = max(float(sample_rate), 1.0)
        dt = 1.0 / sample_rate
        start_t = 0.0 if self.last_sample_t is None else self.last_sample_t + dt

        for index, force in enumerate(forces):
            t = start_t + index * dt
            self.tbuf.append(t)
            self.fbuf.append(float(force))

        self.last_sample_t = start_t + (len(forces) - 1) * dt
        self._prune(self.last_sample_t)
        self._update_curve()

    def add_timed_samples(self, times, forces):
        times = np.asarray(times, dtype=float)
        forces = np.asarray(forces, dtype=float)
        if times.size == 0 or forces.size == 0:
            return

        pair_count = min(times.size, forces.size)
        times = times[:pair_count]
        forces = forces[:pair_count]
        positive_deltas = np.diff(times)
        positive_deltas = positive_deltas[
            np.isfinite(positive_deltas) & (positive_deltas > 0)
        ]
        if positive_deltas.size:
            observed_dt = float(np.median(positive_deltas))
            if self.expected_sample_dt is None:
                self.expected_sample_dt = observed_dt
            else:
                self.expected_sample_dt = min(self.expected_sample_dt, observed_dt)

        for sample_time, force in zip(times, forces):
            sample_time = float(sample_time)
            if self._is_time_gap(sample_time):
                gap_time = self.last_sample_t + self.expected_sample_dt
                self.tbuf.append(gap_time)
                self.fbuf.append(float("nan"))
            self.tbuf.append(sample_time)
            self.fbuf.append(float(force))
            self.last_sample_t = sample_time

        self._prune(self.last_sample_t)
        self._update_curve()

    def _is_time_gap(self, sample_time):
        if self.last_sample_t is None or self.expected_sample_dt is None:
            return False
        return (
            float(sample_time) - self.last_sample_t
            > self.expected_sample_dt * self.GAP_FACTOR
        )

    def _prune(self, latest_t):
        while self.tbuf and (latest_t - self.tbuf[0]) > self.time_window:
            self.tbuf.popleft()
            self.fbuf.popleft()

    def _update_curve(self):
        x = np.array(self.tbuf)
        y = np.array(self.fbuf)
        x, y = downsample_xy(x, y, self.max_display_points)

        self.curve.setData(
            x,
            y,
            connect="finite",
        )

    def apply_max_display_points(self, max_display_points):
        self.max_display_points = int(max_display_points)
        self._update_curve()

    def _enable_plot_optimizations(self):
        if hasattr(self.plot, "setClipToView"):
            self.plot.setClipToView(True)
        if hasattr(self.plot, "setDownsampling"):
            self.plot.setDownsampling(auto=True, mode="peak")
