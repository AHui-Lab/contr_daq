import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage


class CameraThread(QThread):
    frame_ready = Signal(QImage)
    TARGET_WIDTH = 640
    TARGET_HEIGHT = 480
    TARGET_FPS = 15

    def __init__(self, cam_index: int):
        super().__init__()
        self.cam_index = cam_index
        self._running = True
        self.cap = None

    def run(self):
        self.cap = cv2.VideoCapture(self.cam_index, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            print(f"Camera {self.cam_index} failed to open")
            while self._running:
                self.msleep(100)
            return

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.TARGET_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.TARGET_HEIGHT)
        self.cap.set(cv2.CAP_PROP_FPS, self.TARGET_FPS)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        while self._running:
            ret, frame = self.cap.read()
            if not ret:
                self.msleep(10)
                continue

            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame.shape
            image = QImage(
                frame.data, w, h, ch * w, QImage.Format_RGB888
            ).copy()

            self.frame_ready.emit(image)
            self.msleep(round(1000 / self.TARGET_FPS))

        self.cap.release()

    def request_stop(self):
        self._running = False

    def stop(self):
        self.request_stop()
        self.wait()
