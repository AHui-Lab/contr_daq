from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules.ui.i18n import SUPPORTED_LANGUAGES, Translator


class SettingsDialog(QDialog):
    def __init__(
        self,
        config,
        translator=None,
        on_apply=None,
        on_restart=None,
        on_reset_restart=None,
        parent=None,
    ):
        super().__init__(parent)
        self.config = config
        self.translator = translator or Translator(config.ui_language)
        self.on_apply = on_apply
        self.on_restart = on_restart
        self.on_reset_restart = on_reset_restart
        self.setMinimumSize(640, 700)

        layout = QVBoxLayout(self)

        self.interface_group = QGroupBox()
        self.interface_form = QFormLayout(self.interface_group)
        self.language_combo = QComboBox()
        for language in SUPPORTED_LANGUAGES:
            self.language_combo.addItem("", language)
        self.language_label = QLabel()
        self.interface_form.addRow(self.language_label, self.language_combo)
        layout.addWidget(self.interface_group)

        self.general_group = QGroupBox()
        self.general_form = QFormLayout(self.general_group)

        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.0, 100000.0)
        self.threshold_spin.setDecimals(4)
        self.threshold_spin.setSingleStep(0.1)
        self.threshold_spin.setSuffix(" mA")
        self.threshold_label = QLabel()
        self.general_form.addRow(self.threshold_label, self.threshold_spin)

        self.max_points_spin = QSpinBox()
        self.max_points_spin.setRange(100, 200000)
        self.max_points_spin.setSingleStep(500)
        self.max_points_label = QLabel()
        self.general_form.addRow(self.max_points_label, self.max_points_spin)

        self.chunk_interval_spin = QDoubleSpinBox()
        self.chunk_interval_spin.setRange(0.005, 1.0)
        self.chunk_interval_spin.setDecimals(3)
        self.chunk_interval_spin.setSingleStep(0.01)
        self.chunk_interval_spin.setSuffix(" s")
        self.chunk_interval_label = QLabel()
        self.general_form.addRow(self.chunk_interval_label, self.chunk_interval_spin)
        layout.addWidget(self.general_group)

        self.data_group = QGroupBox()
        self.data_form = QFormLayout(self.data_group)
        self.operator_edit = QLineEdit()
        self.operator_label = QLabel()
        self.data_form.addRow(self.operator_label, self.operator_edit)

        self.output_dir_row = QWidget()
        output_dir_layout = QHBoxLayout(self.output_dir_row)
        output_dir_layout.setContentsMargins(0, 0, 0, 0)
        output_dir_layout.setSpacing(6)
        self.output_dir_edit = QLineEdit()
        self.output_dir_browse = QPushButton()
        self.output_dir_browse.clicked.connect(self._browse_output_dir)
        output_dir_layout.addWidget(self.output_dir_edit, 1)
        output_dir_layout.addWidget(self.output_dir_browse)
        self.output_dir_label = QLabel()
        self.data_form.addRow(self.output_dir_label, self.output_dir_row)
        layout.addWidget(self.data_group)

        self.channel_group = QGroupBox()
        channel_layout = QVBoxLayout(self.channel_group)
        self.channel_table = QTableWidget(self.config.channel_count, 3)
        self.channel_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.channel_table.verticalHeader().setVisible(False)
        channel_layout.addWidget(self.channel_table)
        layout.addWidget(self.channel_group)

        self.restart_group = QGroupBox()
        restart_layout = QVBoxLayout(self.restart_group)
        self.restart_button = QPushButton()
        self.restart_button.clicked.connect(self._restart)
        restart_layout.addWidget(self.restart_button)
        self.reset_restart_button = QPushButton()
        self.reset_restart_button.clicked.connect(self._reset_restart)
        restart_layout.addWidget(self.reset_restart_button)
        layout.addWidget(self.restart_group)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.Apply | QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self.buttons.button(QDialogButtonBox.Apply).clicked.connect(self.apply_settings)
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.load_from_config()
        self.retranslate_ui()

    def retranslate_ui(self):
        t = self.translator
        self.setWindowTitle(t("settings.title"))
        self.interface_group.setTitle(t("settings.interface_group"))
        self.language_label.setText(t("settings.language"))
        self.general_group.setTitle(t("settings.display_group"))
        self.threshold_label.setText(t("settings.led_threshold"))
        self.max_points_label.setText(t("settings.max_points"))
        self.chunk_interval_label.setText(t("settings.chunk_interval"))
        self.data_group.setTitle(t("settings.data_group"))
        self.operator_label.setText(t("settings.operator"))
        self.output_dir_label.setText(t("settings.output_dir"))
        self.output_dir_browse.setText(t("settings.browse"))
        self.channel_group.setTitle(t("settings.channels_group"))
        self.channel_table.setHorizontalHeaderLabels(
            [t("settings.channel"), t("settings.resistance"), t("settings.gain")]
        )
        self.restart_group.setTitle(t("settings.restart_group"))
        self.restart_button.setText(t("settings.restart"))
        self.reset_restart_button.setText(t("settings.reset_restart"))
        self.buttons.button(QDialogButtonBox.Apply).setText(t("settings.apply"))
        self.buttons.button(QDialogButtonBox.Ok).setText(t("settings.ok"))
        self.buttons.button(QDialogButtonBox.Cancel).setText(t("settings.cancel"))

        for index in range(self.language_combo.count()):
            language = self.language_combo.itemData(index)
            self.language_combo.setItemText(index, t(f"language.{language}"))

    def load_from_config(self):
        self.threshold_spin.setValue(self.config.led_threshold_mA)
        self.max_points_spin.setValue(self.config.max_display_points)
        self.chunk_interval_spin.setValue(self.config.daq_chunk_interval_s)
        self.operator_edit.setText(self.config.operator_name)
        self.output_dir_edit.setText(self.config.data_save_dir)
        language_index = self.language_combo.findData(self.config.ui_language)
        self.language_combo.setCurrentIndex(max(language_index, 0))

        for index in range(self.config.channel_count):
            channel_item = QTableWidgetItem(f"ai{index}")
            channel_item.setFlags(channel_item.flags() & ~Qt.ItemIsEditable)
            self.channel_table.setItem(index, 0, channel_item)

            resistance_spin = self.channel_table.cellWidget(index, 1)
            if resistance_spin is None:
                resistance_spin = QDoubleSpinBox()
                resistance_spin.setRange(0.001, 1_000_000.0)
                resistance_spin.setDecimals(4)
                self.channel_table.setCellWidget(index, 1, resistance_spin)
            resistance_spin.setValue(self.config.sample_resistances_ohm[index])

            gain_spin = self.channel_table.cellWidget(index, 2)
            if gain_spin is None:
                gain_spin = QDoubleSpinBox()
                gain_spin.setRange(0.001, 1_000_000.0)
                gain_spin.setDecimals(4)
                self.channel_table.setCellWidget(index, 2, gain_spin)
            gain_spin.setValue(self.config.amplify_gains[index])

    def apply_settings(self):
        self.config.ui_language = self.language_combo.currentData() or "en"
        self.config.led_threshold_mA = self.threshold_spin.value()
        self.config.max_display_points = self.max_points_spin.value()
        self.config.daq_chunk_interval_s = self.chunk_interval_spin.value()
        self.config.operator_name = self.operator_edit.text().strip()
        self.config.data_save_dir = self.output_dir_edit.text().strip() or "data"

        for index in range(self.config.channel_count):
            self.config.sample_resistances_ohm[index] = self.channel_table.cellWidget(index, 1).value()
            self.config.amplify_gains[index] = self.channel_table.cellWidget(index, 2).value()

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

    def _browse_output_dir(self):
        directory = QFileDialog.getExistingDirectory(
            self,
            self.translator("settings.select_output_dir"),
            self.output_dir_edit.text() or "data",
        )
        if directory:
            self.output_dir_edit.setText(directory)
