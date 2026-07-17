import sys
from pathlib import Path

import pyqtgraph as pg
from PySide6.QtCore import QProcess, Qt
from PySide6.QtUiTools import QUiLoader
from PySide6.QtWidgets import QApplication

from modules.app_config import AppConfig
from modules.app_runtime import ResourceArbiter, RuntimeStateStore
from modules.app_state import AppState
from modules.camera.camera_controller import CameraController
from modules.daq.ao_controller import AOController
from modules.daq.daq_controller import DaqController
from modules.daq.daq_plot import DaqPlot
from modules.daq.iv_controller import IVController
from modules.force.force_controller import ForceController
from modules.motion.motion_controller import MotionController
from modules.recorder.data_recorder import DataRecorder
from modules.ui.led_indicator import LedIndicatorManager
from modules.ui.fonts import load_application_fonts
from modules.ui.i18n import Translator
from modules.ui.settings_dialog import SettingsDialog
from modules.ui.theme import apply_graph_theme, build_stylesheet, patch_led_manager
from modules.ui.update_scheduler import UiUpdateScheduler
from modules.ui.view_binder import ViewBinder
from modules.workflow.led_scan import LedScanWorkflow
from utils.log import bind_log_widget, log


BASE_DIR = Path(__file__).resolve().parent
ORIGINAL_UI_FILE = BASE_DIR / "test.ui"
UI_FILE = BASE_DIR / "test_optimized.ui"
CONFIG_FILE = BASE_DIR / "config.json"


class MainWindow:
    def __init__(self):
        self.config = AppConfig.load(CONFIG_FILE)
        self.translator = Translator(self.config.ui_language)
        self.runtime = RuntimeStateStore()
        self.resources = ResourceArbiter()
        self.ui = QUiLoader().load(str(UI_FILE))
        self.ui.closeEvent = self.closeEvent

        self.ui.setWindowFlag(Qt.Window, True)
        self.ui.setWindowFlag(Qt.WindowMinimizeButtonHint, True)
        self.ui.setWindowFlag(Qt.WindowMaximizeButtonHint, True)
        self.ui.setWindowFlag(Qt.WindowCloseButtonHint, True)

        self.view_binder = ViewBinder(
            self.ui,
            self.current_state,
            translator=self.translator,
            runtime=self.runtime,
        )
        self.view_binder.setup()
        self._settings_dialog = None

        self.camera_controller_1 = CameraController(
            self.ui.Camera1,
            default_index=0,
            translator=self.translator,
            runtime=self.runtime,
            subsystem="camera_1",
        )
        self.camera_controller_2 = CameraController(
            self.ui.Camera2,
            default_index=1,
            translator=self.translator,
            runtime=self.runtime,
            subsystem="camera_2",
        )

        self.plot = DaqPlot(
            self.ui.daqPlotWidget,
            self.ui,
            config=self.config,
            translator=self.translator,
        )
        self.led_manager = LedIndicatorManager(self.ui, config=self.config)
        patch_led_manager(self.led_manager)
        self.recorder = DataRecorder(save_dir=self.config.data_save_dir)

        self.daq_controller = DaqController(
            self.ui,
            self.plot,
            self.led_manager,
            recorder=self.recorder,
            config=self.config,
            runtime=self.runtime,
            resources=self.resources,
            translator=self.translator,
        )
        self.ao_controller = AOController(
            self.ui,
            runtime=self.runtime,
            resources=self.resources,
            translator=self.translator,
        )
        bind_log_widget(self.ui.logTextEdit)

        self.motion_controller = MotionController(self.ui, runtime=self.runtime)
        self.force_controller = ForceController(
            self.ui,
            recorder=self.recorder,
            config=self.config,
            runtime=self.runtime,
            resources=self.resources,
            translator=self.translator,
        )
        self.iv_controller = IVController(
            ui=self.ui,
            daq_plot=self.plot,
            led_manager=self.led_manager,
            recorder=self.recorder,
            config=self.config,
            runtime=self.runtime,
            resources=self.resources,
        )
        self.scan_workflow = LedScanWorkflow(
            ui=self.ui,
            motion_controller=self.motion_controller,
            daq_controller=self.daq_controller,
            force_controller=self.force_controller,
            recorder=self.recorder,
            config=self.config,
            runtime=self.runtime,
            translator=self.translator,
        )
        self._build_settings_menu()
        self.view_binder.refresh_static_text()

        self.update_scheduler = UiUpdateScheduler(
            camera_callback=self.update_camera_ui,
            plot_callback=self.update_plot_ui,
            status_callback=self.update_status_ui,
        )
        self.update_scheduler.start()

    def _build_settings_menu(self):
        self.settings_menu = self.ui.menuBar().addMenu(self.translator("menu.settings"))
        self.settings_action = self.settings_menu.addAction(
            self.translator("menu.runtime_settings")
        )
        self.settings_action.triggered.connect(self.open_settings)

    def open_settings(self):
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(
                self.config,
                translator=self.translator,
                on_apply=self.apply_runtime_settings,
                on_restart=self.restart_application,
                on_reset_restart=self.reset_defaults_and_restart,
                parent=self.ui,
            )
        self._settings_dialog.load_from_config()
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def apply_runtime_settings(self):
        language_changed = self.translator.set_language(self.config.ui_language)
        self.config.save(CONFIG_FILE)
        try:
            self.recorder.set_save_dir(self.config.data_save_dir)
        except OSError as exc:
            log(f"[Settings] Output folder unavailable: {exc}", "error")
        self.led_manager.apply_config()
        self.plot.apply_config()
        self.force_controller.apply_config()
        if language_changed:
            self._retranslate_ui()

    def _retranslate_ui(self):
        self.settings_menu.setTitle(self.translator("menu.settings"))
        self.settings_action.setText(self.translator("menu.runtime_settings"))
        if hasattr(self, "scan_workflow"):
            self.scan_workflow.retranslate_ui()
        self.view_binder.refresh_static_text()
        self.camera_controller_1.retranslate_ui()
        self.camera_controller_2.retranslate_ui()
        self.plot.retranslate_ui()
        self.force_controller.plot.retranslate_ui()
        self.daq_controller.retranslate_ui()
        self.ao_controller.retranslate_ui()
        self.force_controller.retranslate_ui()
        if self._settings_dialog is not None:
            self._settings_dialog.retranslate_ui()

    def reset_defaults_and_restart(self):
        self.config.reset_to_defaults()
        self.apply_runtime_settings()
        force_controller = getattr(self, "force_controller", None)
        if force_controller is not None:
            force_controller.reset_runtime_state()
        self.restart_application(save_config=False)

    def restart_application(self, save_config=True):
        if save_config:
            self.apply_runtime_settings()

        self._stop_runtime_for_restart()
        program, arguments = self._restart_command()
        working_directory = str(BASE_DIR)

        if QProcess.startDetached(program, arguments, working_directory):
            QApplication.quit()
        else:
            print("[App] restart failed")

    def _restart_command(self):
        if getattr(sys, "frozen", False):
            return sys.executable, sys.argv[1:]

        script = str(Path(sys.argv[0]).resolve())
        return sys.executable, [script, *sys.argv[1:]]

    def current_state(self) -> AppState:
        return AppState(
            daq_running=self.daq_controller.thread is not None
            if hasattr(self, "daq_controller")
            else False,
            ao_running=self.ao_controller.running
            if hasattr(self, "ao_controller")
            else False,
            iv_running=self.iv_controller.running
            if hasattr(self, "iv_controller")
            else False,
            camera_1_running=self._camera_running("camera_controller_1"),
            camera_2_running=self._camera_running("camera_controller_2"),
            motion_running=self._motion_running(),
            force_running=self.force_controller.running
            if hasattr(self, "force_controller")
            else False,
            recording=self._recording_active(),
        )

    def update_all_ui(self):
        self.update_camera_ui()
        self.update_plot_ui()
        self.update_status_ui()

    def update_camera_ui(self):
        if hasattr(self, "camera_controller_1"):
            self.camera_controller_1.update_ui()

        if hasattr(self, "camera_controller_2"):
            self.camera_controller_2.update_ui()

    def update_plot_ui(self):
        if hasattr(self, "daq_controller"):
            self.daq_controller.update_ui()

        if hasattr(self, "force_controller"):
            self.force_controller.update_ui()

    def update_status_ui(self):
        if hasattr(self, "scan_workflow"):
            self.scan_workflow.refresh_readiness(preserve_result=True)
        self.view_binder.update_status()

    def closeEvent(self, event):
        self._stop_runtime_for_restart()
        event.accept()

    def _stop_runtime_for_restart(self):
        scan_workflow = getattr(self, "scan_workflow", None)
        if scan_workflow is not None:
            scan_workflow.wait_for_save()

        for controller_name in ("camera_controller_1", "camera_controller_2"):
            controller = getattr(self, controller_name, None)
            if controller and controller.thread:
                controller.thread.stop()

        if hasattr(self, "daq_controller") and self.daq_controller.thread:
            self.daq_controller.stop()

        if hasattr(self, "iv_controller") and self.iv_controller.running:
            self.iv_controller.stop_scan()

        if hasattr(self, "ao_controller") and self.ao_controller.running:
            self.ao_controller.stop_output()

        if hasattr(self, "force_controller") and self.force_controller.thread:
            self.force_controller.stop()

        if hasattr(self, "motion_controller"):
            self.motion_controller.shutdown()

        if hasattr(self, "recorder") and self.recorder.recording:
            self.recorder.stop()

    def _camera_running(self, controller_name: str) -> bool:
        controller = getattr(self, controller_name, None)
        return bool(controller and controller.thread)

    def _motion_running(self) -> bool:
        if not hasattr(self, "motion_controller"):
            return False
        return self.motion_controller.scan_running

    def _recording_active(self) -> bool:
        recorder = getattr(self, "recorder", None)
        return bool(recorder and recorder.recording)


def main() -> int:
    app = QApplication(sys.argv)
    load_application_fonts(app)
    app.setStyleSheet(build_stylesheet())
    apply_graph_theme(pg)

    window = MainWindow()
    window.ui.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
