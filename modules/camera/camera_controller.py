import cv2
from PySide6.QtWidgets import QLabel, QVBoxLayout, QPushButton, QComboBox
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt
from .camera_thread import CameraThread
from utils.log import log   # 如果你有统一日志系统（可选）


class CameraController:
    def __init__(self, parent_widget, default_index=0):
        self.default_index = default_index
        self.parent = parent_widget

        self.latest_frame = None

        # ===== UI =====
        self.video_label = QLabel("相机未开启")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("background:black;color:white;")

        self.camera_combo = QComboBox()
        self.btn_toggle = QPushButton("打开相机")

        layout = QVBoxLayout(self.parent)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.video_label)
        layout.addWidget(self.camera_combo)
        layout.addWidget(self.btn_toggle)

        # ===== State =====
        self.thread = None

        self.btn_toggle.clicked.connect(self.toggle_camera)
        self.scan_cameras()

    # ---------- 枚举相机 ----------
    def scan_cameras(self):
        self.camera_combo.clear()
        for i in range(4):  # ⭐ 多扫几个
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                self.camera_combo.addItem(f"Camera {i}", i)
                cap.release()

        # ⭐ 自动选默认相机
        index = self.camera_combo.findData(self.default_index)
        if index >= 0:
            self.camera_combo.setCurrentIndex(index)

    # ---------- 打开 / 关闭 ----------
    def toggle_camera(self):
        if self.thread is None:
            cam_index = self.camera_combo.currentData()
            self.thread = CameraThread(cam_index)
            self.thread.frame_ready.connect(self.on_frame)
            self.thread.start()
            self.btn_toggle.setText("关闭相机")
        else:
            self.thread.stop()
            self.thread = None
            self.video_label.setText("相机未开启")
            self.btn_toggle.setText("打开相机")

    # ---------- UI 更新（主线程） ----------
    def on_frame(self, image):
        self.latest_frame = image

    def update_ui(self):
        if self.latest_frame is None:
            return
        frame = self.latest_frame
        self.latest_frame = None  # ⭐ 只显示最新帧（防堆积）
        self.video_label.setPixmap(QPixmap.fromImage(frame))


