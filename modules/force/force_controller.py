# modules/force/force_controller.py
from collections import deque
from dataclasses import dataclass
from threading import Lock
import time

import numpy as np

from modules.force.force_thread import ForceThread
from modules.force.analog_force import AnalogForceConfig, convert_voltages_to_force
from modules.force.analog_force_thread import AnalogForceProcessor, AnalogForceThread
from modules.force.force_plot import ForcePlot
from modules.app_config import AppConfig
from modules.app_runtime import RuntimeStatus, ni_resource
from modules.daq.device_catalog import (
    capability_tooltip,
    discover_ni_devices,
    selected_device_name,
)
from modules.recorder.data_recorder import DataRecorder
from utils.log import log


@dataclass(frozen=True)
class ForceAcquisitionConfig:
    mode: str
    device: str = ""
    channels: tuple[str, ...] = ()
    sample_rate_hz: int = 0
    terminal_configuration: str = ""
    voltage_range: str = ""
    full_scale_force_n: float = 0.0
    daq_input_min_v: float = 0.0
    daq_input_max_v: float = 0.0
    serial_port: str = ""
    baud_rate: int = 0

    def analog_config(self) -> AnalogForceConfig:
        return AnalogForceConfig(
            voltage_range=self.voltage_range,
            full_scale_force=self.full_scale_force_n,
        )

    def metadata(self) -> dict:
        return {
            "force_mode": self.mode,
            "force_device": self.device,
            "force_channels": list(self.channels),
            "force_sample_rate_hz": self.sample_rate_hz,
            "force_terminal_configuration": self.terminal_configuration,
            "force_voltage_range": self.voltage_range,
            "force_full_scale_force_n": self.full_scale_force_n,
            "force_daq_input_min_v": self.daq_input_min_v,
            "force_daq_input_max_v": self.daq_input_max_v,
            "force_serial_port": self.serial_port,
            "force_baud_rate": self.baud_rate,
        }


class ForceController:
    CHANNEL_COUNT = ForceThread.CHANNEL_COUNT
    ZERO_SAMPLE_COUNT = 30
    ZERO_STD_LIMIT = 2.0
    ZERO_TREND_LIMIT = 3.0
    DEFAULT_ANALOG_SAMPLE_RATE = 2000
    ANALOG_OUTPUT_RATE = 400
    ANALOG_MEDIAN_WINDOW = 3
    ANALOG_AVERAGE_WINDOW_MS = 5

    def __init__(self, ui, recorder=None, config=None, runtime=None, resources=None, translator=None):
        self.ui = ui
        self.config = config or AppConfig()
        self.runtime = runtime
        self.resources = resources
        self.translator = translator

        self.running = False
        self.latest_force = 0.0
        self.latest_vals = None
        self.latest_voltage_vals = None
        self._voltage_warning = ""
        self.active_mode = "serial"
        self.active_config = None
        self._config_locked = False

        self.zero_offset = np.zeros(self.CHANNEL_COUNT)
        self.zero_buffer = deque(maxlen=300)
        self._force_control_buffer = deque(maxlen=400)
        self._state_lock = Lock()
        self._pending_force_plot_rows = deque(maxlen=24)
        self._force_display_sample_index = 0
        self._force_device_catalog = {}
        sample_rate_widget = getattr(self.ui, "forceSampleRateSpinBox", None)
        self._force_sample_rate_ui_maximum = (
            int(sample_rate_widget.maximum())
            if sample_rate_widget is not None and hasattr(sample_rate_widget, "maximum")
            else 48000
        )

        self.plot = ForcePlot(
            self.ui.forcePlotWidget,
            time_window=10.0,
            max_display_points=self.config.max_display_points,
            translator=self.translator,
        )
        self.thread = None
        self.recorder = recorder or DataRecorder()

        self.ui.forceStartButton.clicked.connect(self.toggle)
        self.ui.forceZeroButton.clicked.connect(self.zero)
        self.ui.recorderStartButton.clicked.connect(self.start_record)
        self.ui.recorderStopButton.clicked.connect(self.stop_record)
        mode_combo = getattr(self.ui, "forceModeComboBox", None)
        if mode_combo is not None and hasattr(mode_combo, "currentTextChanged"):
            mode_combo.currentTextChanged.connect(self.update_mode_controls)
        device_combo = getattr(self.ui, "forceDeviceComboBox", None)
        if device_combo is not None and hasattr(device_combo, "currentIndexChanged"):
            device_combo.currentIndexChanged.connect(self._on_force_device_changed)
        self.refresh_force_devices()
        self.update_mode_controls()

    def refresh_force_devices(self):
        combo = getattr(self.ui, "forceDeviceComboBox", None)
        if combo is None or not hasattr(combo, "clear") or not hasattr(combo, "addItem"):
            return

        try:
            previous_device = selected_device_name(combo)
            combo.clear()
            preferred_index = 0
            devices = discover_ni_devices()
            self._force_device_catalog = {device.name: device for device in devices}
            for device in devices:
                combo.addItem(device.display_label, device.name)
                if previous_device and device.name == previous_device:
                    preferred_index = combo.count() - 1
                elif not previous_device and "6009" in device.product_type:
                    preferred_index = combo.count() - 1
            if combo.count() > 0 and hasattr(combo, "setCurrentIndex"):
                combo.setCurrentIndex(preferred_index)
                self._on_force_device_changed(preferred_index)
        except Exception as exc:
            self._force_device_catalog = {}
            log(f"[Force] NI device discovery failed: {exc}", "error")

    def update_mode_controls(self):
        unlocked = not self._config_locked
        analog_enabled = self._selected_mode() == "analog" and unlocked
        mode_widget = getattr(self.ui, "forceModeComboBox", None)
        if mode_widget is not None and hasattr(mode_widget, "setEnabled"):
            mode_widget.setEnabled(unlocked)
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
        start_button = getattr(self.ui, "forceStartButton", None)
        if start_button is not None and hasattr(start_button, "setToolTip"):
            if self._selected_mode() == "serial":
                start_button.setToolTip(
                    self._t(
                        "force.serial_selected",
                        port=getattr(self.config, "force_serial_port", "COM15"),
                        baud=int(
                            getattr(self.config, "force_serial_baudrate", 9600)
                        ),
                    )
                )
            else:
                start_button.setToolTip("")
        self._apply_force_device_capabilities()

    def _on_force_device_changed(self, *_args):
        self._apply_force_device_capabilities()

    def retranslate_ui(self):
        self.update_mode_controls()

    def active_configuration_metadata(self):
        return self.active_config.metadata() if self.active_config is not None else {}

    def start_record(self):
        self.recorder.start(start_monotonic=time.perf_counter())
        self.recorder.update_metadata(self.active_configuration_metadata())
        if self.runtime is not None:
            self.runtime.set("recording", RuntimeStatus.RUNNING)

    def stop_record(self):
        self.recorder.stop()
        if self.runtime is not None:
            self.runtime.set("recording", RuntimeStatus.READY)

    def apply_config(self):
        self.plot.apply_max_display_points(self.config.max_display_points)
        self.update_mode_controls()

    def toggle(self):
        if self.thread and self.thread.isRunning():
            self.stop()
        else:
            self.start()

    def start(self):
        self.plot.clear()
        self.zero_buffer.clear()
        self._force_control_buffer.clear()
        self._pending_force_plot_rows.clear()
        self.zero_offset = np.zeros(self.CHANNEL_COUNT)
        self.latest_vals = None
        self.latest_force = 0.0
        self.latest_voltage_vals = None
        self._voltage_warning = ""

        if self._selected_mode() == "analog":
            self._start_analog()
            return

        self._start_serial()

    def _start_serial(self):
        serial_port = str(getattr(self.config, "force_serial_port", "COM15")).strip()
        baud_rate = int(getattr(self.config, "force_serial_baudrate", 9600))
        if not serial_port:
            detail = self._t("force.serial_missing")
            log(f"[Force] {detail}", "warning")
            if self.runtime is not None:
                self.runtime.set("force", RuntimeStatus.WARNING, detail)
            return
        self.active_mode = "serial"
        self.active_config = ForceAcquisitionConfig(
            mode="serial",
            serial_port=serial_port,
            baud_rate=baud_rate,
        )
        self._set_config_locked(True)
        if self.runtime is not None:
            self.runtime.set("force", RuntimeStatus.CONNECTING)
        try:
            self.thread = ForceThread(port=serial_port, baudrate=baud_rate)
            self.thread.data_ready.connect(self.on_data)
            self.thread.started_ok.connect(self.on_started)
            self.thread.start()
        except Exception as exc:
            self.thread = None
            self.active_config = None
            self._set_config_locked(False)
            if self.runtime is not None:
                self.runtime.set("force", RuntimeStatus.ERROR, str(exc))
            log(f"[Force] Serial start failed: {type(exc).__name__}: {exc}", "error")

    def _start_analog(self):
        device = self._force_device()
        if not device:
            log("[Force] No NI DAQ device selected", "warning")
            self.on_started(False)
            return

        info = self._force_device_catalog.get(device)
        required_channels = {f"ai{index}" for index in range(self.CHANNEL_COUNT)}
        if info is not None and not required_channels.issubset(info.ai_channels):
            detail = f"{device} does not provide the required ai0-ai{self.CHANNEL_COUNT - 1} inputs"
            log(f"[Force] {detail}", "warning")
            if self.runtime is not None:
                self.runtime.set("force", RuntimeStatus.WARNING, detail)
            return
        if info is not None:
            limit = info.ai_rate_limit(self.CHANNEL_COUNT)
            if limit and self._force_sample_rate() > limit:
                detail = f"Force rate exceeds {device} limit {limit:,} Hz"
                log(f"[Force] {detail}", "warning")
                if self.runtime is not None:
                    self.runtime.set("force", RuntimeStatus.WARNING, detail)
                return

        if self.resources is not None:
            acquired, detail = self.resources.acquire("force", [ni_resource(device, "ai")])
            if not acquired:
                log(f"[Force] Start blocked: {detail}", "warning")
                if self.runtime is not None:
                    self.runtime.set("force", RuntimeStatus.WARNING, detail)
                return

        force_config = self._analog_config()
        daq_input_min, daq_input_max = force_config.daq_input_limits
        active_config = ForceAcquisitionConfig(
            mode="analog",
            device=device,
            channels=tuple(f"ai{index}" for index in range(self.CHANNEL_COUNT)),
            sample_rate_hz=self._force_sample_rate(),
            terminal_configuration=self._force_terminal_config(),
            voltage_range=force_config.voltage_range,
            full_scale_force_n=force_config.full_scale_force,
            daq_input_min_v=daq_input_min,
            daq_input_max_v=daq_input_max,
        )
        self.active_mode = "analog"
        self.active_config = active_config
        self._set_config_locked(True)
        if self.runtime is not None:
            self.runtime.set("force", RuntimeStatus.CONNECTING)
        try:
            self.thread = AnalogForceThread(
                device=device,
                channels=list(active_config.channels),
                sample_rate=active_config.sample_rate_hz,
                terminal_config=active_config.terminal_configuration,
                input_min_voltage=active_config.daq_input_min_v,
                input_max_voltage=active_config.daq_input_max_v,
                force_config=active_config.analog_config(),
                output_rate=self.ANALOG_OUTPUT_RATE,
                median_window=self.ANALOG_MEDIAN_WINDOW,
                average_window_ms=self.ANALOG_AVERAGE_WINDOW_MS,
                force_rows_callback=self._on_analog_force_chunk_from_thread,
                voltage_rows_callback=self._on_analog_voltage_chunk_from_thread,
            )
            self.thread.started_ok.connect(self.on_started)
            self.thread.start()
        except Exception as exc:
            self.thread = None
            self.active_config = None
            self._set_config_locked(False)
            if self.resources is not None:
                self.resources.release("force")
            if self.runtime is not None:
                self.runtime.set("force", RuntimeStatus.ERROR, str(exc))
            log(f"[Force] Start failed: {type(exc).__name__}: {exc}", "error")

    def stop(self):
        if self.thread:
            if self.runtime is not None:
                self.runtime.set("force", RuntimeStatus.STOPPING)
            self.thread.stop()
            self.thread = None

        self.reset_runtime_state(clear_plot=False)
        self.running = False
        self.active_config = None
        self._set_config_locked(False)
        if self.resources is not None:
            self.resources.release("force")
        if self.runtime is not None:
            self.runtime.set("force", RuntimeStatus.READY)

    def reset_runtime_state(self, clear_plot=True):
        with self._state_lock:
            self.zero_offset = np.zeros(self.CHANNEL_COUNT)
            self.zero_buffer.clear()
            self._force_control_buffer.clear()
            self._pending_force_plot_rows.clear()
            self._force_display_sample_index = 0
            self.latest_vals = None
            self.latest_force = 0.0
            self.latest_voltage_vals = None
            self._voltage_warning = ""
        if clear_plot and self.plot is not None:
            self.plot.clear()

    def zero(self):
        with self._state_lock:
            if len(self.zero_buffer) < self.ZERO_SAMPLE_COUNT:
                log("[Force] Not enough data to zero", "warning")
                return
            window = np.array(list(self.zero_buffer)[-self.ZERO_SAMPLE_COUNT:])

        half = self.ZERO_SAMPLE_COUNT // 2

        mean1 = np.mean(window[:half], axis=0)
        mean2 = np.mean(window[half:], axis=0)

        if np.max(np.std(window, axis=0)) > self.ZERO_STD_LIMIT:
            log("[Force] Signal is fluctuating; zero failed", "warning")
            return

        if np.linalg.norm(mean2 - mean1) > self.ZERO_TREND_LIMIT:
            log("[Force] Signal is changing; zero failed", "warning")
            return

        with self._state_lock:
            self.zero_offset = np.mean(window, axis=0)
            self._force_control_buffer.clear()
        log("[Force] Zero completed")

    def on_started(self, ok):
        if ok:
            self.running = True
            self._set_config_locked(True)
            if self.runtime is not None:
                self.runtime.set("force", RuntimeStatus.RUNNING)
        else:
            self.running = False
            self.thread = None
            self.active_config = None
            self._set_config_locked(False)
            if self.resources is not None:
                self.resources.release("force")
            if self.runtime is not None:
                self.runtime.set("force", RuntimeStatus.ERROR, "Start failed")
            log("[Force] Start failed", "error")

    def on_data(self, total_force, vals):
        sample_clock = time.perf_counter()
        vals = np.array(vals, dtype=float)
        if self.active_mode == "analog":
            force_config = (
                self.active_config.analog_config()
                if self.active_config is not None
                else self._analog_config()
            )
            vals = convert_voltages_to_force(vals, force_config)

        with self._state_lock:
            if vals.size != self.zero_offset.size:
                self.zero_offset = np.zeros(vals.size)

            self.zero_buffer.append(vals)

            corrected_vals = vals - self.zero_offset
            corrected_total = float(np.sum(corrected_vals))

            self.latest_vals = corrected_vals
            self.latest_force = corrected_total
            self._force_control_buffer.append((sample_clock, corrected_total))

        if self.recorder.recording and self.active_mode != "analog":
            self.recorder.add_force_data(
                total_force=corrected_total,
                vals=corrected_vals.tolist(),
                source_monotonic=sample_clock,
            )

    def on_analog_force_chunk(self, force_rows):
        self._handle_analog_force_rows(force_rows)

    def _on_analog_force_chunk_from_thread(self, force_rows):
        self._handle_analog_force_rows(force_rows)

    def _on_analog_voltage_chunk_from_thread(self, voltage_rows):
        self._handle_analog_voltage_rows(voltage_rows)

    def _handle_analog_voltage_rows(self, voltage_rows):
        voltage_rows = np.asarray(voltage_rows, dtype=float)
        if voltage_rows.size == 0:
            return
        if voltage_rows.ndim == 1:
            voltage_rows = voltage_rows.reshape(1, -1)

        source_start, sample_rate = self._analog_voltage_chunk_timing(len(voltage_rows))
        force_config = (
            self.active_config.analog_config()
            if self.active_config is not None
            else self._analog_config()
        )
        warning = self._voltage_warning_for_rows(voltage_rows, force_config)
        with self._state_lock:
            previous_warning = self._voltage_warning
            self.latest_voltage_vals = voltage_rows[-1].copy()
            self._voltage_warning = warning

        if self.recorder.recording and hasattr(
            self.recorder,
            "add_force_voltage_chunk",
        ):
            self.recorder.add_force_voltage_chunk(
                rows=voltage_rows,
                sample_rate=sample_rate,
                source_start_monotonic=source_start,
            )

        if warning != previous_warning:
            if warning:
                log(f"[Force] {warning}", "warning")
            elif previous_warning:
                log("[Force] Analog input voltage returned to the selected range")

    def _handle_analog_force_rows(self, force_rows):
        force_rows = np.asarray(force_rows, dtype=float)
        if force_rows.size == 0:
            return
        if force_rows.ndim == 1:
            force_rows = force_rows.reshape(1, -1)

        latest = force_rows[-1]
        source_start, output_rate = self._analog_chunk_timing(len(force_rows))
        with self._state_lock:
            if force_rows.shape[1] != self.zero_offset.size:
                self.zero_offset = np.zeros(force_rows.shape[1])

            self.zero_buffer.append(latest)
            corrected_rows = force_rows - self.zero_offset
            latest_corrected = corrected_rows[-1]
            row_count = len(corrected_rows)
            start_index = self._force_display_sample_index
            self._force_display_sample_index += row_count
            times = (
                np.arange(start_index, start_index + row_count)
                / output_rate
            )

            self.latest_vals = latest_corrected
            self.latest_force = float(np.sum(latest_corrected))
            corrected_totals = np.sum(corrected_rows, axis=1)
            sample_times = source_start + np.arange(row_count) / output_rate
            self._force_control_buffer.extend(
                (float(sample_time), float(total))
                for sample_time, total in zip(sample_times, corrected_totals)
            )
            self._pending_force_plot_rows.append((times, corrected_rows))

        if self.recorder.recording:
            self.recorder.add_force_chunk(
                rows=corrected_rows,
                sample_rate=output_rate,
                source_start_monotonic=source_start,
            )

    def force_control_snapshot(self, window_s=0.05):
        """Return a robust recent total-force value and its source timestamp."""
        with self._state_lock:
            if not self._force_control_buffer:
                return None, None
            latest_time = float(self._force_control_buffer[-1][0])
            cutoff = latest_time - max(float(window_s), 0.0)
            values = [
                value
                for sample_time, value in self._force_control_buffer
                if sample_time >= cutoff
            ]
        return float(np.median(values)), latest_time

    def _analog_chunk_timing(self, row_count):
        thread = self.thread
        output_rate = float(
            getattr(thread, "force_output_sample_rate", self.ANALOG_OUTPUT_RATE)
        )
        source_start = getattr(thread, "force_chunk_start_monotonic", None)
        if source_start is None:
            source_start = (
                time.perf_counter()
                - max(int(row_count) - 1, 0) / output_rate
            )
        return float(source_start), output_rate

    def _analog_voltage_chunk_timing(self, row_count):
        thread = self.thread
        sample_rate = float(
            getattr(
                thread,
                "sample_rate",
                self.active_config.sample_rate_hz
                if self.active_config is not None
                else self._force_sample_rate(),
            )
        )
        source_start = getattr(thread, "voltage_chunk_start_monotonic", None)
        if source_start is None:
            source_start = (
                time.perf_counter()
                - max(int(row_count) - 1, 0) / sample_rate
            )
        return float(source_start), sample_rate

    @staticmethod
    def _voltage_warning_for_rows(voltage_rows, force_config):
        voltage_rows = np.asarray(voltage_rows, dtype=float)
        if not np.all(np.isfinite(voltage_rows)):
            return "Non-finite voltage detected on the force inputs"

        signal_low, signal_high = force_config.signal_voltage_limits
        daq_low, daq_high = force_config.daq_input_limits
        daq_margin = max(abs(daq_low), abs(daq_high)) * 0.02
        near_limit = np.any(
            (voltage_rows <= daq_low + daq_margin)
            | (voltage_rows >= daq_high - daq_margin),
            axis=0,
        )
        if np.any(near_limit):
            channels = ", ".join(
                f"P{index + 1}" for index in np.flatnonzero(near_limit)
            )
            return (
                f"{channels} is within 2% of the NI input limit "
                f"({daq_low:g} to {daq_high:g} V); clipping may occur"
            )

        expected_margin = max((signal_high - signal_low) * 0.02, 0.02)
        outside_range = np.any(
            (voltage_rows < signal_low - expected_margin)
            | (voltage_rows > signal_high + expected_margin),
            axis=0,
        )
        if np.any(outside_range):
            channels = ", ".join(
                f"P{index + 1}" for index in np.flatnonzero(outside_range)
            )
            return (
                f"{channels} is outside the selected transmitter range "
                f"{force_config.voltage_range}; check polarity and range settings"
            )
        return ""

    def on_analog_chunk(self, rows):
        processor = AnalogForceProcessor(
            sample_rate=self._force_sample_rate(),
            force_config=self._analog_config(),
            output_rate=self.ANALOG_OUTPUT_RATE,
            median_window=self.ANALOG_MEDIAN_WINDOW,
            average_window_ms=self.ANALOG_AVERAGE_WINDOW_MS,
        )
        voltage_rows, force_rows = processor.process_with_voltage(rows)
        self._handle_analog_voltage_rows(voltage_rows)
        self.on_analog_force_chunk(force_rows)

    def update_ui(self):
        with self._state_lock:
            latest_vals = None if self.latest_vals is None else self.latest_vals.copy()
            latest_voltage_vals = (
                None
                if self.latest_voltage_vals is None
                else self.latest_voltage_vals.copy()
            )
            voltage_warning = self._voltage_warning
            latest_force = self.latest_force
            pending_rows = list(self._pending_force_plot_rows)
            self._pending_force_plot_rows.clear()

        if not self.running or latest_vals is None:
            return

        if self.translator is not None:
            self.ui.totalForceLabel.setText(
                self.translator(
                    "force.total",
                    value=self._format_force_value(latest_force),
                )
            )
        else:
            self.ui.totalForceLabel.setText(
                f"Total: {self._format_force_value(latest_force)} N"
            )
        if latest_voltage_vals is not None and hasattr(
            self.ui.totalForceLabel,
            "setToolTip",
        ):
            raw_values = "  ".join(
                f"P{index}: {value:+.4f} V"
                for index, value in enumerate(latest_voltage_vals, start=1)
            )
            tooltip_lines = [f"Raw force inputs: {raw_values}"]
            if self.active_config is not None:
                tooltip_lines.append(
                    "NI input range: "
                    f"{self.active_config.daq_input_min_v:g} to "
                    f"{self.active_config.daq_input_max_v:g} V"
                )
            if voltage_warning:
                tooltip_lines.append(f"Warning: {voltage_warning}")
            self.ui.totalForceLabel.setToolTip("\n".join(tooltip_lines))
        channel_unit = "N"

        for i, val in enumerate(latest_vals, start=1):
            label = getattr(self.ui, f"Force{i}_Label", None)
            if label is not None:
                if self.translator is not None:
                    label.setText(
                        self.translator(
                            "force.point",
                            index=i,
                            value=self._format_force_value(val),
                        )
                    )
                else:
                    label.setText(
                        f"P{i}: {self._format_force_value(val)} {channel_unit}"
                    )
                if hasattr(label, "setToolTip"):
                    label.setToolTip(f"P{i}: {float(val):+.6f} {channel_unit}")

        if self.active_mode == "analog":
            self._flush_analog_plot(pending_rows)
        else:
            self.plot.add_point(latest_force)

    def _flush_analog_plot(self, pending_rows):
        if not pending_rows:
            return

        times = np.concatenate([row[0] for row in pending_rows])
        force_rows = np.vstack([row[1] for row in pending_rows])
        self.plot.add_timed_samples(
            times,
            np.sum(force_rows, axis=1),
        )

    @staticmethod
    def _format_force_value(value):
        value = float(value)
        magnitude = abs(value)
        if magnitude < 0.0005:
            value = 0.0
            magnitude = 0.0
        if magnitude >= 100000 or (0 < magnitude < 0.001):
            return f"{value:.3e}"
        if magnitude >= 1000:
            return f"{value:.1f}"
        if magnitude >= 100:
            return f"{value:.2f}"
        return f"{value:.3f}"

    def _selected_mode(self):
        widget = getattr(self.ui, "forceModeComboBox", None)
        if widget is None or not hasattr(widget, "currentText"):
            return "analog"
        if hasattr(widget, "currentData"):
            value = widget.currentData()
            if value in ("analog", "serial"):
                return value
        text = widget.currentText().lower()
        if "analog" in text or "模拟" in text:
            return "analog"
        return "serial"

    def _force_device(self):
        widget = getattr(self.ui, "forceDeviceComboBox", None)
        return selected_device_name(widget)

    def _set_config_locked(self, locked):
        self._config_locked = bool(locked)
        self.update_mode_controls()

    def _apply_force_device_capabilities(self):
        combo = getattr(self.ui, "forceDeviceComboBox", None)
        sample_rate = getattr(self.ui, "forceSampleRateSpinBox", None)
        if combo is None or sample_rate is None:
            return
        info = self._force_device_catalog.get(self._force_device())
        if info is not None:
            if hasattr(combo, "setToolTip"):
                combo.setToolTip(capability_tooltip(info, self.translator))
            rate_limit = info.ai_rate_limit(self.CHANNEL_COUNT)
        else:
            if hasattr(combo, "setToolTip"):
                combo.setToolTip("")
            rate_limit = 0

        if hasattr(sample_rate, "setMaximum"):
            maximum = self._force_sample_rate_ui_maximum
            if rate_limit:
                maximum = min(maximum, rate_limit)
            minimum = int(sample_rate.minimum()) if hasattr(sample_rate, "minimum") else 1
            sample_rate.setMaximum(max(minimum, int(maximum)))
        if hasattr(sample_rate, "setToolTip"):
            tooltip = (
                self._t(
                    "device.rate_limit",
                    channels=self.CHANNEL_COUNT,
                    rate=f"{rate_limit:,}",
                )
                if rate_limit
                else ""
            )
            sample_rate.setToolTip(tooltip)

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

    def _t(self, key, **values):
        if self.translator is None:
            if key == "device.rate_limit":
                return "Limit for {channels} selected channel(s): {rate} Hz".format(
                    **values
                )
            if key == "force.serial_selected":
                return "Serial source: {port} at {baud} baud (change in Settings)".format(
                    **values
                )
            if key == "force.serial_missing":
                return "Select a force-sensor serial port in Settings"
            return key.format(**values) if values else key
        return self.translator(key, **values)

