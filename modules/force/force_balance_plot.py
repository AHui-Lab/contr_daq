# modules/force/force_balance_plot.py
import pyqtgraph as pg
from PySide6.QtWidgets import QVBoxLayout


class ForceBalancePlot:
    def __init__(self, parent_widget):
        self.plot = pg.PlotWidget()
        self.plot.setAspectLocked(True)
        self.plot.setXRange(-1.2, 1.2)
        self.plot.setYRange(-1.2, 1.2)
        self.plot.showGrid(x=True, y=True)

        layout = QVBoxLayout(parent_widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.plot)

        # 中心点
        self.center = self.plot.plot(
            [0], [0],
            pen=None,
            symbol="o",
            symbolSize=12,
            symbolBrush=(150, 150, 150)
        )

        # 当前受力点
        self.point = self.plot.plot(
            [0], [0],
            pen=None,
            symbol="o",
            symbolSize=14,
            symbolBrush=(0, 120, 255)
        )

    def update_force(self, f1, f2, f3, f4):
        total = f1 + f2 + f3 + f4
        if total <= 0:
            return

        x = (-f1 + f2 - f3 + f4) / total
        y = ( f1 + f2 - f3 - f4) / total

        self.point.setData([x], [y])
