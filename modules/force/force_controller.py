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
    DEFAULT_ANALOG_SAMPLE_RATE = 2000
    ANALOG_OUTPUT_RATE = 400
    ANALOG_MEDIAN_WINDOW = 3
    ANALOG_AVERAGE_WINDOW_MS = 20

    def __init__(self, ui, recorder=None):
        self.ui = ui

        self.running = False
        self.latest_force = 0.0
        self.latest_vals = None
        self.active_mode = "serial"

        self.zero_offset = np.zeros(self.CHANNEL_COUNT)
        self.zero_buffer = deque(maxlen=300)
        self._analog_median_buffers = []
        self._analog_average_buffer = deque()
        self._analog_sample_count = 0

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
            preferred_index = 0
            for dev in System.local().devices:
                combo.addItem(dev.name)
                try:
                    if "6009" in dev.product_type:
                        preferred_index = combo.count() - 1
                except Exception:
                    pass
            if combo.count() > 0 and hasattr(combo, "setCurrentIndex"):
                combo.setCurrentIndex(preferred_index)
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
        self._reset_analog_filter()

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
        device = self._force_device()
        if not device:
            print("[Force] no NI DAQ device selected")
            self.on_started(False)
            return

        self.active_mode = "analog"
        self.thread = AnalogForceThread(
            device=device,
            sample_rate=self._force_sample_rate(),
            terminal_config=self._force_terminal_config(),
        )
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
        filtered_voltage_rows = self._filter_analog_voltage_rows(rows)
        if filtered_voltage_rows.size == 0:
            return

        force_rows = convert_voltages_to_force(filtered_voltage_rows, self._analog_config())

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
                sample_rate=self.ANALOG_OUTPUT_RATE,
            )

    def update_ui(self):
        if not self.running or self.latest_vals is None:
            return

        self.ui.totalForceLabel.setText(f"Total: {self.latest_force:.2f} N")
        channel_unit = "N"

        for i, val in enumerate(self.latest_vals, start=1):
            label = getattr(self.ui, f"Force{i}_Label", None)
            if label is not None:
                label.setText(f"P{i}: {val:.2f} {channel_unit}")

        self.plot.add_point(self.latest_force)

    def _selected_mode(self):
        widget = getattr(self.ui, "forceModeComboBox", None)
        if widget is None or not hasattr(widget, "currentText"):
            return "analog"
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
        return self.DEFAULT_ANALOG_SAMPLE_RATE

    def _force_terminal_config(self):
        widget = getattr(self.ui, "forceTerminalConfigComboBox", None)
        if widget is not None and hasattr(widget, "currentText"):
            text = widget.currentText().strip().upper()
            if text:
                return text
        return AnalogForceThread.DEFAULT_TERMINAL_CONFIG

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
            else 98.0665
        )
        return AnalogForceConfig(voltage_range=voltage_range, full_scale_force=full_scale)

    def _reset_analog_filter(self):
        self._analog_median_buffers = []
        self._analog_average_buffer = deque()
        self._analog_sample_count = 0

    def _filter_analog_voltage_rows(self, rows):
        voltage_rows = np.asarray(rows, dtype=float)
        if voltage_rows.ndim == 1:
            voltage_rows = voltage_rows.reshape(1, -1)

        if not self._analog_median_buffers or len(self._analog_median_buffers) != voltage_rows.shape[1]:
            self._analog_median_buffers = [
                deque(maxlen=self.ANALOG_MEDIAN_WINDOW)
                for _ in range(voltage_rows.shape[1])
            ]
            self._analog_average_buffer.clear()
            self._analog_sample_count = 0

        sample_rate = max(1, self._force_sample_rate())
        decimation = max(1, round(sample_rate / self.ANALOG_OUTPUT_RATE))
        average_window = max(
            1,
            round(sample_rate * self.ANALOG_AVERAGE_WINDOW_MS / 1000.0),
        )

        output_rows = []
        for row in voltage_rows:
            median_values = []
            for value, buffer in zip(row, self._analog_median_buffers):
                buffer.append(value)
                median_values.append(float(np.median(buffer)))

            self._analog_average_buffer.append(median_values)
            while len(self._analog_average_buffer) > average_window:
                self._analog_average_buffer.popleft()

            self._analog_sample_count += 1
            if self._analog_sample_count % decimation == 0:
                output_rows.append(np.mean(self._analog_average_buffer, axis=0))

        if not output_rows:
            return np.empty((0, voltage_rows.shape[1]))

        return np.asarray(output_rows, dtype=float)
