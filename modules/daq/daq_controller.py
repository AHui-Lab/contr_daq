from nidaqmx.system import System
from .daq_thread import DaqThread
from .daq_plot import DaqPlot
from utils.log import log
import numpy as np
from modules.recorder.data_recorder import DataRecorder

class DaqController:
    def __init__(self, ui, plot, led_manager, recorder=None):
        self.ui = ui
        self.plot = plot
        self.led_manager = led_manager


        # ===== Thread =====
        self.thread = None

        # ===== UI 信号 =====
        self.ui.startStopButton.clicked.connect(self.toggle)
        self.ui.daqDeviceComboBox.currentIndexChanged.connect(
            self.on_device_changed
        )

        self.ui.recorderStartButton.clicked.connect(self.start_record)
        self.ui.recorderStopButton.clicked.connect(self.stop_record)
        # ===== 初始化 =====
        self.refresh_devices()

        self.recorder = recorder or DataRecorder()

    # --------------------------------------------------
    # 枚举 NI 设备
    # --------------------------------------------------
    def refresh_devices(self):
        self.ui.daqDeviceComboBox.clear()

        system = System.local()
        for dev in system.devices:
            self.ui.daqDeviceComboBox.addItem(dev.name)

        if self.ui.daqDeviceComboBox.count() > 0:
            self.ui.daqDeviceComboBox.setCurrentIndex(0)
            self.on_device_changed(0)

    def start_record(self):
        if self.thread is None:
            print("[Recorder] 请先启动DAQ")
            return

        self.recorder.start()

    def stop_record(self):
        self.recorder.stop()

    def on_device_changed(self, index):
        if index < 0:
            return
        print(f"[DAQ] Selected device: {self.ui.daqDeviceComboBox.currentText()}")

    # --------------------------------------------------
    # Start / Stop
    # --------------------------------------------------
    def toggle(self):
        if self.thread is None:
            self.start()
        else:
            self.stop()

    def start(self):
        if self.thread is not None:
            print("[DAQ] Thread still running, ignore start")
            return
        device = self.ui.daqDeviceComboBox.currentText()
        fs = self.ui.sampleRateSpinBox.value()

        # ⚠️ 这里只给逻辑通道名 ai0 / ai1
        channels = [
            f"ai{i}"
            for i in range(16)
            if hasattr(self.ui, f"ai{i}CheckBox")
               and getattr(self.ui, f"ai{i}CheckBox").isChecked()
        ]

        if not channels:
            log("[DAQ] No channels selected")
            return

        # 清图
        self.plot.set_mode_time()
        self.plot.clear()

        # 启动线程（与你的 DaqThread 完全匹配）
        self.thread = DaqThread(
            device=device,
            channels=channels,
            sample_rate=fs,
        )

        def on_daq_data(data):
            self.plot.update(
                data,
                fs,
                self.ui.timeWindowSpinBox.value()
            )

            # === 电压 → 电流（按你的 IV 同样电路）===
            currents = {}
            for ch, v in data.items():
                mean_v = float(np.mean(v))
                current_mA = mean_v / (30.0 * 51.0) * 1000.0
                currents[ch] = current_mA

            self.led_manager.update_from_currents(currents)
            if self.recorder.recording:
                # shape: (chunk_size, 通道数)
                channel_names = list(data.keys())
                stacked = np.vstack([data[ch] for ch in channel_names]).T
                self.recorder.add_daq_chunk(
                    rows=stacked,
                    sample_rate=fs,
                    channels=channel_names,
                )

        self.thread.data_ready.connect(on_daq_data)

        self.thread.start()

        self._lock_ui(True)
        self.ui.startStopButton.setText("停止")

    def stop(self):
        if not self.thread:
            return

        # 1️⃣ 请求线程退出
        self.thread.stop()

        # 2️⃣ 等待线程真正结束（最多 1 秒）
        self.thread.wait(1000)

        # 3️⃣ 断开信号（防止残留）
        try:
            self.thread.data_ready.disconnect()
        except TypeError:
            pass

        self.thread = None

        # 4️⃣ 清空图像（停止时就清）
        self.plot.clear()

        # 5️⃣ UI 恢复
        self._lock_ui(False)
        self.ui.startStopButton.setText("开始")

    # --------------------------------------------------
    def _lock_ui(self, locked: bool):
        self.ui.daqDeviceComboBox.setDisabled(locked)
        for i in range(16):
            cb = getattr(self.ui, f"ai{i}CheckBox", None)
            if cb:
                cb.setDisabled(locked)
