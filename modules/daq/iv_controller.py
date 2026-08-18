import numpy as np
from PySide6.QtCore import QObject
from utils.log import log
from modules.app_config import AppConfig
from modules.app_runtime import RuntimeStatus, ni_resource
from modules.daq.device_catalog import discover_ni_devices, selected_device_name
from modules.daq.iv_worker import IVWorker
from modules.recorder.data_recorder import DataRecorder


class IVController(QObject):
    def __init__(self, ui, daq_plot, led_manager, recorder=None, config=None, runtime=None, resources=None):
        super().__init__()
        self.ui = ui
        self.plot = daq_plot
        self.led_manager = led_manager
        self.recorder = recorder or DataRecorder()
        self.config = config or AppConfig()
        self.runtime = runtime
        self.resources = resources

        # ===== 纭欢鍙傛暟 =====
        self.sample_resistance = self.config.default_sample_resistance_ohm
        self.amplify_gain = self.config.default_amplify_gain

        self.worker = None
        self.running = False
        self._controls_locked = False
        self._control_enabled_snapshot = {}

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
        mode = (
            self.ui.ivModeComboBox.currentData()
            if hasattr(self.ui.ivModeComboBox, "currentData")
            else None
        )
        if mode is None:
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

        if len(voltages) == 0:
            log("[IV] Voltage sequence is empty", "warning")
            if self.runtime is not None:
                self.runtime.set("iv", RuntimeStatus.WARNING, "Voltage sequence is empty")
            return

        if not ai_channels:
            log("[IV] No AI channel selected", "warning")
            if self.runtime is not None:
                self.runtime.set("iv", RuntimeStatus.WARNING, "No AI channel selected")
            return

        device = selected_device_name(self.ui.daqDeviceComboBox)
        ao_channel = self.ui.aoChannelComboBox.currentText()

        if not device or not ao_channel.startswith(f"{device}/"):
            detail = "AI and AO channels must belong to the selected NI device"
            log(f"[IV] {detail}", "warning")
            if self.runtime is not None:
                self.runtime.set("iv", RuntimeStatus.WARNING, detail)
            return

        sample_rate = 10_000
        try:
            device_info = next(
                (item for item in discover_ni_devices() if item.name == device),
                None,
            )
        except Exception as exc:
            device_info = None
            log(f"[IV] NI capability query failed: {exc}", "warning")
        if device_info is not None:
            rate_limit = device_info.ai_rate_limit(len(ai_channels))
            if rate_limit:
                sample_rate = min(sample_rate, rate_limit)
            if sample_rate < 10_000:
                log(
                    f"[IV] Sample rate adjusted to {sample_rate:,} Hz for "
                    f"{len(ai_channels)} channels on {device}",
                    "warning",
                )
            ao_voltage_range = (
                device_info.ao_range_for(min(voltages), max(voltages))
                if device_info.ao_voltage_ranges
                else (-10.0, 10.0)
            )
            if device_info.ao_voltage_ranges and ao_voltage_range is None:
                detail = (
                    f"{device} AO does not support the requested IV range "
                    f"{min(voltages):g} to {max(voltages):g} V"
                )
                log(f"[IV] {detail}", "warning")
                if self.runtime is not None:
                    self.runtime.set("iv", RuntimeStatus.WARNING, detail)
                return
        else:
            ao_voltage_range = (-10.0, 10.0)

        if self.resources is not None:
            required = [ni_resource(device, "ai"), ni_resource(ao_channel, "ao")]
            acquired, detail = self.resources.acquire("iv", required)
            if not acquired:
                log(f"[IV] Start blocked: {detail}", "warning")
                if self.runtime is not None:
                    self.runtime.set("iv", RuntimeStatus.WARNING, detail)
                return

        self.plot.set_mode_iv()
        self.plot.clear()

        try:
            self.worker = IVWorker(
                device=device,
                ao_channel=ao_channel,
                ai_channels=ai_channels,
                voltages=voltages,
                sample_rate=sample_rate,
                ao_min_voltage=ao_voltage_range[0],
                ao_max_voltage=ao_voltage_range[1],
                shunt_resistance=self.sample_resistance,
                amplify_gain=self.amplify_gain,
                channel_resistances=self.config.sample_resistances_ohm,
                channel_gains=self.config.amplify_gains,
            )

            self.worker.point_acquired.connect(self.on_iv_point)
            self.worker.finished.connect(self.on_finished)
            self.worker.error.connect(self.on_error)
            self.running = True
            if self.runtime is not None:
                self.runtime.set("iv", RuntimeStatus.RUNNING)
            self._set_controls_locked(True)
            self.worker.start()
        except Exception as exc:
            self.running = False
            self.worker = None
            self._set_controls_locked(False)
            if self.resources is not None:
                self.resources.release("iv")
            if self.runtime is not None:
                self.runtime.set("iv", RuntimeStatus.ERROR, str(exc))
            log(f"[IV Error] {type(exc).__name__}: {exc}", "error")
            return

        log(f"[IV] Scan started ({len(voltages)} points)")

    # -------------------------

    def stop_scan(self):
        if self.runtime is not None:
            self.runtime.set("iv", RuntimeStatus.STOPPING)
        if self.worker:
            self.worker.stop()
            self.worker.wait()
        self.on_finished()

    # -------------------------
    def on_finished(self):
        if not (self.running or self.worker is not None or self._controls_locked):
            return
        self.running = False
        self.worker = None
        self._set_controls_locked(False)
        if self.resources is not None:
            self.resources.release("iv")
        if self.runtime is not None:
            self.runtime.set("iv", RuntimeStatus.READY)
        # self.plot.set_mode_time()
        log("[IV] Scan finished")

    # -------------------------
    def on_error(self, msg):
        log(f"[IV Error] {msg}", "error")
        self.on_finished()
        if self.runtime is not None:
            self.runtime.set("iv", RuntimeStatus.ERROR, str(msg))

    def on_iv_point(self, ch, voltage, current_mA):
        # 鍘熸湁 IV 缁樺浘
        self.plot.add_iv_point(ch, voltage, current_mA)

        # 鍚屾鏇存柊 LED
        self.led_manager.update_from_currents({
            ch: current_mA
        })

        self.recorder.add_iv_point(ch, voltage, current_mA)

    def _set_controls_locked(self, locked):
        names = [
            "ivModeComboBox",
            "ivRepeatSpinBox",
            "ivStartSpinBox",
            "ivStopSpinBox",
            "ivStepSpinBox",
            "daqDeviceComboBox",
            "aoChannelComboBox",
        ]
        names.extend(f"ai{index}CheckBox" for index in range(16))
        if locked and not self._controls_locked:
            self._control_enabled_snapshot = {}
            for name in names:
                widget = getattr(self.ui, name, None)
                if widget is not None and hasattr(widget, "isEnabled"):
                    self._control_enabled_snapshot[name] = widget.isEnabled()
            self._controls_locked = True
            for name in names:
                widget = getattr(self.ui, name, None)
                if widget is not None and hasattr(widget, "setEnabled"):
                    widget.setEnabled(False)
        elif not locked and self._controls_locked:
            for name, enabled in self._control_enabled_snapshot.items():
                widget = getattr(self.ui, name, None)
                if widget is not None and hasattr(widget, "setEnabled"):
                    widget.setEnabled(enabled)
            self._control_enabled_snapshot = {}
            self._controls_locked = False

