import cv2
import time
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QComboBox, QLabel, QPushButton, QVBoxLayout

from modules.ui.theme import CAMERA_PREVIEW_STYLE

from .camera_thread import CameraThread


class CameraController:
    def __init__(self, parent_widget, default_index=0, clock=None, target_fps=15):
        self.default_index = default_index
        self.parent = parent_widget
        self.latest_frame = None
        self.clock = clock or time.monotonic
        self.paint_interval = 1.0 / max(float(target_fps), 1.0)
        self.last_paint_time = None

        self.video_label = QLabel("Camera idle")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumHeight(220)
        self.video_label.setStyleSheet(CAMERA_PREVIEW_STYLE)

        self.camera_combo = QComboBox()
        self.btn_toggle = QPushButton("Open Camera")

        layout = QVBoxLayout(self.parent)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)
        layout.addWidget(self.video_label)
        layout.addWidget(self.camera_combo)
        layout.addWidget(self.btn_toggle)

        self.thread = None

        self.btn_toggle.clicked.connect(self.toggle_camera)
        self.scan_cameras()

    def scan_cameras(self):
        self.camera_combo.clear()
        for index in range(4):
            cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
            if cap.isOpened():
                self.camera_combo.addItem(f"Camera {index}", index)
                cap.release()

        selected_index = self.camera_combo.findData(self.default_index)
        if selected_index >= 0:
            self.camera_combo.setCurrentIndex(selected_index)

        has_camera = self.camera_combo.count() > 0
        self.btn_toggle.setEnabled(has_camera)
        if not has_camera:
            self.video_label.setText("No camera detected")

    def toggle_camera(self):
        if self.thread is None:
            camera_index = self.camera_combo.currentData()
            if camera_index is None:
                self.video_label.setText("No camera selected")
                return

            self.thread = CameraThread(camera_index)
            self.thread.frame_ready.connect(self.on_frame)
            self.thread.finished.connect(self.on_thread_finished)
            self.thread.start()
            self.btn_toggle.setText("Close Camera")
            self.camera_combo.setEnabled(False)
        else:
            self.btn_toggle.setEnabled(False)
            self.btn_toggle.setText("Closing Camera")
            self.thread.request_stop()

    def on_frame(self, image):
        self.latest_frame = image

    def on_thread_finished(self):
        self.thread = None
        self.latest_frame = None
        self.video_label.setText("Camera idle")
        self.btn_toggle.setText("Open Camera")
        self.btn_toggle.setEnabled(True)
        self.camera_combo.setEnabled(True)

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
