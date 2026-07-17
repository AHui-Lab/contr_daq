from modules.daq.device_catalog import (
    NiDeviceInfo,
    capability_tooltip,
    discover_ni_devices,
    selected_device_name,
)


class FakeChannel:
    def __init__(self, name):
        self.name = name


class FakeDevice:
    name = "DevSim"
    product_type = "USB-6009"
    is_simulated = True
    ai_max_single_chan_rate = 48000.9
    ai_max_multi_chan_rate = 48000.4
    ai_simultaneous_sampling_supported = False
    ai_physical_chans = [FakeChannel("DevSim/ai0"), FakeChannel("DevSim/ai1")]
    ao_physical_chans = [FakeChannel("DevSim/ao0")]
    ao_voltage_rngs = [0.0, 5.0]


class FakeSystem:
    devices = [FakeDevice()]


class FakeCombo:
    def __init__(self, text, data=None):
        self._text = text
        self._data = data

    def currentText(self):
        return self._text

    def currentData(self):
        return self._data


def test_discovery_normalizes_physical_channels_and_rates():
    info = discover_ni_devices(FakeSystem())[0]

    assert info.name == "DevSim"
    assert info.display_label == "DevSim · SIM"
    assert info.ai_channels == ("ai0", "ai1")
    assert info.ao_channels == ("ao0",)
    assert info.ao_voltage_ranges == ((0.0, 5.0),)
    assert info.ao_range_for(0.0, 4.5) == (0.0, 5.0)
    assert info.ao_range_for(-1.0, 1.0) is None
    assert info.ai_rate_limit(1) == 48000
    assert info.ai_rate_limit(2) == 24000
    assert info.ai_rate_limit(8) == 6000
    assert info.has_ai_channel("DevSim/ai1")
    assert not info.has_ai_channel("ai2")


def test_simultaneous_sampling_does_not_divide_the_multi_channel_rate():
    info = NiDeviceInfo(
        name="DevSimultaneous",
        product_type="Simultaneous AI",
        is_simulated=False,
        ai_channels=("ai0", "ai1", "ai2", "ai3"),
        ao_channels=(),
        max_single_channel_rate=100000,
        max_multi_channel_rate=100000,
        simultaneous_sampling=True,
    )

    assert info.ai_rate_limit(4) == 100000


def test_combo_uses_raw_item_data_instead_of_presentation_label():
    assert selected_device_name(FakeCombo("DevSim · SIM", "DevSim")) == "DevSim"
    assert selected_device_name(FakeCombo("DevSim · SIM")) == "DevSim"


def test_capability_tooltip_reports_simulation_and_hardware_limits():
    info = NiDeviceInfo(
        name="DevSim",
        product_type="USB-6009",
        is_simulated=True,
        ai_channels=("ai0", "ai1"),
        ao_channels=("ao0",),
        max_single_channel_rate=48000,
        max_multi_channel_rate=24000,
    )

    tooltip = capability_tooltip(info)

    assert "Simulated NI device" in tooltip
    assert "2 AI / 1 AO" in tooltip
    assert "24,000 S/s" in tooltip
