import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QVBoxLayout
import itertools

def generate_colors(n):
    # 高对比科研级调色板（支持 32 路）
    base_colors = [
        (230, 25, 75),   # red
        (60, 180, 75),   # green
        (0, 130, 200),   # blue
        (245, 130, 48),  # orange
        (145, 30, 180),  # purple
        (70, 240, 240),  # cyan
        (240, 50, 230),  # magenta
        (210, 245, 60),  # lime
        (250, 190, 190), # pink
        (0, 128, 128),   # teal
        (230, 190, 255), # lavender
        (170, 110, 40),  # brown
        (255, 250, 200), # beige
        (128, 0, 0),     # maroon
        (170, 255, 195), # mint
        (128, 128, 0),   # olive
        (255, 215, 180), # coral
        (0, 0, 128),     # navy
        (128, 128, 128), # gray
        (255, 255, 255), # white
        (255, 99, 71),   # tomato
        (64, 224, 208),  # turquoise
        (218, 112, 214), # orchid
        (154, 205, 50),  # yellowgreen
        (0, 191, 255),   # deepskyblue
        (255, 140, 0),   # darkorange
        (138, 43, 226),  # blueviolet
        (50, 205, 50),   # limegreen
        (220, 20, 60),   # crimson
        (0, 255, 127),   # springgreen
        (255, 20, 147),  # deeppink
        (30, 144, 255),  # dodgerblue
    ]

    if n <= len(base_colors):
        return [pg.mkColor(c) for c in base_colors[:n]]

    # 超过 32 路时 fallback 到 HSV 均分
    colors = [pg.mkColor(c) for c in base_colors]
    for i in range(n - len(base_colors)):
        hue = i / (n - len(base_colors))
        colors.append(pg.hsvColor(hue, sat=1.0, val=1.0))
    return colors




class DaqPlot:
    MAX_DISPLAY_POINTS = 3000

    def __init__(self, parent_widget, ui):
        self.mode = "time"  # "time" or "iv"

        self.parent = parent_widget
        self.ui = ui

        # ===== Layout =====
        if not parent_widget.layout():
            layout = QVBoxLayout(parent_widget)
            layout.setContentsMargins(0, 0, 0, 0)
        else:
            layout = parent_widget.layout()

        self.plot = pg.PlotWidget()
        layout.addWidget(self.plot)

        self.plot.showGrid(x=True, y=True)
        self.plot.addLegend()

        # ===== 状态 =====
        self.buffers = {}   # time mode buffer
        self.curves = {}    # channel -> PlotDataItem

        self.max_channels = 32
        self._colors = generate_colors(self.max_channels)
        self._color_index = 0
        self._channel_colors = {}

        # ===== Y 轴控制 =====
        self.ui.autoRangeCheckBox.toggled.connect(self.on_auto_range)
        self.ui.yMinSpinBox.valueChanged.connect(self.update_y_range)
        self.ui.yMaxSpinBox.valueChanged.connect(self.update_y_range)
        self.on_auto_range(self.ui.autoRangeCheckBox.isChecked())

        self.set_mode_time()

    # ================== 模式切换 ==================
    def _next_color(self):
        color = self._colors[self._color_index % self.max_channels]
        self._color_index += 1
        return color

    def channel_color(self, ch):
        if ch not in self._channel_colors:
            self._channel_colors[ch] = self._next_color()
        return self._channel_colors[ch]

    def set_mode_time(self):
        self.mode = "time"
        # self.clear()
        self.plot.setLabel("bottom", "Time", units="s")
        self.plot.setLabel("left", "Voltage", units="V")

    def set_mode_iv(self):
        self.mode = "iv"
        # self.clear()
        self.plot.setLabel("bottom", "Voltage", units="V")
        self.plot.setLabel("left", "Current", units="A")

    # ================== 清空 ==================
    def clear(self):
        self.plot.clear()
        self.plot.addLegend()
        self.buffers.clear()
        self.curves.clear()
        self._channel_colors.clear()

    # ================== IV ==================
    def add_iv_point(self, channel: str, voltage: float, current: float):
        if self.mode != "iv":
            return

        if channel not in self.curves:
            pen = pg.mkPen(self.channel_color(channel), width=2)
            curve = self.plot.plot([], [], pen=pen, name=channel)
            self.curves[channel] = {"curve": curve, "x": [], "y": []}

        self.curves[channel]["x"].append(voltage)
        self.curves[channel]["y"].append(current)

        self.curves[channel]["curve"].setData(
            self.curves[channel]["x"],
            self.curves[channel]["y"]
        )

    # ================== Time ==================
    def update(self, data: dict, fs: float, time_window: float):
        if self.mode != "time":
            return

        max_points = int(fs * time_window)

        for ch, y in data.items():
            y = np.asarray(y)

            if ch not in self.buffers:
                self.buffers[ch] = y
            else:
                self.buffers[ch] = np.concatenate((self.buffers[ch], y))

            self.buffers[ch] = self.buffers[ch][-max_points:]
            t, y_display = self._display_data(self.buffers[ch], fs)

            if ch not in self.curves:
                pen = pg.mkPen(self.channel_color(ch), width=2)
                self.curves[ch] = self.plot.plot(
                    t, y_display, pen=pen, name=ch
                )
            else:
                self.curves[ch].setData(t, y_display)

    def _display_data(self, values, fs):
        if len(values) <= self.MAX_DISPLAY_POINTS:
            return np.arange(len(values)) / fs, values

        step = int(np.ceil(len(values) / self.MAX_DISPLAY_POINTS))
        indices = np.arange(0, len(values), step)
        return indices / fs, values[indices]

    # ================== Y 轴 ==================
    def on_auto_range(self, checked: bool):
        self.plot.enableAutoRange(axis='y', enable=checked)
        self.ui.yMinSpinBox.setDisabled(checked)
        self.ui.yMaxSpinBox.setDisabled(checked)

        if not checked:
            self.update_y_range()

    def update_y_range(self):
        if self.ui.autoRangeCheckBox.isChecked():
            return
        ymin = self.ui.yMinSpinBox.value()
        ymax = self.ui.yMaxSpinBox.value()
        if ymin < ymax:
            self.plot.setYRange(ymin, ymax)
