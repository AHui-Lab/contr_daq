import sys
import types

from modules.app_state import AppState


qtcore = types.ModuleType("PySide6.QtCore")
qtwidgets = types.ModuleType("PySide6.QtWidgets")


class DummyQt:
    AlignCenter = 132


class DummySizePolicy:
    Expanding = "expanding"


class DummyLabel:
    def __init__(self):
        self.text = ""
        self.style = ""
        self.alignment = None
        self.minimum_width = None

    def setStyleSheet(self, style):
        self.style = style

    def setAlignment(self, alignment):
        self.alignment = alignment

    def setMinimumWidth(self, width):
        self.minimum_width = width

    def setText(self, text):
        self.text = text


qtcore.Qt = DummyQt
qtwidgets.QLabel = DummyLabel
qtwidgets.QSizePolicy = DummySizePolicy

pyside6 = types.ModuleType("PySide6")
pyside6.QtCore = qtcore
pyside6.QtWidgets = qtwidgets
sys.modules["PySide6"] = pyside6
sys.modules["PySide6.QtCore"] = qtcore
sys.modules["PySide6.QtWidgets"] = qtwidgets

from modules.ui.view_binder import ViewBinder


class DummyTabWidget:
    def __init__(self, count):
        self._count = count
        self.labels = {}

    def count(self):
        return self._count

    def setTabText(self, index, text):
        self.labels[index] = text

    def removeTab(self, index):
        self._count -= 1
        self.labels.pop(index, None)


class DummyGroupBox:
    def __init__(self):
        self.title = ""

    def setTitle(self, title):
        self.title = title


class DummyTextWidget:
    def __init__(self):
        self.text = ""

    def setText(self, text):
        self.text = text


class DummyStatusBar:
    def __init__(self):
        self.message = ""
        self.widgets = []

    def showMessage(self, message):
        self.message = message

    def addPermanentWidget(self, widget):
        self.widgets.append(widget)


class DummyLayout:
    def __init__(self):
        self.margins = None
        self.spacing = None

    def setContentsMargins(self, *margins):
        self.margins = margins

    def setSpacing(self, spacing):
        self.spacing = spacing


class DummySurface:
    def __init__(self):
        self.policy = None

    def setSizePolicy(self, horizontal, vertical):
        self.policy = (horizontal, vertical)


class DummyUi:
    def __init__(self):
        self.title = ""
        self.minimum_size = None
        self._status_bar = DummyStatusBar()
        self.tabWidget = DummyTabWidget(2)
        self.tabWidget_2 = DummyTabWidget(1)
        self.tabWidget_3 = DummyTabWidget(1)
        self.tabWidget_4 = DummyTabWidget(2)
        self.groupBox = DummyGroupBox()
        self.groupBox_2 = DummyGroupBox()
        self.groupBox_4 = DummyGroupBox()
        self.groupBox_5 = DummyGroupBox()
        self.groupBox_6 = DummyGroupBox()
        self.groupBox_7 = DummyGroupBox()
        self.startStopButton = DummyTextWidget()
        self.aoControlButton = DummyTextWidget()
        self.Emergency_Stop = DummyTextWidget()
        self.totalForceLabel = DummyTextWidget()
        self.Force1_Label = DummyTextWidget()
        self.Force2_Label = DummyTextWidget()
        self.Force3_Label = DummyTextWidget()
        self.Force4_Label = DummyTextWidget()
        self.gridLayout_3 = DummyLayout()
        self.daqPlotWidget = DummySurface()
        self.forcePlotWidget = DummySurface()
        self.Camera1 = DummySurface()
        self.Camera2 = DummySurface()

    def setWindowTitle(self, title):
        self.title = title

    def setMinimumSize(self, width, height):
        self.minimum_size = (width, height)

    def statusBar(self):
        return self._status_bar


def test_setup_names_workbench_sections_and_status_bar():
    ui = DummyUi()
    binder = ViewBinder(ui, lambda: AppState(daq_running=True, recording=True))

    binder.setup()

    assert ui.title == "NI-USB-6259 Control Workbench"
    assert ui.minimum_size == (1280, 820)
    assert ui.tabWidget.labels == {0: "Camera 1", 1: "Camera 2"}
    assert ui.tabWidget_4.labels == {0: "DAQ", 1: "IV"}
    assert ui.groupBox.title == "Acquisition Control"
    assert ui.groupBox_7.title == "Channel Activity"
    assert ui.startStopButton.text == "Start DAQ"
    assert ui.Emergency_Stop.text == "Emergency Stop"
    assert ui.statusBar().message == "Workbench ready"
    assert len(ui.statusBar().widgets) == 5
    assert binder.status_labels["daq"].text == "DAQ: Sampling"
    assert binder.status_labels["recording"].text == "RECORDING: On"


def test_setup_removes_unused_placeholder_tabs_and_defaults_force_labels():
    ui = DummyUi()
    binder = ViewBinder(ui, lambda: AppState())

    binder.setup()

    assert ui.tabWidget_2.count() == 1
    assert ui.tabWidget_3.count() == 1
    assert ui.totalForceLabel.text == "Total: 0.00 N"
    assert ui.Force1_Label.text == "P1: 0.00"
