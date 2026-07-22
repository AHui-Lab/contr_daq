import sys
import types


class DummySignal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)

    def emit(self, *args, **kwargs):
        for callback in self.callbacks:
            callback(*args, **kwargs)


class DummyQt:
    AlignCenter = 1
    KeepAspectRatio = 2
    SmoothTransformation = 3
    FastTransformation = 4


class DummyPixmap:
    scaled_calls = []

    @classmethod
    def fromImage(cls, image):
        pixmap = cls()
        pixmap.image = image
        return pixmap

    def scaled(self, size, aspect_mode, transform_mode):
        self.scaled_calls.append((size, aspect_mode, transform_mode))
        return self


class DummyWidget:
    def __init__(self, *args, **kwargs):
        self.enabled = True
        self.text = ""

    def setEnabled(self, value):
        self.enabled = value


class DummyLabel(DummyWidget):
    def __init__(self, text=""):
        super().__init__()
        self.text = text
        self.pixmaps = []

    def setAlignment(self, value):
        self.alignment = value

    def setMinimumHeight(self, value):
        self.minimum_height = value

    def setStyleSheet(self, value):
        self.stylesheet = value

    def setText(self, value):
        self.text = value

    def size(self):
        return (640, 360)

    def setPixmap(self, pixmap):
        self.pixmaps.append(pixmap)


class DummyComboBox(DummyWidget):
    def __init__(self):
        super().__init__()
        self.items = []
        self.current_index = 0

    def clear(self):
        self.items.clear()

    def addItem(self, label, data):
        self.items.append((label, data))

    def findData(self, data):
        for index, item in enumerate(self.items):
            if item[1] == data:
                return index
        return -1

    def setCurrentIndex(self, index):
        self.current_index = index

    def count(self):
        return len(self.items)

    def currentData(self):
        if not self.items:
            return None
        return self.items[self.current_index][1]


class DummyButton(DummyWidget):
    def __init__(self, text=""):
        super().__init__()
        self.text = text
        self.clicked = DummySignal()

    def setText(self, value):
        self.text = value


class DummyLayout:
    def __init__(self, parent=None):
        self.parent = parent

    def setContentsMargins(self, *args):
        pass

    def setSpacing(self, value):
        pass

    def addWidget(self, widget, stretch=0):
        pass

    def addLayout(self, layout):
        pass


class DummyCapture:
    def __init__(self, index, backend):
        self.index = index

    def isOpened(self):
        return self.index == 0

    def release(self):
        pass


cv2 = types.ModuleType("cv2")
cv2.CAP_DSHOW = 700
cv2.VideoCapture = DummyCapture
sys.modules["cv2"] = cv2

qtcore = types.ModuleType("PySide6.QtCore")
qtcore.Qt = DummyQt
qtcore.QObject = object
qtcore.QThread = object
qtcore.Signal = lambda *args, **kwargs: DummySignal()
qtgui = types.ModuleType("PySide6.QtGui")
qtgui.QPixmap = DummyPixmap
qtwidgets = types.ModuleType("PySide6.QtWidgets")
qtwidgets.QComboBox = DummyComboBox
qtwidgets.QHBoxLayout = DummyLayout
qtwidgets.QLabel = DummyLabel
qtwidgets.QPushButton = DummyButton
qtwidgets.QVBoxLayout = DummyLayout
pyside6 = types.ModuleType("PySide6")
pyside6.QtCore = qtcore
pyside6.QtGui = qtgui
pyside6.QtWidgets = qtwidgets
sys.modules["PySide6"] = pyside6
sys.modules["PySide6.QtCore"] = qtcore
sys.modules["PySide6.QtGui"] = qtgui
sys.modules["PySide6.QtWidgets"] = qtwidgets

class DummyCameraThread:
    def __init__(self, camera_index):
        self.camera_index = camera_index
        self.frame_ready = DummySignal()
        self.opened = DummySignal()
        self.error = DummySignal()
        self.finished = DummySignal()
        self.started = False
        self.stop_called = False
        self.request_stop_called = False

    def start(self):
        self.started = True

    def stop(self):
        self.stop_called = True

    def request_stop(self):
        self.request_stop_called = True


class DummyCameraDiscoveryThread:
    def __init__(self, max_devices):
        self.max_devices = max_devices
        self.devices_ready = DummySignal()
        self.error = DummySignal()
        self.finished = DummySignal()
        self.started = False
        self.request_stop_called = False

    def start(self):
        self.started = True

    def request_stop(self):
        self.request_stop_called = True


camera_thread_module = types.ModuleType("modules.camera.camera_thread")
camera_thread_module.CameraThread = DummyCameraThread
camera_thread_module.CameraDiscoveryThread = DummyCameraDiscoveryThread
sys.modules["modules.camera.camera_thread"] = camera_thread_module

from modules.camera.camera_controller import CameraController


class Clock:
    def __init__(self):
        self.value = 0.0

    def monotonic(self):
        return self.value


def test_camera_preview_uses_fast_transform_and_throttles_main_thread_paints():
    clock = Clock()
    controller = CameraController(object(), clock=clock.monotonic, target_fps=10)

    controller.on_frame("frame-1")
    controller.update_ui()
    controller.on_frame("frame-2")
    clock.value = 0.05
    controller.update_ui()

    assert len(controller.video_label.pixmaps) == 1
    assert DummyPixmap.scaled_calls[-1][2] == DummyQt.FastTransformation

    clock.value = 0.11
    controller.update_ui()

    assert len(controller.video_label.pixmaps) == 2


def test_closing_camera_requests_stop_without_blocking_wait():
    controller = CameraController(object())

    controller.toggle_camera()
    thread = controller.thread
    controller.toggle_camera()

    assert thread.request_stop_called is True
    assert thread.stop_called is False
    assert controller.btn_toggle.enabled is False

    thread.finished.emit()

    assert controller.thread is None
    assert controller.btn_toggle.enabled is True


def test_camera_open_failure_returns_controller_to_retryable_state():
    controller = CameraController(object())

    controller.toggle_camera()
    thread = controller.thread
    thread.error.emit("open failed")
    thread.finished.emit()

    assert controller.thread is None
    assert controller.btn_toggle.enabled is True
    assert "open failed" in controller.video_label.text

    controller.toggle_camera()

    assert controller.thread is not None
    assert controller.thread is not thread


def test_camera_refresh_runs_through_background_discovery_thread():
    controller = CameraController(object())

    controller.scan_cameras()
    discovery = controller.discovery_thread

    assert discovery.started is True
    assert controller.btn_refresh.enabled is False

    discovery.devices_ready.emit([2, 5])
    discovery.finished.emit()

    assert [item[1] for item in controller.camera_combo.items] == [2, 5]
    assert controller.discovery_thread is None
    assert controller.btn_refresh.enabled is True


def test_configured_camera_index_remains_selectable_before_discovery():
    controller = CameraController(object(), default_index=12)

    assert controller.camera_combo.currentData() == 12
