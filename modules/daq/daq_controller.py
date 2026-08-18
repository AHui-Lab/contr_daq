from collections import deque
from dataclasses import asdict, dataclass
from threading import Lock
import time

import numpy as np

from modules.app_config import AppConfig
from modules.app_runtime import RuntimeStatus, ni_resource
from modules.daq.device_catalog import (
    capability_tooltip,
    discover_ni_devices,
    selected_device_name,
)
from modules.recorder.data_recorder import DataRecorder
from modules.ui.plot_downsample import downsample_xy
from utils.log import log
from .daq_thread import DaqThread


@dataclass(frozen=True)
class DaqAcquisitionConfig:
    device: str
    product_type: str
    simulated: bool
    simultaneous_sampling: bool
    channels: tuple[str, ...]
    sample_rate_hz: int
    hardware_rate_limit_hz: int
    chunk_size: int

    def metadata(self) -> dict:
        values = asdict(self)
        return {
            "daq_device": values["device"],
            "daq_product_type": values["product_type"],
            "daq_device_simulated": values["simulated"],
            "daq_simultaneous_sampling": values["simultaneous_sampling"],
            "daq_channels": list(values["channels"]),
            "daq_sample_rate_hz": values["sample_rate_hz"],
            "daq_ai_rate_limit_hz": values["hardware_rate_limit_hz"],
            "daq_chunk_size": values["chunk_size"],
        }


class DaqController:
    def __init__(
        self,
        ui,
        plot,
        led_manager,
        recorder=None,
        config=None,
        runtime=None,
        resources=None,
        translator=None,
    ):
        self.ui = ui
        self.plot = plot
        self.led_manager = led_manager
        self.config = config or AppConfig()
        self.runtime = runtime
        self.resources = resources
        self.translator = translator

        self.thread = None
        self._data_lock = Lock()
        self._pending_plot_chunks = deque(maxlen=24)
        self._latest_currents = {}
        self._active_sample_rate = 1
        self._active_sample_index = 0
        self._stopping = False
        self._ui_locked = False
        self._device_catalog = {}
        self._sample_rate_ui_maximum = int(self.ui.sampleRateSpinBox.maximum())
        self.active_config = None
        self.recorder = recorder or DataRecorder()

        self.ui.startStopButton.clicked.connect(self.toggle)
        self.ui.daqDeviceComboBox.currentIndexChanged.connect(
            self.on_device_changed
        )
        self.ui.recorderStartButton.clicked.connect(self.start_record)
        self.ui.recorderStopButton.clicked.connect(self.stop_record)
        for index in range(16):
            checkbox = getattr(self.ui, f"ai{index}CheckBox", None)
            if checkbox is not None and hasattr(checkbox, "stateChanged"):
                checkbox.stateChanged.connect(self._on_channel_selection_changed)

        self.refresh_devices()

    def refresh_devices(self):
        combo = self.ui.daqDeviceComboBox
        previous_device = selected_device_name(combo)
        combo.clear()

        try:
            devices = discover_ni_devices()
        except Exception as exc:
            self._device_catalog = {}
            log(f"[DAQ] NI device discovery failed: {exc}", "error")
            self._apply_device_capabilities()
            return

        self._device_catalog = {device.name: device for device in devices}
        for device in devices:
            combo.addItem(device.display_label, device.name)

        if combo.count() > 0:
            index = combo.findData(previous_device) if previous_device else -1
            combo.setCurrentIndex(index if index >= 0 else 0)
            self.on_device_changed(combo.currentIndex())
        else:
            self._apply_device_capabilities()

    def start_record(self):
        self.recorder.start(start_monotonic=time.perf_counter())
        self.recorder.update_metadata(self.active_configuration_metadata())
        if self.runtime is not None:
            self.runtime.set("recording", RuntimeStatus.RUNNING)

    def stop_record(self):
        self.recorder.stop()
        if self.runtime is not None:
            self.runtime.set("recording", RuntimeStatus.READY)

    def on_device_changed(self, index):
        if index < 0:
            return
        device = self.selected_device_name()
        self._apply_device_capabilities()
        print(f"[DAQ] Selected device: {device}")

    def selected_device_name(self):
        return selected_device_name(self.ui.daqDeviceComboBox)

    def selected_device_info(self):
        return self._device_catalog.get(self.selected_device_name())

    def retranslate_ui(self):
        self._apply_device_capabilities()

    def active_configuration_metadata(self):
        return self.active_config.metadata() if self.active_config is not None else {}

    def toggle(self):
        if self.thread is None:
            self.start()
        else:
            self.stop()

    def start(self):
        if self.thread is not None:
            print("[DAQ] Thread still running, ignore start")
            return

        device = self.selected_device_name()
        fs = self.ui.sampleRateSpinBox.value()
        self._active_sample_rate = fs
        self._active_sample_index = 0
        channels = [
            f"ai{i}"
            for i in range(16)
            if hasattr(self.ui, f"ai{i}CheckBox")
            and getattr(self.ui, f"ai{i}CheckBox").isChecked()
        ]

        info = self.selected_device_info()
        if not device:
            log("[DAQ] No NI device selected", "warning")
            if self.runtime is not None:
                self.runtime.set("daq", RuntimeStatus.WARNING, "No NI device selected")
            return
        if info is not None:
            channels = [channel for channel in channels if info.has_ai_channel(channel)]
            limit = info.ai_rate_limit(len(channels))
            if limit and fs > limit:
                detail = f"Sample rate {fs:,} Hz exceeds {device} limit {limit:,} Hz"
                log(f"[DAQ] {detail}", "warning")
                if self.runtime is not None:
                    self.runtime.set("daq", RuntimeStatus.WARNING, detail)
                return

        if not channels:
            log("[DAQ] No channels selected")
            if self.runtime is not None:
                self.runtime.set("daq", RuntimeStatus.WARNING, "No channels selected")
            return

        if self.resources is not None:
            acquired, detail = self.resources.acquire("daq", [ni_resource(device, "ai")])
            if not acquired:
                log(f"[DAQ] Start blocked: {detail}", "warning")
                if self.runtime is not None:
                    self.runtime.set("daq", RuntimeStatus.WARNING, detail)
                return

        chunk_size = self.config.daq_chunk_size(fs)
        self.active_config = DaqAcquisitionConfig(
            device=device,
            product_type=info.product_type if info is not None else "",
            simulated=bool(info.is_simulated) if info is not None else False,
            simultaneous_sampling=(
                bool(info.simultaneous_sampling) if info is not None else False
            ),
            channels=tuple(channels),
            sample_rate_hz=int(fs),
            hardware_rate_limit_hz=(
                info.ai_rate_limit(len(channels)) if info is not None else 0
            ),
            chunk_size=int(chunk_size),
        )

        self.plot.set_mode_time()
        self.plot.clear()
        self._clear_pending_data()

        thread = DaqThread(
            device=device,
            channels=channels,
            sample_rate=fs,
            chunk_size=chunk_size,
            data_callback=self._on_daq_data_from_thread,
        )
        thread.finished.connect(lambda: self._on_thread_finished(thread))
        self.thread = thread
        self._stopping = False
        try:
            thread.start()
        except Exception as exc:
            self.thread = None
            self.active_config = None
            if self.resources is not None:
                self.resources.release("daq")
            if self.runtime is not None:
                self.runtime.set("daq", RuntimeStatus.ERROR, str(exc))
            log(f"[DAQ] Start failed: {type(exc).__name__}: {exc}", "error")
            return

        self._lock_ui(True)
        if self.runtime is not None:
            self.runtime.set("daq", RuntimeStatus.RUNNING)

    def stop(self):
        if not self.thread:
            return

        if self.runtime is not None:
            self.runtime.set("daq", RuntimeStatus.STOPPING)
        self._stopping = True
        self.thread.stop()
        self.thread.wait(1000)

        self.thread = None
        self.active_config = None
        self.plot.clear()
        self._clear_pending_data()

        self._lock_ui(False)
        if self.resources is not None:
            self.resources.release("daq")
        if self.runtime is not None:
            self.runtime.set("daq", RuntimeStatus.READY)

    def _on_thread_finished(self, thread):
        if self.thread is not thread:
            return
        self.thread = None
        self.active_config = None
        self._lock_ui(False)
        self._clear_pending_data()
        if self.resources is not None:
            self.resources.release("daq")
        if self.runtime is not None:
            if self._stopping:
                self.runtime.set("daq", RuntimeStatus.READY)
            else:
                self.runtime.set("daq", RuntimeStatus.ERROR, "Acquisition stopped unexpectedly")
        self._stopping = False

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
            source_start = None
            thread = self.thread
            if thread is not None and thread.sample_clock_origin is not None:
                source_start = (
                    thread.sample_clock_origin
                    + start_index / self._active_sample_rate
                )
            self.recorder.add_daq_chunk(
                rows=stacked,
                sample_rate=self._active_sample_rate,
                channels=channel_names,
                source_start_monotonic=source_start,
            )

    def _clear_pending_data(self):
        with self._data_lock:
            self._pending_plot_chunks.clear()
            self._latest_currents.clear()

    def _lock_ui(self, locked: bool):
        self._ui_locked = bool(locked)
        self._apply_device_capabilities()

    def _on_channel_selection_changed(self, *_args):
        if not self._ui_locked:
            self._apply_rate_limit(self.selected_device_info())

    def _apply_device_capabilities(self):
        info = self.selected_device_info()
        device = self.selected_device_name()
        self.ui.daqDeviceComboBox.setDisabled(self._ui_locked)

        for i in range(16):
            cb = getattr(self.ui, f"ai{i}CheckBox", None)
            if cb is None:
                continue
            available = info is None or info.has_ai_channel(f"ai{i}")
            if not available and cb.isChecked():
                cb.setChecked(False)
            cb.setEnabled(bool(available and not self._ui_locked))
            if not available:
                cb.setToolTip(
                    self._t("device.channel_unavailable", channel=f"ai{i}", device=device)
                )
            else:
                cb.setToolTip("")

        self._apply_rate_limit(info)
        if info is not None:
            self.ui.daqDeviceComboBox.setToolTip(
                capability_tooltip(info, self.translator)
            )
        else:
            self.ui.daqDeviceComboBox.setToolTip("")

    def _apply_rate_limit(self, info):
        selected_count = max(1, len(self._selected_channels()))
        hardware_limit = info.ai_rate_limit(selected_count) if info is not None else 0
        maximum = self._sample_rate_ui_maximum
        if hardware_limit:
            maximum = min(maximum, hardware_limit)
        maximum = max(int(self.ui.sampleRateSpinBox.minimum()), int(maximum))
        self.ui.sampleRateSpinBox.setMaximum(maximum)
        self.ui.sampleRateSpinBox.setDisabled(self._ui_locked)
        if info is not None and hardware_limit:
            self.ui.sampleRateSpinBox.setToolTip(
                self._t(
                    "device.rate_limit",
                    channels=selected_count,
                    rate=f"{hardware_limit:,}",
                )
            )
        else:
            self.ui.sampleRateSpinBox.setToolTip("")

    def _selected_channels(self):
        return [
            f"ai{i}"
            for i in range(16)
            if (checkbox := getattr(self.ui, f"ai{i}CheckBox", None)) is not None
            and checkbox.isChecked()
        ]

    def _t(self, key, **values):
        if self.translator is None:
            fallbacks = {
                "device.channel_unavailable": "{channel} is not available on {device}",
                "device.rate_limit": "Limit for {channels} selected channel(s): {rate} Hz",
            }
            return fallbacks[key].format(**values)
        return self.translator(key, **values)
