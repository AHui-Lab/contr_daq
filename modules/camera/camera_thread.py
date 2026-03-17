import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage
from utils.log import log   # 如果你有统一日志系统（可选）


class CameraThread(QThread):
    frame_ready = Signal(QImage)

    def __init__(self, cam_index: int):
        super().__init__()
        self.cam_index = cam_index
        self._running = True
        self.cap = None

    def run(self):
        self.cap = cv2.VideoCapture(self.cam_index, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            if not self.cap.isOpened():
                print(f"摄像头 {self.cam_index} 未打开")
            while self._running:
                self.msleep(100)  # ⭐ 保持线程活着
            return

        while self._running:
            ret, frame = self.cap.read()
            if not ret:
                continue

            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame.shape
            image = QImage(
                frame.data, w, h, ch * w, QImage.Format_RGB888
            ).copy()  # ⭐ 非常重要：copy()

            self.frame_ready.emit(image)
            self.msleep(40)

        self.cap.release()

    def stop(self):
        self._running = False
        self.wait()
