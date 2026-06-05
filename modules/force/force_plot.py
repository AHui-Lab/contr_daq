# modules/force/force_plot.py
import pyqtgraph as pg
import numpy as np
from PySide6.QtWidgets import QVBoxLayout
from collections import deque
import time


class ForcePlot:
    MAX_DISPLAY_POINTS = 3000

    def __init__(self, parent_widget, time_window=10.0):
        self.time_window = time_window

        if not parent_widget.layout():
            layout = QVBoxLayout(parent_widget)
            layout.setContentsMargins(0, 0, 0, 0)
        else:
            layout = parent_widget.layout()

        self.plot = pg.PlotWidget()
        layout.addWidget(self.plot)

        self.plot.setLabel("bottom", "Time", units="s")
        self.plot.setLabel("left", "Total Force")
        self.plot.showGrid(x=True, y=True)

        self.curve = self.plot.plot(pen=pg.mkPen("r", width=2))
        self.t0 = time.time()
        self.last_sample_t = None

        self.tbuf = deque()
        self.fbuf = deque()

    def clear(self):
        self.tbuf.clear()
        self.fbuf.clear()
        self.curve.clear()
        self.t0 = time.time()
        self.last_sample_t = None

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

    def _prune(self, latest_t):
        while self.tbuf and (latest_t - self.tbuf[0]) > self.time_window:
            self.tbuf.popleft()
            self.fbuf.popleft()

    def _update_curve(self):
        x = np.array(self.tbuf)
        y = np.array(self.fbuf)
        if len(y) > self.MAX_DISPLAY_POINTS:
            step = int(np.ceil(len(y) / self.MAX_DISPLAY_POINTS))
            x = x[::step]
            y = y[::step]

        self.curve.setData(
            x,
            y
        )
