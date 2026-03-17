# modules/force/force_plot.py
import pyqtgraph as pg
import numpy as np
from PySide6.QtWidgets import QVBoxLayout
from collections import deque
import time


class ForcePlot:
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

        self.tbuf = deque()
        self.fbuf = deque()

    def clear(self):
        self.tbuf.clear()
        self.fbuf.clear()
        self.curve.clear()
        self.t0 = time.time()

    def add_point(self, force):
        t = time.time() - self.t0
        self.tbuf.append(t)
        self.fbuf.append(force)

        while self.tbuf and (t - self.tbuf[0]) > self.time_window:
            self.tbuf.popleft()
            self.fbuf.popleft()

        self.curve.setData(
            np.array(self.tbuf),
            np.array(self.fbuf)
        )
