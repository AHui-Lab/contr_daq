import nidaqmx
from nidaqmx.constants import VoltageUnits

from utils.log import log
from modules.app_runtime import RuntimeStatus, ni_resource
from modules.daq.device_catalog import discover_ni_devices, selected_device_name


class AOController:
    def __init__(self, ui, runtime=None, resources=None, translator=None):
        self.ui = ui
        self.runtime = runtime
        self.resources = resources
        self.translator = translator
        self.task = None
        self.running = False
        self._device_catalog = {}
        self._voltage_ui_minimum = float(self.ui.aoVoltageSpinBox.minimum())
        self._voltage_ui_maximum = float(self.ui.aoVoltageSpinBox.maximum())

        # 初始化 UI
        self.refresh_ao_channels()

        # 信号
        self.ui.aoControlButton.clicked.connect(self.toggle_output)
        self.ui.daqDeviceComboBox.currentIndexChanged.connect(
            self._on_daq_device_changed
        )

    # --------------------------------------------------
    # 枚举 AO 通道
    # --------------------------------------------------
    def refresh_ao_channels(self):
        if self.running:
            return
        selected_device = selected_device_name(self.ui.daqDeviceComboBox)
        previous_channel = self.ui.aoChannelComboBox.currentText()
        self.ui.aoChannelComboBox.clear()

        try:
            devices = discover_ni_devices()
        except Exception as exc:
            log(f"[AO] NI channel discovery failed: {exc}", "error")
            return
        self._device_catalog = {device.name: device for device in devices}
        for device in devices:
            if selected_device and device.name != selected_device:
                continue
            for channel in device.ao_channels:
                self.ui.aoChannelComboBox.addItem(f"{device.name}/{channel}")

        if self.ui.aoChannelComboBox.count() > 0:
            index = self.ui.aoChannelComboBox.findText(previous_channel)
            self.ui.aoChannelComboBox.setCurrentIndex(index if index >= 0 else 0)
        self._apply_voltage_capability(selected_device)

    def _on_daq_device_changed(self, *_args):
        self.refresh_ao_channels()

    def retranslate_ui(self):
        self._apply_voltage_capability(
            selected_device_name(self.ui.daqDeviceComboBox)
        )

    # --------------------------------------------------
    # 按钮状态切换
    # --------------------------------------------------
    def toggle_output(self):
        if not self.running:
            self.start_output()
        else:
            self.stop_output()

    # --------------------------------------------------
    # Start
    # --------------------------------------------------
    def start_output(self):
        channel = self.ui.aoChannelComboBox.currentText()
        voltage = self.ui.aoVoltageSpinBox.value()

        if not channel:
            log("[AO] No channel selected")
            if self.runtime is not None:
                self.runtime.set("ao", RuntimeStatus.WARNING, "No channel selected")
            return

        info = self._device_catalog.get(channel.split("/", 1)[0])
        voltage_range = info.ao_range_for(voltage, voltage) if info is not None else None
        if info is not None and voltage_range is None:
            detail = f"{channel} does not support {voltage:.3f} V"
            log(f"[AO] {detail}", "warning")
            if self.runtime is not None:
                self.runtime.set("ao", RuntimeStatus.WARNING, detail)
            return
        if voltage_range is None:
            voltage_range = (self._voltage_ui_minimum, self._voltage_ui_maximum)

        if self.resources is not None:
            acquired, detail = self.resources.acquire("ao", [ni_resource(channel, "ao")])
            if not acquired:
                log(f"[AO] Start blocked: {detail}", "warning")
                if self.runtime is not None:
                    self.runtime.set("ao", RuntimeStatus.WARNING, detail)
                return

        try:
            self.task = nidaqmx.Task()
            self.task.ao_channels.add_ao_voltage_chan(
                channel,
                min_val=voltage_range[0],
                max_val=voltage_range[1],
                units=VoltageUnits.VOLTS
            )

            self.task.write(voltage)

            # === 状态更新 ===
            self.running = True
            if self.runtime is not None:
                self.runtime.set("ao", RuntimeStatus.RUNNING)
            self.ui.aoChannelComboBox.setDisabled(True)
            self.ui.aoVoltageSpinBox.setDisabled(True)

            log(f"[AO] Output ON: {channel} = {voltage:.3f} V")

        except Exception as e:
            log(f"[AO Error] {type(e).__name__}: {e}", "error")
            self.stop_output()
            if self.runtime is not None:
                self.runtime.set("ao", RuntimeStatus.ERROR, str(e))

    # --------------------------------------------------
    # Stop
    # --------------------------------------------------
    def stop_output(self):
        if self.task:
            try:
                # 保护：拉回 0V
                self.task.write(0.0)
                self.task.stop()
                self.task.close()
            except Exception:
                pass

            self.task = None

        # === 状态恢复 ===
        self.running = False
        if self.resources is not None:
            self.resources.release("ao")
        if self.runtime is not None:
            self.runtime.set("ao", RuntimeStatus.READY)
        self.ui.aoChannelComboBox.setDisabled(False)
        self.ui.aoVoltageSpinBox.setDisabled(False)
        self.refresh_ao_channels()

        log("[AO] Output OFF")

    def _apply_voltage_capability(self, device_name):
        info = self._device_catalog.get(device_name)
        if info is not None and info.ao_voltage_ranges:
            minimum = min(item[0] for item in info.ao_voltage_ranges)
            maximum = max(item[1] for item in info.ao_voltage_ranges)
        else:
            minimum = self._voltage_ui_minimum
            maximum = self._voltage_ui_maximum
        self.ui.aoVoltageSpinBox.setRange(minimum, maximum)
        self.ui.aoVoltageSpinBox.setToolTip(
            self._t("device.ao_range", minimum=minimum, maximum=maximum)
        )

    def _t(self, key, **values):
        if self.translator is None:
            return "AO range: {minimum:g} to {maximum:g} V".format(**values)
        return self.translator(key, **values)
