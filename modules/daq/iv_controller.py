import numpy as np
from PySide6.QtCore import QObject
from utils.log import log
from modules.app_config import AppConfig
from modules.daq.iv_worker import IVWorker
from modules.recorder.data_recorder import DataRecorder


class IVController(QObject):
    def __init__(self, ui, daq_plot, led_manager, recorder=None, config=None):
        super().__init__()
        self.ui = ui
        self.plot = daq_plot
        self.led_manager = led_manager
        self.recorder = recorder or DataRecorder()
        self.config = config or AppConfig()

        # ===== 纭欢鍙傛暟 =====
        self.sample_resistance = self.config.default_sample_resistance_ohm
        self.amplify_gain = self.config.default_amplify_gain

        self.worker = None
        self.running = False

        self.ui.ivControlButton.clicked.connect(self.toggle)

    # -------------------------
    def toggle(self):
        if not self.running:
            self.start_scan()
        else:
            self.stop_scan()

    # -------------------------
    def build_voltage_sequence(self):
        start = self.ui.ivStartSpinBox.value()
        stop = self.ui.ivStopSpinBox.value()
        step = self.ui.ivStepSpinBox.value()
        mode = self.ui.ivModeComboBox.currentText()
        repeat = self.ui.ivRepeatSpinBox.value()

        forward = np.arange(start, stop + step, step)
        backward = forward[::-1]

        seq = []
        for _ in range(repeat):
            if mode == "Forward":
                seq.extend(forward)
            elif mode == "Reverse":
                seq.extend(backward)
            elif mode == "Forward-Backward":
                seq.extend(forward)
                seq.extend(backward)

        return seq

    # -------------------------
    def get_selected_ai_channels(self):
        channels = []
        for i in range(16):
            cb = getattr(self.ui, f"ai{i}CheckBox")
            if cb.isChecked():
                channels.append(f"ai{i}")
        return channels

    # -------------------------
    def start_scan(self):
        voltages = self.build_voltage_sequence()
        ai_channels = self.get_selected_ai_channels()

        if not ai_channels:
            log("[IV] No AI channel selected", "warning")
            return

        device = self.ui.daqDeviceComboBox.currentText()
        ao_channel = self.ui.aoChannelComboBox.currentText()

        self.plot.set_mode_iv()
        self.plot.clear()

        self.worker = IVWorker(
            device=device,
            ao_channel=ao_channel,
            ai_channels=ai_channels,
            voltages=voltages,
            shunt_resistance=self.sample_resistance,
            amplify_gain=self.amplify_gain,
            channel_resistances=self.config.sample_resistances_ohm,
            channel_gains=self.config.amplify_gains,
        )

        self.worker.point_acquired.connect(self.on_iv_point)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)

        self.worker.start()

        self.running = True
        self.ui.ivControlButton.setText("急停")

        log(f"[IV] Scan started ({len(voltages)} points)")

    # -------------------------

    def stop_scan(self):
        if self.worker:
            self.worker.stop()
            self.worker.wait()
        self.on_finished()

    # -------------------------
    def on_finished(self):
        self.running = False
        self.worker = None
        self.ui.ivControlButton.setText("开始扫描")
        # self.plot.set_mode_time()
        log("[IV] Scan finished")

    # -------------------------
    def on_error(self, msg):
        log(f"[IV Error] {msg}", "error")
        self.on_finished()

    def on_iv_point(self, ch, voltage, current_mA):
        # 鍘熸湁 IV 缁樺浘
        self.plot.add_iv_point(ch, voltage, current_mA)

        # 鍚屾鏇存柊 LED
        self.led_manager.update_from_currents({
            ch: current_mA
        })

        self.recorder.add_iv_point(ch, voltage, current_mA)

