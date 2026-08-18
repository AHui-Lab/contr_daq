import numpy as np
import pyqtgraph as pg
from PySide6.QtWidgets import QVBoxLayout
import itertools
from modules.ui.plot_downsample import downsample_xy
from modules.ui.i18n import Translator

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
    MAX_DISPLAY_POINTS = 1200

    def __init__(self, parent_widget, ui, config=None, translator=None):
        self.mode = "time"  # "time" or "iv"

        self.parent = parent_widget
        self.ui = ui
        self.config = config
        self.translator = translator or Translator("en")
        self.max_display_points = self._configured_max_display_points()
        self.max_buffer_points = self._configured_max_buffer_points()

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
        self._enable_plot_optimizations()

        # ===== 状态 =====
        self.buffers = {}   # time mode buffer
        self.time_buffers = {}
        self.sample_counts = {}
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
        self.retranslate_ui()

    def set_mode_iv(self):
        self.mode = "iv"
        # self.clear()
        self.retranslate_ui()

    def retranslate_ui(self):
        if self.mode == "iv":
            self.plot.setLabel("bottom", self.translator("plot.voltage"), units="V")
            self.plot.setLabel("left", self.translator("plot.current"), units="A")
            return
        self.plot.setLabel("bottom", self.translator("plot.time"), units="s")
        self.plot.setLabel("left", self.translator("plot.voltage"), units="V")

    # ================== 清空 ==================
    def clear(self):
        self.plot.clear()
        self.plot.addLegend()
        self.buffers.clear()
        self.time_buffers.clear()
        self.sample_counts.clear()
        self.curves.clear()
        self._channel_colors.clear()

    def apply_config(self):
        self.max_display_points = self._configured_max_display_points()
        self.max_buffer_points = self._configured_max_buffer_points()
        for ch in list(self.buffers):
            t = self.time_buffers[ch]
            y = self.buffers[ch]
            t, y = self._limit_buffer_data(t, y)
            self.time_buffers[ch] = t
            self.buffers[ch] = y
            if ch in self.curves:
                display_t, display_y = self._limit_display_data(t, y)
                self.curves[ch].setData(display_t, display_y)

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

        for ch, incoming in data.items():
            if self._has_explicit_time(incoming):
                t, y = incoming
                t = np.asarray(t)
                y = np.asarray(y)
                self.sample_counts[ch] = max(
                    self.sample_counts.get(ch, 0),
                    int(round((t[-1] * fs) + 1)) if len(t) else 0,
                )
            else:
                y = np.asarray(incoming)
                start_index = self.sample_counts.get(ch, 0)
                self.sample_counts[ch] = start_index + len(y)
                t = (np.arange(len(y)) + start_index) / fs

            if ch in self.buffers:
                y = np.concatenate((self.buffers[ch], y))
                t = np.concatenate((self.time_buffers[ch], t))

            latest_t = t[-1] if len(t) else 0.0
            keep_mask = t >= max(0.0, latest_t - float(time_window))
            t = t[keep_mask]
            y = y[keep_mask]
            t, y = self._limit_buffer_data(t, y)
            self.time_buffers[ch] = t
            self.buffers[ch] = y
            display_t, display_y = self._limit_display_data(t, y)

            if ch not in self.curves:
                pen = pg.mkPen(self.channel_color(ch), width=2)
                self.curves[ch] = self.plot.plot(
                    display_t, display_y, pen=pen, name=ch
                )
            else:
                self.curves[ch].setData(display_t, display_y)

    def _limit_display_data(self, t, y):
        return downsample_xy(t, y, self.max_display_points)

    def _has_explicit_time(self, incoming):
        return (
            isinstance(incoming, tuple)
            and len(incoming) == 2
        )

    def _configured_max_display_points(self):
        if self.config is None:
            return self.MAX_DISPLAY_POINTS
        return int(self.config.max_display_points)

    def _configured_max_buffer_points(self):
        return max(self.max_display_points * 4, self.max_display_points + 1)

    def _limit_buffer_data(self, t, y):
        return downsample_xy(t, y, self.max_buffer_points)

    def _enable_plot_optimizations(self):
        if hasattr(self.plot, "setClipToView"):
            self.plot.setClipToView(True)
        if hasattr(self.plot, "setDownsampling"):
            self.plot.setDownsampling(auto=True, mode="peak")

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
