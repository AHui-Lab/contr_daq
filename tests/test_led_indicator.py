from modules.ui.led_indicator import LedIndicatorManager
from modules.app_config import AppConfig


class DummyLed:
    def __init__(self):
        self.style = ""

    def setStyleSheet(self, style):
        self.style = style


class DummyUi:
    def __init__(self):
        for index in range(16):
            setattr(self, f"led{index}Widget", DummyLed())


def test_led_indicator_displays_channel_16_on_left_and_channel_1_on_right():
    ui = DummyUi()
    manager = LedIndicatorManager(ui, threshold_mA=0.5)

    manager.update_from_currents({"ai0": 1.0, "ai15": 1.0})

    assert "#2196F3" in ui.led15Widget.style
    assert "#2196F3" in ui.led0Widget.style
    assert manager.channel_to_led_index(0) == 15
    assert manager.channel_to_led_index(15) == 0


def test_led_indicator_ignores_out_of_range_channels():
    ui = DummyUi()
    manager = LedIndicatorManager(ui, threshold_mA=0.5)

    manager.update_from_currents({"ai16": 1.0, "bad": 1.0})

    assert all("#2196F3" not in getattr(ui, f"led{index}Widget").style for index in range(16))


def test_led_indicator_reads_runtime_threshold_from_config():
    ui = DummyUi()
    config = AppConfig(led_threshold_mA=2.0)
    manager = LedIndicatorManager(ui, config=config)

    manager.update_from_currents({"ai0": 1.0})
    assert "#2196F3" not in ui.led15Widget.style

    config.led_threshold_mA = 0.5
    manager.apply_config()
    manager.update_from_currents({"ai0": 1.0})

    assert "#2196F3" in ui.led15Widget.style
