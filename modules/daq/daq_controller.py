from collections import deque
from threading import Lock

import numpy as np
from nidaqmx.system import System

from modules.app_config import AppConfig
from modules.recorder.data_recorder import DataRecorder
from modules.ui.plot_downsample import downsample_xy
from utils.log import log
from .daq_thread import DaqThread


class DaqController:
    def __init__(self, ui, plot, led_manager, recorder=None, config=None):
        self.ui = ui
        self.plot = plot
        self.led_manager = led_manager
        self.config = config or AppConfig()

        self.thread = None
        self._data_lock = Lock()
        self._pending_plot_chunks = deque(maxlen=24)
        self._latest_currents = {}
        self._active_sample_rate = 1
        self._active_sample_index = 0
        self.recorder = recorder or DataRecorder()

        self.ui.startStopButton.clicked.connect(self.toggle)
        self.ui.daqDeviceComboBox.currentIndexChanged.connect(
            self.on_device_changed
        )
        self.ui.recorderStartButton.clicked.connect(self.start_record)
        self.ui.recorderStopButton.clicked.connect(self.stop_record)

        self.refresh_devices()

    def refresh_devices(self):
        self.ui.daqDeviceComboBox.clear()

        system = System.local()
        for dev in system.devices:
            self.ui.daqDeviceComboBox.addItem(dev.name)

        if self.ui.daqDeviceComboBox.count() > 0:
            self.ui.daqDeviceComboBox.setCurrentIndex(0)
            self.on_device_changed(0)

    def start_record(self):
        self.recorder.start()

    def stop_record(self):
        self.recorder.stop()

    def on_device_changed(self, index):
        if index < 0:
            return
        print(f"[DAQ] Selected device: {self.ui.daqDeviceComboBox.currentText()}")

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
        self._active_sample_rate = fs
        self._active_sample_index = 0
        channels = [
            f"ai{i}"
            for i in range(16)
            if hasattr(self.ui, f"ai{i}CheckBox")
            and getattr(self.ui, f"ai{i}CheckBox").isChecked()
        ]

        if not channels:
            log("[DAQ] No channels selected")
            return

        self.plot.set_mode_time()
        self.plot.clear()
        self._clear_pending_data()

        self.thread = DaqThread(
            device=device,
            channels=channels,
            sample_rate=fs,
            chunk_size=self.config.daq_chunk_size(fs),
            data_callback=self._on_daq_data_from_thread,
        )
        self.thread.start()

        self._lock_ui(True)
        self.ui.startStopButton.setText("停止")

    def stop(self):
        if not self.thread:
            return

        self.thread.stop()
        self.thread.wait(1000)

        self.thread = None
        self.plot.clear()
        self._clear_pending_data()

        self._lock_ui(False)
        self.ui.startStopButton.setText("开始")

    def update_ui(self):
        with self._data_lock:
            chunks = list(self._pending_plot_chunks)
            self._pending_plot_chunks.clear()
            currents = dict(self._latest_currents)
            self._latest_currents.clear()

        if currents:
            self.led_manager.update_from_currents(currents)

        if not chunks:
            return

        merged = {}
        for chunk in chunks:
            for ch, values in chunk.items():
                t, y = values
                entry = merged.setdefault(ch, {"t": [], "y": []})
                entry["t"].append(np.asarray(t))
                entry["y"].append(np.asarray(y))

        plot_data = {
            ch: (
                np.concatenate(values["t"]),
                np.concatenate(values["y"]),
            )
            for ch, values in merged.items()
        }
        self.plot.update(
            plot_data,
            self.ui.sampleRateSpinBox.value(),
            self.ui.timeWindowSpinBox.value(),
        )

    def _on_daq_data_from_thread(self, data):
        sample_count = len(next(iter(data.values()))) if data else 0
        start_index = self._active_sample_index
        self._active_sample_index += sample_count

        currents = {}
        display_chunk = {}
        t = (np.arange(sample_count) + start_index) / self._active_sample_rate
        for ch, values in data.items():
            mean_v = float(np.mean(values))
            currents[ch] = self.config.current_mA(ch, mean_v)
            display_t, display_y = downsample_xy(
                t,
                values,
                max(100, min(500, self.config.max_display_points // 2)),
            )
            display_chunk[ch] = (display_t, display_y)

        with self._data_lock:
            self._pending_plot_chunks.append(display_chunk)
            self._latest_currents.update(currents)

        if self.recorder.recording:
            channel_names = list(data.keys())
            stacked = np.vstack([data[ch] for ch in channel_names]).T
            self.recorder.add_daq_chunk(
                rows=stacked,
                sample_rate=self._active_sample_rate,
                channels=channel_names,
            )

    def _clear_pending_data(self):
        with self._data_lock:
            self._pending_plot_chunks.clear()
            self._latest_currents.clear()

    def _lock_ui(self, locked: bool):
        self.ui.daqDeviceComboBox.setDisabled(locked)
        for i in range(16):
            cb = getattr(self.ui, f"ai{i}CheckBox", None)
            if cb:
                cb.setDisabled(locked)
