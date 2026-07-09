from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


class SettingsDialog(QDialog):
    def __init__(
        self,
        config,
        on_apply=None,
        on_restart=None,
        on_reset_restart=None,
        parent=None,
    ):
        super().__init__(parent)
        self.config = config
        self.on_apply = on_apply
        self.on_restart = on_restart
        self.on_reset_restart = on_reset_restart
        self.setWindowTitle("运行参数设置")
        self.setMinimumSize(560, 560)

        layout = QVBoxLayout(self)

        general_group = QGroupBox("显示与 LED")
        general_form = QFormLayout(general_group)

        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.0, 100000.0)
        self.threshold_spin.setDecimals(4)
        self.threshold_spin.setSingleStep(0.1)
        self.threshold_spin.setSuffix(" mA")
        general_form.addRow("亮灯阈值电流", self.threshold_spin)

        self.max_points_spin = QSpinBox()
        self.max_points_spin.setRange(100, 200000)
        self.max_points_spin.setSingleStep(500)
        general_form.addRow("曲线最大显示点数", self.max_points_spin)

        self.chunk_interval_spin = QDoubleSpinBox()
        self.chunk_interval_spin.setRange(0.005, 1.0)
        self.chunk_interval_spin.setDecimals(3)
        self.chunk_interval_spin.setSingleStep(0.01)
        self.chunk_interval_spin.setSuffix(" s")
        general_form.addRow("DAQ 每次读取时长", self.chunk_interval_spin)

        layout.addWidget(general_group)

        channel_group = QGroupBox("各通道电流换算")
        channel_layout = QVBoxLayout(channel_group)
        self.channel_table = QTableWidget(self.config.channel_count, 3)
        self.channel_table.setHorizontalHeaderLabels(
            ["通道", "采样电阻 (ohm)", "放大增益"]
        )
        self.channel_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.channel_table.verticalHeader().setVisible(False)
        channel_layout.addWidget(self.channel_table)
        layout.addWidget(channel_group)

        restart_group = QGroupBox("软件重启")
        restart_layout = QVBoxLayout(restart_group)

        self.restart_button = QPushButton("保存当前设置并重启软件")
        self.restart_button.clicked.connect(self._restart)
        restart_layout.addWidget(self.restart_button)

        self.reset_restart_button = QPushButton("恢复默认设置并重启软件")
        self.reset_restart_button.clicked.connect(self._reset_restart)
        restart_layout.addWidget(self.reset_restart_button)

        layout.addWidget(restart_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Apply | QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Apply).clicked.connect(self.apply_settings)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.load_from_config()

    def load_from_config(self):
        self.threshold_spin.setValue(self.config.led_threshold_mA)
        self.max_points_spin.setValue(self.config.max_display_points)
        self.chunk_interval_spin.setValue(self.config.daq_chunk_interval_s)

        for index in range(self.config.channel_count):
            channel_item = QTableWidgetItem(f"ai{index}")
            channel_item.setFlags(channel_item.flags() & ~Qt.ItemIsEditable)
            self.channel_table.setItem(index, 0, channel_item)

            resistance_spin = QDoubleSpinBox()
            resistance_spin.setRange(0.001, 1_000_000.0)
            resistance_spin.setDecimals(4)
            resistance_spin.setValue(self.config.sample_resistances_ohm[index])
            self.channel_table.setCellWidget(index, 1, resistance_spin)

            gain_spin = QDoubleSpinBox()
            gain_spin.setRange(0.001, 1_000_000.0)
            gain_spin.setDecimals(4)
            gain_spin.setValue(self.config.amplify_gains[index])
            self.channel_table.setCellWidget(index, 2, gain_spin)

    def apply_settings(self):
        self.config.led_threshold_mA = self.threshold_spin.value()
        self.config.max_display_points = self.max_points_spin.value()
        self.config.daq_chunk_interval_s = self.chunk_interval_spin.value()

        for index in range(self.config.channel_count):
            resistance_spin = self.channel_table.cellWidget(index, 1)
            gain_spin = self.channel_table.cellWidget(index, 2)
            self.config.sample_resistances_ohm[index] = resistance_spin.value()
            self.config.amplify_gains[index] = gain_spin.value()

        if self.on_apply is not None:
            self.on_apply()

    def _accept(self):
        self.apply_settings()
        self.accept()

    def _restart(self):
        self.apply_settings()
        if self.on_restart is not None:
            self.on_restart()

    def _reset_restart(self):
        if self.on_reset_restart is not None:
            self.on_reset_restart()
