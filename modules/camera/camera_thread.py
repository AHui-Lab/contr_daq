import cv2
from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage


class CameraThread(QThread):
    frame_ready = Signal(QImage)
    opened = Signal()
    error = Signal(str)
    TARGET_WIDTH = 640
    TARGET_HEIGHT = 480
    TARGET_FPS = 15
    MAX_CONSECUTIVE_READ_FAILURES = 15

    def __init__(self, cam_index: int):
        super().__init__()
        self.cam_index = cam_index
        self._running = True
        self.cap = None

    def run(self):
        consecutive_failures = 0
        try:
            self.cap = cv2.VideoCapture(self.cam_index, cv2.CAP_DSHOW)
            if not self.cap.isOpened():
                detail = f"Camera {self.cam_index} failed to open"
                print(detail)
                self.error.emit(detail)
                return

            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.TARGET_WIDTH)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.TARGET_HEIGHT)
            self.cap.set(cv2.CAP_PROP_FPS, self.TARGET_FPS)
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            self.opened.emit()

            while self._running:
                ret, frame = self.cap.read()
                if not ret:
                    consecutive_failures += 1
                    if consecutive_failures >= self.MAX_CONSECUTIVE_READ_FAILURES:
                        self.error.emit(
                            f"Camera {self.cam_index} stopped returning frames"
                        )
                        return
                    self.msleep(20)
                    continue

                consecutive_failures = 0
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame.shape
                image = QImage(
                    frame.data, w, h, ch * w, QImage.Format_RGB888
                ).copy()

                self.frame_ready.emit(image)
                self.msleep(round(1000 / self.TARGET_FPS))
        except Exception as exc:
            self.error.emit(
                f"Camera {self.cam_index} error: {type(exc).__name__}: {exc}"
            )
        finally:
            if self.cap is not None:
                self.cap.release()
            self.cap = None

    def request_stop(self):
        self._running = False

    def stop(self):
        self.request_stop()
        self.wait()


class CameraDiscoveryThread(QThread):
    """Probe camera indices away from the GUI thread."""

    devices_ready = Signal(list)
    error = Signal(str)

    def __init__(self, max_devices=8):
        super().__init__()
        self.max_devices = max(1, int(max_devices))
        self._running = True

    def run(self):
        devices = []
        try:
            for index in range(self.max_devices):
                if not self._running:
                    return
                cap = None
                try:
                    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
                    if cap.isOpened():
                        devices.append(index)
                finally:
                    if cap is not None:
                        cap.release()
            if self._running:
                self.devices_ready.emit(devices)
        except Exception as exc:
            self.error.emit(f"Camera discovery failed: {type(exc).__name__}: {exc}")

    def request_stop(self):
        self._running = False
