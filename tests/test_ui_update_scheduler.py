import sys
import types


class DummySignal:
    def __init__(self):
        self.callback = None

    def connect(self, callback):
        self.callback = callback

    def emit(self, *args, **kwargs):
        if self.callback:
            self.callback(*args, **kwargs)


class DummyTimer:
    created = []

    def __init__(self):
        self.timeout = DummySignal()
        self.interval = None
        DummyTimer.created.append(self)

    def start(self, interval):
        self.interval = interval


qtcore = types.ModuleType("PySide6.QtCore")
qtcore.QTimer = DummyTimer
qtcore.QThread = object
qtcore.QObject = object
qtcore.Signal = lambda *args, **kwargs: DummySignal()
pyside6 = types.ModuleType("PySide6")
pyside6.QtCore = qtcore
sys.modules["PySide6"] = pyside6
sys.modules["PySide6.QtCore"] = qtcore

from modules.ui.update_scheduler import UiUpdateScheduler


def test_ui_update_scheduler_uses_separate_refresh_intervals():
    calls = []

    scheduler = UiUpdateScheduler(
        camera_callback=lambda: calls.append("camera"),
        plot_callback=lambda: calls.append("plot"),
        status_callback=lambda: calls.append("status"),
    )

    scheduler.start()

    assert [timer.interval for timer in DummyTimer.created] == [66, 100, 250]

    for timer in DummyTimer.created:
        timer.timeout.callback()

    assert calls == ["camera", "plot", "status"]
