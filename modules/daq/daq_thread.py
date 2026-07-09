import numpy as np
import nidaqmx
from nidaqmx.constants import AcquisitionType, TerminalConfiguration
from PySide6.QtCore import QThread, Signal

from utils.log import log


class DaqThread(QThread):
    data_ready = Signal(dict)

    def __init__(
        self,
        device,
        channels,
        sample_rate,
        recorder=None,
        chunk_size=None,
        data_callback=None,
    ):
        super().__init__()
        self.device = device
        self.channels = channels
        self.sample_rate = sample_rate
        self.chunk_size = int(chunk_size or 100)
        self._running = True
        self.recorder = recorder
        self.data_callback = data_callback
        self.read_timeout = self._read_timeout()

    def run(self):
        try:
            with nidaqmx.Task() as task:
                for channel in self.channels:
                    task.ai_channels.add_ai_voltage_chan(
                        f"{self.device}/{channel}",
                        terminal_config=TerminalConfiguration.RSE,
                    )

                task.timing.cfg_samp_clk_timing(
                    rate=self.sample_rate,
                    sample_mode=AcquisitionType.CONTINUOUS,
                    samps_per_chan=self.chunk_size,
                )

                task.start()

                while self._running:
                    data = task.read(
                        number_of_samples_per_channel=self.chunk_size,
                        timeout=self.read_timeout,
                    )

                    if not self._running:
                        break

                    if len(self.channels) == 1:
                        data = [data]

                    result = {
                        channel: np.asarray(values)
                        for channel, values in zip(self.channels, data)
                    }
                    if self.data_callback is not None:
                        self.data_callback(result)
                    else:
                        self.data_ready.emit(result)

        except Exception as exc:
            log(f"[DAQ Thread Error] {type(exc).__name__}: {exc}", "error")

    def stop(self):
        self._running = False

    def _read_timeout(self):
        sample_rate = max(float(self.sample_rate), 1.0)
        expected = self.chunk_size / sample_rate
        return max(0.2, min(1.0, expected * 3.0))
