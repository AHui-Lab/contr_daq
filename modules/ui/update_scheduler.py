from PySide6.QtCore import QTimer


class UiUpdateScheduler:
    CAMERA_INTERVAL_MS = 66
    PLOT_INTERVAL_MS = 33
    STATUS_INTERVAL_MS = 250

    def __init__(self, camera_callback, plot_callback, status_callback, timer_factory=QTimer):
        self._timers = [
            self._make_timer(timer_factory, camera_callback, self.CAMERA_INTERVAL_MS),
            self._make_timer(timer_factory, plot_callback, self.PLOT_INTERVAL_MS),
            self._make_timer(timer_factory, status_callback, self.STATUS_INTERVAL_MS),
        ]

    def start(self):
        for timer, interval in self._timers:
            timer.start(interval)

    def _make_timer(self, timer_factory, callback, interval):
        timer = timer_factory()
        timer.timeout.connect(callback)
        return timer, interval
