# modules/force/force_controller.py
from collections import deque

import numpy as np

from modules.force.force_thread import ForceThread
from modules.force.analog_force import AnalogForceConfig, convert_voltages_to_force
from modules.force.analog_force_thread import AnalogForceThread
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
        self.active_mode = "serial"

        self.zero_offset = np.zeros(self.CHANNEL_COUNT)
        self.zero_buffer = deque(maxlen=300)

        self.plot = ForcePlot(self.ui.forcePlotWidget, time_window=10.0)
        self.thread = None
        self.recorder = recorder or DataRecorder()

        self.ui.forceStartButton.clicked.connect(self.toggle)
        self.ui.forceZeroButton.clicked.connect(self.zero)
        self.ui.recorderStartButton.clicked.connect(self.start_record)
        self.ui.recorderStopButton.clicked.connect(self.stop_record)
        mode_combo = getattr(self.ui, "forceModeComboBox", None)
        if mode_combo is not None and hasattr(mode_combo, "currentTextChanged"):
            mode_combo.currentTextChanged.connect(self.update_mode_controls)
        self.refresh_force_devices()
        self.update_mode_controls()

    def refresh_force_devices(self):
        combo = getattr(self.ui, "forceDeviceComboBox", None)
        if combo is None or not hasattr(combo, "clear") or not hasattr(combo, "addItem"):
            return

        try:
            from nidaqmx.system import System

            combo.clear()
            for dev in System.local().devices:
                combo.addItem(dev.name)
        except Exception as exc:
            print("[Force] list NI devices failed:", exc)

    def update_mode_controls(self):
        analog_enabled = self._selected_mode() == "analog"
        for widget_name in (
            "forceDeviceComboBox",
            "forceSampleRateSpinBox",
            "forceTerminalConfigComboBox",
            "forceVoltageRangeComboBox",
            "forceFullScaleSpinBox",
        ):
            widget = getattr(self.ui, widget_name, None)
            if widget is not None and hasattr(widget, "setEnabled"):
                widget.setEnabled(analog_enabled)

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

        if self._selected_mode() == "analog":
            self._start_analog()
            return

        self._start_serial()

    def _start_serial(self):
        self.active_mode = "serial"
        self.thread = ForceThread(port="COM15", baudrate=9600)
        self.thread.data_ready.connect(self.on_data)
        self.thread.started_ok.connect(self.on_started)
        self.thread.start()

    def _start_analog(self):
        self.active_mode = "analog"
        self.thread = AnalogForceThread(
            device=self._force_device(),
            sample_rate=self._force_sample_rate(),
            terminal_config=self._force_terminal_config(),
        )
        self.thread.data_ready.connect(self.on_data)
        self.thread.chunk_ready.connect(self.on_analog_chunk)
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
        if self.active_mode == "analog":
            vals = convert_voltages_to_force(vals, self._analog_config())

        if vals.size != self.zero_offset.size:
            self.zero_offset = np.zeros(vals.size)

        self.zero_buffer.append(vals)

        corrected_vals = vals - self.zero_offset
        corrected_total = float(np.sum(corrected_vals))

        self.latest_vals = corrected_vals
        self.latest_force = corrected_total

        if self.recorder.recording and self.active_mode != "analog":
            self.recorder.add_force_data(
                total_force=corrected_total,
                vals=corrected_vals.tolist(),
            )

    def on_analog_chunk(self, rows):
        force_rows = convert_voltages_to_force(rows, self._analog_config())
        if force_rows.ndim == 1:
            force_rows = force_rows.reshape(1, -1)

        if force_rows.shape[1] != self.zero_offset.size:
            self.zero_offset = np.zeros(force_rows.shape[1])

        latest = force_rows[-1]
        self.zero_buffer.append(latest)
        corrected_rows = force_rows - self.zero_offset
        latest_corrected = corrected_rows[-1]

        self.latest_vals = latest_corrected
        self.latest_force = float(np.sum(latest_corrected))

        if self.recorder.recording:
            self.recorder.add_force_chunk(
                rows=corrected_rows,
                sample_rate=self._force_sample_rate(),
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

    def _selected_mode(self):
        widget = getattr(self.ui, "forceModeComboBox", None)
        if widget is None or not hasattr(widget, "currentText"):
            return "serial"
        text = widget.currentText().lower()
        if "analog" in text or "模拟" in text:
            return "analog"
        return "serial"

    def _force_device(self):
        widget = getattr(self.ui, "forceDeviceComboBox", None)
        if widget is not None and hasattr(widget, "currentText"):
            return widget.currentText()
        return ""

    def _force_sample_rate(self):
        widget = getattr(self.ui, "forceSampleRateSpinBox", None)
        if widget is not None and hasattr(widget, "value"):
            return int(widget.value())
        return 1000

    def _force_terminal_config(self):
        widget = getattr(self.ui, "forceTerminalConfigComboBox", None)
        if widget is not None and hasattr(widget, "currentText"):
            return widget.currentText()
        return "RSE"

    def _analog_config(self):
        range_widget = getattr(self.ui, "forceVoltageRangeComboBox", None)
        scale_widget = getattr(self.ui, "forceFullScaleSpinBox", None)
        voltage_range = (
            range_widget.currentText()
            if range_widget is not None and hasattr(range_widget, "currentText")
            else "0-10V"
        )
        full_scale = (
            float(scale_widget.value())
            if scale_widget is not None and hasattr(scale_widget, "value")
            else 100.0
        )
        return AnalogForceConfig(voltage_range=voltage_range, full_scale_force=full_scale)
