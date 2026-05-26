from PySide6.QtCore import QThread, Signal
import numpy as np

from utils.log import log


class AnalogForceThread(QThread):
    data_ready = Signal(float, list)
    chunk_ready = Signal(object)
    started_ok = Signal(bool)

    DEFAULT_CHANNELS = ["ai0", "ai1", "ai2", "ai3"]

    def __init__(
        self,
        device,
        channels=None,
        sample_rate=1000,
        terminal_config="RSE",
        chunk_size=100,
    ):
        super().__init__()
        self.device = device
        self.channels = list(channels or self.DEFAULT_CHANNELS)
        self.sample_rate = sample_rate
        self.terminal_config = terminal_config
        self.chunk_size = chunk_size
        self._running = True

    def run(self):
        try:
            import nidaqmx
            from nidaqmx.constants import AcquisitionType, TerminalConfiguration

            terminal_config = getattr(TerminalConfiguration, self.terminal_config)
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
                        timeout=1.0,
                    )
                    if not self._running:
                        break

                    if len(self.channels) == 1:
                        data = [data]

                    rows = np.vstack([np.asarray(values, dtype=float) for values in data]).T
                    latest = rows[-1]
                    self.chunk_ready.emit(rows)
                    self.data_ready.emit(float(np.sum(latest)), latest.tolist())

        except Exception as exc:
            log("[Analog Force Thread Error]", exc)
            self.started_ok.emit(False)

    def stop(self):
        self._running = False
        self.wait()
