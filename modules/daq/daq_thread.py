from PySide6.QtCore import QThread, Signal
import nidaqmx
from nidaqmx.constants import AcquisitionType
import numpy as np
from nidaqmx.constants import TerminalConfiguration
from utils.log import log


class DaqThread(QThread):
    data_ready = Signal(dict)

    def __init__(self, device, channels, sample_rate):
        super().__init__()
        self.device = device
        self.channels = channels
        self.sample_rate = sample_rate
        self.chunk_size = 100
        self._running = True

    def run(self):
        try:
            with nidaqmx.Task() as task:
                for ch in self.channels:
                    task.ai_channels.add_ai_voltage_chan(
                        f"{self.device}/{ch}",
                        terminal_config=TerminalConfiguration.RSE
                    )

                task.timing.cfg_samp_clk_timing(
                    rate=self.sample_rate,
                    sample_mode=AcquisitionType.CONTINUOUS,
                    samps_per_chan=self.chunk_size
                )

                task.start()

                while self._running:
                    data = task.read(
                        number_of_samples_per_channel=self.chunk_size,
                        timeout=1.0   # ⭐ 关键：不要无限阻塞
                    )

                    if not self._running:
                        break

                    if len(self.channels) == 1:
                        data = [data]

                    result = {
                        ch: np.asarray(d)
                        for ch, d in zip(self.channels, data)
                    }

                    self.data_ready.emit(result)

        except Exception as e:
            log("[DAQ Thread Error]", e)

    def stop(self):
        self._running = False
