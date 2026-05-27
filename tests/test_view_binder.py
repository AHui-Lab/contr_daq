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
        self.style = ""
        self.minimum_width = None
        self.maximum_width = None
        self.minimum_height = None
        self.maximum_height = None

    def count(self):
        return self._count

    def setTabText(self, index, text):
        self.labels[index] = text

    def removeTab(self, index):
        self._count -= 1
        self.labels.pop(index, None)

    def setStyleSheet(self, style):
        self.style = style

    def setMaximumHeight(self, height):
        self.maximum_height = height

    def setMinimumHeight(self, height):
        self.minimum_height = height

    def setMinimumWidth(self, width):
        self.minimum_width = width

    def setMaximumWidth(self, width):
        self.maximum_width = width


class DummyGroupBox:
    def __init__(self):
        self.title = ""
        self.style = ""
        self.minimum_height = None
        self.maximum_height = None

    def setTitle(self, title):
        self.title = title

    def setStyleSheet(self, style):
        self.style = style

    def setMinimumHeight(self, height):
        self.minimum_height = height

    def setMaximumHeight(self, height):
        self.maximum_height = height


class DummyTextWidget:
    def __init__(self):
        self.text = ""
        self.minimum_width = None
        self.minimum_height = None
        self.maximum_width = None
        self.maximum_height = None
        self.visible = True

    def setText(self, text):
        self.text = text

    def setMinimumWidth(self, width):
        self.minimum_width = width

    def setMinimumHeight(self, height):
        self.minimum_height = height

    def setMaximumWidth(self, width):
        self.maximum_width = width

    def setMaximumHeight(self, height):
        self.maximum_height = height

    def setVisible(self, visible):
        self.visible = visible


class DummyComboBox(DummyTextWidget):
    def __init__(self, items):
        super().__init__()
        self.items = items
        self.current_index = 0

    def findText(self, text):
        try:
            return self.items.index(text)
        except ValueError:
            return -1

    def setCurrentIndex(self, index):
        self.current_index = index

    def currentText(self):
        return self.items[self.current_index]


class DummySpinBox(DummyTextWidget):
    def __init__(self, value=0):
        super().__init__()
        self.value = value

    def setValue(self, value):
        self.value = value


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
        self.widgets = {}
        self.column_stretches = {}
        self.row_stretches = {}
        self.row_minimum_heights = {}

    def setContentsMargins(self, *margins):
        self.margins = margins

    def setSpacing(self, spacing):
        self.spacing = spacing

    def removeWidget(self, widget):
        for key, value in list(self.widgets.items()):
            if value is widget:
                self.widgets.pop(key)

    def addWidget(self, widget, row, column, row_span=None, column_span=None):
        if row_span is None or column_span is None:
            self.widgets[(row, column)] = widget
            self.last_add_args = (widget, row, column)
        else:
            self.widgets[(row, column, row_span, column_span)] = widget
            self.last_add_args = (widget, row, column, row_span, column_span)

    def setColumnStretch(self, column, stretch):
        self.column_stretches[column] = stretch

    def setRowStretch(self, row, stretch):
        self.row_stretches[row] = stretch

    def setRowMinimumHeight(self, row, height):
        self.row_minimum_heights[row] = height


class DummySurface:
    def __init__(self):
        self.policy = None
        self.minimum_height = None

    def setSizePolicy(self, horizontal, vertical):
        self.policy = (horizontal, vertical)

    def setMinimumHeight(self, height):
        self.minimum_height = height


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
        self.recorderStartButton = DummyTextWidget()
        self.recorderStopButton = DummyTextWidget()
        self.forceStartButton = DummyTextWidget()
        self.forceZeroButton = DummyTextWidget()
        self.Emergency_Stop = DummyTextWidget()
        self.forceModeLabel = DummyTextWidget()
        self.forceModeComboBox = DummyComboBox(["Serial Modbus", "Analog Voltage"])
        self.forceDeviceLabel = DummyTextWidget()
        self.forceDeviceComboBox = DummyTextWidget()
        self.forceSampleRateLabel = DummyTextWidget()
        self.forceSampleRateSpinBox = DummySpinBox(1000)
        self.forceTerminalConfigLabel = DummyTextWidget()
        self.forceTerminalConfigComboBox = DummyComboBox(["RSE", "NRSE", "DIFFERENTIAL"])
        self.forceVoltageRangeLabel = DummyTextWidget()
        self.forceVoltageRangeComboBox = DummyTextWidget()
        self.forceFullScaleLabel = DummyTextWidget()
        self.forceFullScaleSpinBox = DummyTextWidget()
        self.totalForceLabel = DummyTextWidget()
        self.Force1_Label = DummyTextWidget()
        self.Force2_Label = DummyTextWidget()
        self.Force3_Label = DummyTextWidget()
        self.Force4_Label = DummyTextWidget()
        for index in range(16):
            setattr(self, f"ai{index}CheckBox", DummyTextWidget())
        self.Axis_choice = DummyTextWidget()
        self.direction_choice = DummyTextWidget()
        self.distanceSpinBox_2 = DummyTextWidget()
        self.Gap_time = DummyTextWidget()
        self.Circle_times = DummyTextWidget()
        self.Speed_Setting_val = DummyTextWidget()
        self.Forward_circle = DummyTextWidget()
        self.Backward_circle = DummyTextWidget()
        self.label_13 = DummyTextWidget()
        self.logTextEdit = DummyTextWidget()
        self.gridLayout_3 = DummyLayout()
        self.gridLayout_6 = DummyLayout()
        self.gridLayout_11 = DummyLayout()
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
    assert ui.Emergency_Stop.text == "STOP"
    assert ui.forceDeviceLabel.text == "Dev"
    assert ui.forceVoltageRangeLabel.text == "Range"
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
    assert ui.Force1_Label.text == "P1: 0.00 N"
    assert ui.forceModeComboBox.currentText() == "Analog Voltage"
    assert ui.forceTerminalConfigComboBox.currentText() == "DIFFERENTIAL"
    assert ui.forceSampleRateSpinBox.value == 2000


def test_setup_keeps_channel_and_force_controls_readable():
    ui = DummyUi()
    binder = ViewBinder(ui, lambda: AppState())

    binder.setup()

    assert 120 <= ui.groupBox_2.minimum_height <= 135
    assert 225 <= ui.groupBox_4.minimum_height <= 240
    assert 240 <= ui.groupBox_4.maximum_height <= 255
    assert 100 <= ui.daqPlotWidget.minimum_height <= 115
    assert 95 <= ui.forcePlotWidget.minimum_height <= 110
    assert ui.groupBox_5.minimum_height >= 170
    assert ui.groupBox_5.maximum_height <= 185
    assert ui.groupBox_6.minimum_height >= 300
    assert ui.totalForceLabel.minimum_width == 120
    assert ui.totalForceLabel.maximum_width == 120
    assert ui.Force1_Label.minimum_width == 88
    assert ui.Force1_Label.maximum_width == 88
    assert ui.Force1_Label.minimum_height == 22
    assert ui.Force4_Label.minimum_width == 88
    assert ui.Force4_Label.maximum_width == 88
    assert ui.Force4_Label.minimum_height == 22


def test_setup_keeps_ai_channel_checkboxes_legible():
    ui = DummyUi()
    binder = ViewBinder(ui, lambda: AppState())

    binder.setup()

    for index in range(16):
        checkbox = getattr(ui, f"ai{index}CheckBox")
        assert checkbox.minimum_width == 72
        assert checkbox.maximum_width == 16777215
        assert checkbox.minimum_height == 20


def test_setup_compacts_force_panel_into_tool_rows():
    ui = DummyUi()
    binder = ViewBinder(ui, lambda: AppState())

    binder.setup()

    assert ui.gridLayout_6.widgets[(0, 1)] is ui.forceModeComboBox
    assert ui.gridLayout_6.widgets[(3, 0)] is ui.forceStartButton
    assert ui.gridLayout_6.widgets[(2, 1)] is ui.forceVoltageRangeComboBox
    assert ui.gridLayout_6.widgets[(3, 2)] is ui.totalForceLabel
    assert ui.gridLayout_6.widgets[(4, 0)] is ui.Force1_Label
    assert ui.gridLayout_6.widgets[(4, 3)] is ui.Force4_Label


def test_setup_compacts_motion_loop_panel_without_hidden_lower_rows():
    ui = DummyUi()
    binder = ViewBinder(ui, lambda: AppState())

    binder.setup()

    assert ui.gridLayout_11.widgets[(0, 0)] is ui.Axis_choice
    assert ui.gridLayout_11.widgets[(0, 1)] is ui.direction_choice
    assert ui.gridLayout_11.widgets[(1, 0)] is ui.distanceSpinBox_2
    assert ui.gridLayout_11.widgets[(1, 1)] is ui.Gap_time
    assert ui.gridLayout_11.widgets[(2, 0)] is ui.Circle_times
    assert ui.gridLayout_11.widgets[(2, 1)] is ui.label_13
    assert ui.gridLayout_11.widgets[(3, 0)] is ui.Forward_circle
    assert ui.gridLayout_11.widgets[(3, 1)] is ui.Speed_Setting_val
    assert ui.gridLayout_11.widgets[(4, 0)] is ui.Backward_circle
    assert ui.gridLayout_11.widgets[(5, 0, 1, 2)] is ui.Emergency_Stop
    assert ui.label_13.visible is True
    assert ui.Forward_circle.minimum_height == 30
    assert ui.Backward_circle.minimum_height == 30
    assert ui.gridLayout_11.row_stretches[6] == 1
    assert all(ui.gridLayout_11.row_stretches[row] == 0 for row in range(6))
    assert all(ui.gridLayout_11.row_minimum_heights[row] == 0 for row in range(9))


def test_setup_prioritizes_camera_and_keeps_motion_as_sidebar():
    ui = DummyUi()
    binder = ViewBinder(ui, lambda: AppState())

    binder.setup()

    assert 560 <= ui.tabWidget.minimum_width <= 620
    assert ui.tabWidget.minimum_height >= 640
    assert ui.tabWidget_3.minimum_width >= 360
    assert ui.tabWidget_3.maximum_width <= 430
    assert ui.gridLayout_3.last_add_args == (ui.tabWidget_3, 0, 2, 3, 1)
    assert ui.logTextEdit.visible is False
