import nidaqmx
from nidaqmx.system import System
from nidaqmx.constants import VoltageUnits

from utils.log import log


class AOController:
    def __init__(self, ui):
        self.ui = ui
        self.task = None
        self.running = False

        # 初始化 UI
        self.refresh_ao_channels()
        self.ui.aoControlButton.setText("开始输出")

        # 信号
        self.ui.aoControlButton.clicked.connect(self.toggle_output)

    # --------------------------------------------------
    # 枚举 AO 通道
    # --------------------------------------------------
    def refresh_ao_channels(self):
        self.ui.aoChannelComboBox.clear()

        system = System.local()
        for dev in system.devices:
            for ch in dev.ao_physical_chans:
                self.ui.aoChannelComboBox.addItem(ch.name)

        if self.ui.aoChannelComboBox.count() > 0:
            self.ui.aoChannelComboBox.setCurrentIndex(0)

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
            return

        try:
            self.task = nidaqmx.Task()
            self.task.ao_channels.add_ao_voltage_chan(
                channel,
                units=VoltageUnits.VOLTS
            )

            self.task.write(voltage)

            # === 状态更新 ===
            self.running = True
            self.ui.aoControlButton.setText("停止输出")
            self.ui.aoChannelComboBox.setDisabled(True)
            self.ui.aoVoltageSpinBox.setDisabled(True)

            log(f"[AO] Output ON: {channel} = {voltage:.3f} V")

        except Exception as e:
            log("[AO Error]", e)
            self.stop_output()

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
        self.ui.aoControlButton.setText("开始输出")
        self.ui.aoChannelComboBox.setDisabled(False)
        self.ui.aoVoltageSpinBox.setDisabled(False)

        log("[AO] Output OFF")
