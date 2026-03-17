import time
import numpy as np
import nidaqmx
from nidaqmx.constants import AcquisitionType, VoltageUnits
from PySide6.QtCore import QThread, Signal
from nidaqmx.constants import TerminalConfiguration


class IVWorker(QThread):
    point_acquired = Signal(str, float, float)   # channel, V, I(mA)
    finished = Signal()
    error = Signal(str)

    def __init__(
        self,
        device: str,
        ao_channel: str,
        ai_channels: list,
        voltages: list,
        settle_time=0.01,
        samples=100,
        shunt_resistance=30,
        amplify_gain=51.0,
    ):
        super().__init__()
        self.device = device
        self.ao_channel = ao_channel
        self.ai_channels = ai_channels
        self.voltages = voltages

        self.settle_time = settle_time
        self.samples = samples

        self.shunt = shunt_resistance
        self.gain = amplify_gain

        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        try:
            with nidaqmx.Task() as ao_task, nidaqmx.Task() as ai_task:

                # AO
                ao_task.ao_channels.add_ao_voltage_chan(
                    self.ao_channel, units=VoltageUnits.VOLTS
                )

                # AI
                for ch in self.ai_channels:
                    ai_task.ai_channels.add_ai_voltage_chan(
                        f"{self.device}/{ch}",
                        terminal_config=TerminalConfiguration.RSE
                    )

                ai_task.timing.cfg_samp_clk_timing(
                    rate=10_000,
                    sample_mode=AcquisitionType.FINITE,
                    samps_per_chan=self.samples
                )

                for v in self.voltages:
                    if not self._running:
                        break

                    ao_task.write(float(v))
                    time.sleep(self.settle_time)

                    data = ai_task.read(
                        number_of_samples_per_channel=self.samples
                    )

                    if len(self.ai_channels) == 1:
                        data = [data]

                    for ch, d in zip(self.ai_channels, data):
                        v_mean = float(np.mean(d))

                        # ===== 核心公式 =====
                        # I(mA) = V_ai / (R * Gain) * 1000
                        current_mA = v_mean / (self.shunt * self.gain)

                        self.point_acquired.emit(ch, v, current_mA)

            self.finished.emit()

        except Exception as e:
            self.error.emit(str(e))
