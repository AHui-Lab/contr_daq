import queue
from collections import deque

import nidaqmx
import nidaqmx.system

from PySide6.QtWidgets import (
    QApplication, QWidget
)
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import (
    QTimer
)

from PySide6.QtCore import Qt

import pyqtgraph as pg

from modules.camera.camera_controller import CameraController

from modules.daq.daq_controller import DaqController

from modules.daq.ao_controller import AOController

import logging

from utils.log import bind_log_widget

from modules.daq.iv_controller import IVController

from modules.daq.daq_plot import DaqPlot

from modules.motion.motion_controller import MotionController

from modules.force.force_controller import ForceController

from modules.ui.led_indicator import LedIndicatorManager



class MainWindow:
    AI_CHANNELS = [f"ai{i}" for i in range(8)]
    def __init__(self):
        super().__init__()
        self.ui=QUiLoader().load('daq_ui.ui')

        self.ui.setWindowFlag(Qt.Window, True)
        self.ui.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        self.ui.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.ui.setWindowFlag(Qt.WindowCloseButtonHint, True)

        self.ui.setWindowTitle("NI-USB-6259 测试系统")

        self.camera_controller_1 = CameraController(self.ui.Camera1,default_index=0)
        self.camera_controller_2 = CameraController(self.ui.Camera2,default_index=1)
        self.plot = DaqPlot(self.ui.daqPlotWidget,self.ui)
        self.led_manager = LedIndicatorManager(self.ui, threshold_mA=0.5)
        self.daq_controller = DaqController(
            self.ui,
            self.plot,
            self.led_manager
        )
        self.ao_controller = AOController(self.ui)
        bind_log_widget(self.ui.logTextEdit)
        self.motion_controller = MotionController(self.ui)
        self.force_controller = ForceController(self.ui)



        self.iv_controller = IVController(
            ui=self.ui,
            daq_plot=self.plot,  # ⭐ 注意：传的是 DaqPlot
            led_manager=self.led_manager
        )

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_all_ui)
        self.timer.start(30)  # 30ms刷新

    def update_all_ui(self):
        if hasattr(self, "camera_controller_1"):
            self.camera_controller_1.update_ui()

        if hasattr(self, "camera_controller_2"):
            self.camera_controller_2.update_ui()

        if hasattr(self, "force_controller"):
            self.force_controller.update_ui()



    def closeEvent(self, event):
        if self.camera_controller_1.thread:
            self.camera_controller_1.thread.stop()
        if self.camera_controller_2.thread:
            self.camera_controller_2.thread.stop()
        event.accept()


app=QApplication()
Daq=MainWindow()
Daq.ui.show()
app.exec()

