# modules/force/force_controller.py
from collections import deque

import numpy as np

from modules.force.force_thread import ForceThread
from modules.force.force_plot import ForcePlot
from modules.recorder.data_recorder import DataRecorder


class ForceController:
    CHANNEL_COUNT = ForceThread.CHANNEL_COUNT
    ZERO_SAMPLE_COUNT = 30
    ZERO_STD_LIMIT = 2.0
    ZERO_TREND_LIMIT = 3.0

    def __init__(self, ui, recorder=None):
        self.ui = ui

        self.running = False
        self.latest_force = 0.0
        self.latest_vals = None

        self.zero_offset = np.zeros(self.CHANNEL_COUNT)
        self.zero_buffer = deque(maxlen=300)

        self.plot = ForcePlot(self.ui.forcePlotWidget, time_window=10.0)
        self.thread = None
        self.recorder = recorder or DataRecorder()

        self.ui.forceStartButton.clicked.connect(self.toggle)
        self.ui.forceZeroButton.clicked.connect(self.zero)
        self.ui.recorderStartButton.clicked.connect(self.start_record)
        self.ui.recorderStopButton.clicked.connect(self.stop_record)

    def start_record(self):
        if self.thread is None:
            print("[Recorder] please start force acquisition first")
            return

        self.recorder.start()

    def stop_record(self):
        self.recorder.stop()

    def toggle(self):
        if self.thread and self.thread.isRunning():
            self.stop()
        else:
            self.start()

    def start(self):
        self.plot.clear()
        self.zero_buffer.clear()
        self.zero_offset = np.zeros(self.CHANNEL_COUNT)
        self.latest_vals = None
        self.latest_force = 0.0

        self.thread = ForceThread(port="COM15", baudrate=9600)
        self.thread.data_ready.connect(self.on_data)
        self.thread.started_ok.connect(self.on_started)
        self.thread.start()

    def stop(self):
        if self.thread:
            self.thread.stop()
            self.thread = None

        self.latest_vals = None
        self.latest_force = 0.0
        self.running = False
        self.ui.forceStartButton.setText("开始")

    def zero(self):
        if len(self.zero_buffer) < self.ZERO_SAMPLE_COUNT:
            print("[Force] not enough data to zero")
            return

        window = np.array(list(self.zero_buffer)[-self.ZERO_SAMPLE_COUNT:])
        half = self.ZERO_SAMPLE_COUNT // 2

        mean1 = np.mean(window[:half], axis=0)
        mean2 = np.mean(window[half:], axis=0)

        if np.max(np.std(window, axis=0)) > self.ZERO_STD_LIMIT:
            print("[Force] force is fluctuating too much, zero failed")
            return

        if np.linalg.norm(mean2 - mean1) > self.ZERO_TREND_LIMIT:
            print("[Force] force is still changing, zero failed")
            return

        self.zero_offset = np.mean(window, axis=0)
        print("[Force] zero completed")

    def on_started(self, ok):
        if ok:
            self.running = True
            self.ui.forceStartButton.setText("停止")
        else:
            self.running = False
            self.thread = None
            self.ui.forceStartButton.setText("开始")
            print("[Force] start failed")

    def on_data(self, total_force, vals):
        vals = np.array(vals, dtype=float)

        if vals.size != self.zero_offset.size:
            self.zero_offset = np.zeros(vals.size)

        self.zero_buffer.append(vals)

        corrected_vals = vals - self.zero_offset
        corrected_total = float(np.sum(corrected_vals))

        self.latest_vals = corrected_vals
        self.latest_force = corrected_total

        if self.recorder.recording:
            self.recorder.add_force_data(
                total_force=corrected_total,
                vals=corrected_vals.tolist(),
            )

    def update_ui(self):
        if not self.running or self.latest_vals is None:
            return

        self.ui.totalForceLabel.setText(f"总力: {self.latest_force:.2f}")

        for i, val in enumerate(self.latest_vals, start=1):
            label = getattr(self.ui, f"Force{i}_Label", None)
            if label is not None:
                label.setText(f"P{i}: {val:.2f}")

        self.plot.add_point(self.latest_force)
