from PySide6.QtCore import QThread, Signal
import time


class MotionLoopThread(QThread):
    finished = Signal()
    progress = Signal(int)

    def __init__(self, controller, axis, direction, distance, times, gap):
        super().__init__()
        self.controller = controller
        self.axis = axis
        self.direction = direction
        self.distance = distance
        self.times = times
        self.gap = gap
        self._running = True

    def run(self):
        for i in range(self.times):
            if not self._running:
                break

            # 执行一次运动
            self.controller.move_single(self.axis, self.direction, self.distance)

            self.progress.emit(i + 1)

            # 等待间隔（可被急停打断）
            t0 = time.time()
            while time.time() - t0 < self.gap:
                if not self._running:
                    break
                time.sleep(0.05)

        self.finished.emit()

    def stop(self):
        self._running = False
        self.wait()