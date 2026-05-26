import sys
from pathlib import Path

import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QApplication

from modules.app_state import AppState
from modules.camera.camera_controller import CameraController
from modules.daq.ao_controller import AOController
from modules.daq.daq_controller import DaqController
from modules.daq.daq_plot import DaqPlot
from modules.daq.iv_controller import IVController
from modules.force.force_controller import ForceController
from modules.motion.motion_controller import MotionController
from modules.ui.led_indicator import LedIndicatorManager
from modules.ui.theme import apply_graph_theme, build_stylesheet, patch_led_manager
from modules.ui.view_binder import ViewBinder
from utils.log import bind_log_widget


BASE_DIR = Path(__file__).resolve().parent
UI_FILE = BASE_DIR / "test.ui"


class MainWindow:
    def __init__(self):
        self.ui = QUiLoader().load(str(UI_FILE))
        self.ui.closeEvent = self.closeEvent

        self.ui.setWindowFlag(Qt.Window, True)
        self.ui.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        self.ui.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.ui.setWindowFlag(Qt.WindowCloseButtonHint, True)

        self.view_binder = ViewBinder(self.ui, self.current_state)
        self.view_binder.setup()

        self.camera_controller_1 = CameraController(self.ui.Camera1, default_index=0)
        self.camera_controller_2 = CameraController(self.ui.Camera2, default_index=1)

        self.plot = DaqPlot(self.ui.daqPlotWidget, self.ui)
        self.led_manager = LedIndicatorManager(self.ui, threshold_mA=0.5)
        patch_led_manager(self.led_manager)

        self.daq_controller = DaqController(
            self.ui,
            self.plot,
            self.led_manager,
        )
        self.ao_controller = AOController(self.ui)
        bind_log_widget(self.ui.logTextEdit)

        self.motion_controller = MotionController(self.ui)
        self.force_controller = ForceController(self.ui)
        self.iv_controller = IVController(
            ui=self.ui,
            daq_plot=self.plot,
            led_manager=self.led_manager,
        )
        self.view_binder.refresh_static_text()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_all_ui)
        self.timer.start(30)

    def current_state(self) -> AppState:
        return AppState(
            daq_running=self.daq_controller.thread is not None
            if hasattr(self, "daq_controller")
            else False,
            camera_1_running=self._camera_running("camera_controller_1"),
            camera_2_running=self._camera_running("camera_controller_2"),
            motion_loop_running=self._motion_loop_running(),
            force_running=self.force_controller.running
            if hasattr(self, "force_controller")
            else False,
            recording=self._recording_active(),
        )

    def update_all_ui(self):
        if hasattr(self, "camera_controller_1"):
            self.camera_controller_1.update_ui()

        if hasattr(self, "camera_controller_2"):
            self.camera_controller_2.update_ui()

        if hasattr(self, "force_controller"):
            self.force_controller.update_ui()

        self.view_binder.update_status()

    def closeEvent(self, event):
        for controller_name in ("camera_controller_1", "camera_controller_2"):
            controller = getattr(self, controller_name, None)
            if controller and controller.thread:
                controller.thread.stop()

        if hasattr(self, "daq_controller") and self.daq_controller.thread:
            self.daq_controller.stop()

        if hasattr(self, "force_controller") and self.force_controller.thread:
            self.force_controller.stop()

        event.accept()

    def _camera_running(self, controller_name: str) -> bool:
        controller = getattr(self, controller_name, None)
        return bool(controller and controller.thread)

    def _motion_loop_running(self) -> bool:
        if not hasattr(self, "motion_controller"):
            return False
        thread = self.motion_controller.loop_thread
        return bool(thread and thread.isRunning())

    def _recording_active(self) -> bool:
        for controller_name in ("daq_controller", "force_controller"):
            controller = getattr(self, controller_name, None)
            recorder = getattr(controller, "recorder", None)
            if recorder is not None and recorder.recording:
                return True
        return False


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(build_stylesheet())
    apply_graph_theme(pg)

    window = MainWindow()
    window.ui.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
