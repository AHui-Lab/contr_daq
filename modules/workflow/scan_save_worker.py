from PySide6.QtCore import QObject, QThread, Signal, Slot


class ScanSaveWorker(QThread):
    """Runs a sealed scan-save operation without blocking the Qt event loop."""

    succeeded = Signal(object)
    failed = Signal(object)

    def __init__(self, operation):
        super().__init__()
        self._operation = operation

    def run(self):
        try:
            self.succeeded.emit(self._operation())
        except Exception as exc:
            self.failed.emit(exc)


class ScanSaveBridge(QObject):
    """Queues worker results onto the GUI thread before invoking UI callbacks."""

    def __init__(self, on_success, on_failure, on_finished):
        super().__init__()
        self._on_success = on_success
        self._on_failure = on_failure
        self._on_finished = on_finished

    @Slot(object)
    def deliver_success(self, payload):
        self._on_success(payload)

    @Slot(object)
    def deliver_failure(self, exc):
        self._on_failure(exc)

    @Slot()
    def deliver_finished(self):
        self._on_finished()
