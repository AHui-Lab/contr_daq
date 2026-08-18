import time
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from modules.ui.theme import CAMERA_PREVIEW_STYLE
from modules.app_runtime import RuntimeStatus
from modules.ui.i18n import Translator

from .camera_thread import CameraDiscoveryThread, CameraThread


class CameraController:
    CAMERA_SCAN_LIMIT = 8

    def __init__(self, parent_widget, default_index=0, clock=None, target_fps=15, translator=None, runtime=None, subsystem=None):
        self.default_index = default_index
        self.parent = parent_widget
        self.latest_frame = None
        self.clock = clock or time.monotonic
        self.paint_interval = 1.0 / max(float(target_fps), 1.0)
        self.last_paint_time = None
        self.translator = translator or Translator("en")
        self.runtime = runtime
        self.subsystem = subsystem or f"camera_{default_index + 1}"

        self.video_label = QLabel(self.translator("camera.idle"))
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumHeight(220)
        self.video_label.setStyleSheet(CAMERA_PREVIEW_STYLE)

        self.camera_combo = QComboBox()
        self.btn_toggle = QPushButton(self.translator("button.camera.open"))
        self.btn_refresh = QPushButton(self.translator("button.camera.refresh"))

        layout = QVBoxLayout(self.parent)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)
        layout.addWidget(self.video_label)
        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(6)
        controls.addWidget(self.camera_combo, 1)
        controls.addWidget(self.btn_refresh)
        controls.addWidget(self.btn_toggle)
        layout.addLayout(controls)

        self.thread = None
        self.discovery_thread = None
        self._last_error = ""

        self.btn_toggle.clicked.connect(self.toggle_camera)
        self.btn_refresh.clicked.connect(self.scan_cameras)
        self._set_camera_choices(
            [*range(self.CAMERA_SCAN_LIMIT), self.default_index],
            self.default_index,
        )
        if self.runtime is not None:
            self.runtime.set(self.subsystem, RuntimeStatus.READY)

    def scan_cameras(self):
        if self.thread is not None or self.discovery_thread is not None:
            return
        self.video_label.setText(self.translator("camera.scanning"))
        self.btn_refresh.setEnabled(False)
        self.discovery_thread = CameraDiscoveryThread(self.CAMERA_SCAN_LIMIT)
        self.discovery_thread.devices_ready.connect(self._on_cameras_discovered)
        self.discovery_thread.error.connect(self._on_discovery_error)
        self.discovery_thread.finished.connect(self._on_discovery_finished)
        self.discovery_thread.start()

    def _on_cameras_discovered(self, indices):
        current = self.camera_combo.currentData()
        preferred = self.default_index if current is None else int(current)
        self._set_camera_choices(indices, preferred)
        if not indices:
            self.video_label.setText(self.translator("camera.none"))
            if self.runtime is not None:
                self.runtime.set(self.subsystem, RuntimeStatus.DISCONNECTED)
        else:
            self.video_label.setText(self.translator("camera.idle"))
            if self.runtime is not None:
                self.runtime.set(self.subsystem, RuntimeStatus.READY)

    def _on_discovery_error(self, detail):
        self.video_label.setText(
            self.translator("camera.discovery_failed", detail=str(detail))
        )
        if self.runtime is not None:
            self.runtime.set(self.subsystem, RuntimeStatus.ERROR, str(detail))

    def _on_discovery_finished(self):
        self.discovery_thread = None
        self.btn_refresh.setEnabled(self.thread is None)

    def _set_camera_choices(self, indices, preferred_index=None):
        unique_indices = sorted({max(int(index), 0) for index in indices})
        self.camera_combo.clear()
        for index in unique_indices:
            self.camera_combo.addItem(f"Camera {index}", index)
        selected = self.camera_combo.findData(preferred_index)
        if selected < 0 and self.camera_combo.count() > 0:
            selected = 0
        if selected >= 0:
            self.camera_combo.setCurrentIndex(selected)
        self.btn_toggle.setEnabled(self.camera_combo.count() > 0 and self.thread is None)

    def set_preferred_index(self, camera_index):
        self.default_index = max(int(camera_index), 0)
        selected = self.camera_combo.findData(self.default_index)
        if selected < 0:
            self.camera_combo.addItem(f"Camera {self.default_index}", self.default_index)
            selected = self.camera_combo.findData(self.default_index)
        if self.thread is None and selected >= 0:
            self.camera_combo.setCurrentIndex(selected)

    def toggle_camera(self):
        if self.thread is None:
            camera_index = self.camera_combo.currentData()
            if camera_index is None:
                self.video_label.setText(self.translator("camera.not_selected"))
                return

            self.thread = CameraThread(camera_index)
            self.thread.frame_ready.connect(self.on_frame)
            self.thread.finished.connect(self.on_thread_finished)
            opened_signal = getattr(self.thread, "opened", None)
            if opened_signal is not None:
                opened_signal.connect(self.on_camera_opened)
            error_signal = getattr(self.thread, "error", None)
            if error_signal is not None:
                error_signal.connect(self.on_camera_error)
            self._last_error = ""
            self.thread.start()
            self.btn_toggle.setText(self.translator("button.camera.close"))
            if self.runtime is not None:
                self.runtime.set(self.subsystem, RuntimeStatus.CONNECTING)
            self.camera_combo.setEnabled(False)
            self.btn_refresh.setEnabled(False)
        else:
            self.btn_toggle.setEnabled(False)
            self.btn_toggle.setText(self.translator("button.camera.closing"))
            if self.runtime is not None:
                self.runtime.set(self.subsystem, RuntimeStatus.STOPPING)
            self.thread.request_stop()

    def on_camera_opened(self):
        self.video_label.setText(self.translator("camera.opened"))
        if self.runtime is not None:
            self.runtime.set(self.subsystem, RuntimeStatus.RUNNING)

    def on_camera_error(self, detail):
        self._last_error = str(detail)
        self.video_label.setText(
            self.translator("camera.stream_failed", detail=self._last_error)
        )
        if self.runtime is not None:
            self.runtime.set(self.subsystem, RuntimeStatus.ERROR, self._last_error)

    def on_frame(self, image):
        self.latest_frame = image

    def on_thread_finished(self):
        self.thread = None
        self.latest_frame = None
        if self._last_error:
            self.video_label.setText(
                self.translator("camera.stream_failed", detail=self._last_error)
            )
        else:
            self.video_label.setText(self.translator("camera.idle"))
        self.btn_toggle.setText(self.translator("button.camera.open"))
        self.btn_toggle.setEnabled(self.camera_combo.count() > 0)
        self.btn_refresh.setEnabled(True)
        self.camera_combo.setEnabled(True)
        if self.runtime is not None:
            if self._last_error:
                self.runtime.set(
                    self.subsystem,
                    RuntimeStatus.ERROR,
                    self._last_error,
                )
            else:
                self.runtime.set(self.subsystem, RuntimeStatus.READY)

    def retranslate_ui(self):
        if self.thread is None:
            self.video_label.setText(
                self.translator("camera.none")
                if self.camera_combo.count() == 0
                else self.translator("camera.idle")
            )
            self.btn_toggle.setText(self.translator("button.camera.open"))
        else:
            self.btn_toggle.setText(self.translator("button.camera.close"))
        self.btn_refresh.setText(self.translator("button.camera.refresh"))

    def shutdown(self):
        if self.discovery_thread is not None:
            self.discovery_thread.request_stop()
            if hasattr(self.discovery_thread, "wait"):
                self.discovery_thread.wait()
        if self.thread is not None:
            self.thread.stop()

    def update_ui(self):
        if self.latest_frame is None:
            return

        now = self.clock()
        if self.last_paint_time is not None and now - self.last_paint_time < self.paint_interval:
            return

        frame = self.latest_frame
        self.latest_frame = None
        self.last_paint_time = now
        pixmap = QPixmap.fromImage(frame)
        self.video_label.setPixmap(
            pixmap.scaled(
                self.video_label.size(),
                Qt.KeepAspectRatio,
                Qt.FastTransformation,
            )
        )
