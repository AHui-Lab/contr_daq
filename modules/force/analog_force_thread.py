from PySide6.QtCore import QThread, Signal
import numpy as np
from collections import deque

from modules.force.analog_force import convert_voltages_to_force
from utils.log import log


class AnalogForceProcessor:
    def __init__(
        self,
        sample_rate,
        force_config,
        output_rate=400,
        median_window=3,
        average_window_ms=20,
        force_rows_callback=None,
    ):
        self.sample_rate = sample_rate
        self.force_config = force_config
        self.output_rate = output_rate
        self.median_window = median_window
        self.average_window_ms = average_window_ms
        self.force_rows_callback = force_rows_callback
        self._median_buffers = []
        self._average_buffer = deque()
        self._sample_count = 0

    def process(self, rows):
        filtered_voltage_rows = self._filter_voltage_rows(rows)
        if filtered_voltage_rows.size == 0:
            return filtered_voltage_rows

        return convert_voltages_to_force(filtered_voltage_rows, self.force_config)

    def _filter_voltage_rows(self, rows):
        voltage_rows = np.asarray(rows, dtype=float)
        if voltage_rows.ndim == 1:
            voltage_rows = voltage_rows.reshape(1, -1)

        if not self._median_buffers or len(self._median_buffers) != voltage_rows.shape[1]:
            self._median_buffers = [
                deque(maxlen=self.median_window)
                for _ in range(voltage_rows.shape[1])
            ]
            self._average_buffer.clear()
            self._sample_count = 0

        sample_rate = max(1, int(self.sample_rate))
        decimation = max(1, round(sample_rate / max(float(self.output_rate), 1.0)))
        average_window = max(
            1,
            round(sample_rate * self.average_window_ms / 1000.0),
        )

        output_rows = []
        for row in voltage_rows:
            median_values = []
            for value, buffer in zip(row, self._median_buffers):
                buffer.append(value)
                median_values.append(float(np.median(buffer)))

            self._average_buffer.append(median_values)
            while len(self._average_buffer) > average_window:
                self._average_buffer.popleft()

            self._sample_count += 1
            if self._sample_count % decimation == 0:
                output_rows.append(np.mean(self._average_buffer, axis=0))

        if not output_rows:
            return np.empty((0, voltage_rows.shape[1]))

        return np.asarray(output_rows, dtype=float)


class AnalogForceThread(QThread):
    data_ready = Signal(float, list)
    chunk_ready = Signal(object)
    force_chunk_ready = Signal(object)
    started_ok = Signal(bool)

    DEFAULT_CHANNELS = ["ai0", "ai1", "ai2", "ai3"]
    DEFAULT_TERMINAL_CONFIG = "DIFFERENTIAL"
    TERMINAL_CONFIG_ALIASES = {
        "DIFFERENTIAL": "DIFF",
    }

    def __init__(
        self,
        device,
        channels=None,
        sample_rate=1000,
        terminal_config=DEFAULT_TERMINAL_CONFIG,
        chunk_size=100,
        force_config=None,
        output_rate=400,
        median_window=3,
        average_window_ms=20,
        force_rows_callback=None,
    ):
        super().__init__()
        self.device = device
        self.channels = list(channels or self.DEFAULT_CHANNELS)
        self.sample_rate = sample_rate
        self.terminal_config = terminal_config or self.DEFAULT_TERMINAL_CONFIG
        self.chunk_size = chunk_size
        self.force_config = force_config
        self.output_rate = output_rate
        self.median_window = median_window
        self.average_window_ms = average_window_ms
        self.force_rows_callback = force_rows_callback
        self._running = True
        self.read_timeout = self._read_timeout()
        self._processor = None
        if self.force_config is not None:
            self._processor = AnalogForceProcessor(
                sample_rate=self.sample_rate,
                force_config=self.force_config,
                output_rate=self.output_rate,
                median_window=self.median_window,
                average_window_ms=self.average_window_ms,
            )

    def run(self):
        try:
            import nidaqmx
            from nidaqmx.constants import AcquisitionType, TerminalConfiguration

            terminal_config_name = self.TERMINAL_CONFIG_ALIASES.get(
                self.terminal_config.upper(),
                self.terminal_config.upper(),
            )
            terminal_config = getattr(TerminalConfiguration, terminal_config_name)
            with nidaqmx.Task() as task:
                for channel in self.channels:
                    task.ai_channels.add_ai_voltage_chan(
                        f"{self.device}/{channel}",
                        terminal_config=terminal_config,
                    )

                task.timing.cfg_samp_clk_timing(
                    rate=self.sample_rate,
                    sample_mode=AcquisitionType.CONTINUOUS,
                    samps_per_chan=self.chunk_size,
                )

                task.start()
                self.started_ok.emit(True)

                while self._running:
                    data = task.read(
                        number_of_samples_per_channel=self.chunk_size,
                        timeout=self.read_timeout,
                    )
                    if not self._running:
                        break

                    if len(self.channels) == 1:
                        data = [data]

                    rows = np.vstack([np.asarray(values, dtype=float) for values in data]).T
                    latest = rows[-1]
                    if self.force_rows_callback is None:
                        self.chunk_ready.emit(rows)

                    if self.force_config is not None:
                        force_rows = self._process_force_rows(rows)
                        if force_rows.size:
                            if self.force_rows_callback is not None:
                                self.force_rows_callback(force_rows)
                            else:
                                self.force_chunk_ready.emit(force_rows)
                            latest_force = force_rows[-1]
                            if self.force_rows_callback is None:
                                self.data_ready.emit(
                                    float(np.sum(latest_force)),
                                    latest_force.tolist(),
                                )
                    else:
                        self.data_ready.emit(float(np.sum(latest)), latest.tolist())

        except Exception as exc:
            log(f"[Analog Force Thread Error] {type(exc).__name__}: {exc}", "error")
            self.started_ok.emit(False)

    def stop(self):
        self._running = False
        self.wait()

    def _process_force_rows(self, rows):
        if self._processor is None:
            return np.empty((0, np.asarray(rows).shape[-1]))

        return self._processor.process(rows)

    def _read_timeout(self):
        sample_rate = max(float(self.sample_rate), 1.0)
        expected = self.chunk_size / sample_rate
        return max(0.2, min(1.0, expected * 3.0))
