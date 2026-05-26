import numpy as np
import pytest

from modules.force.analog_force import AnalogForceConfig, convert_voltages_to_force


def test_convert_voltages_to_force_maps_selected_voltage_range_to_full_scale():
    config = AnalogForceConfig(voltage_range="0-10V", full_scale_force=100.0)

    values = convert_voltages_to_force([0.0, 2.5, 5.0, 10.0], config)

    assert values.tolist() == [0.0, 25.0, 50.0, 100.0]


def test_convert_voltages_to_force_supports_five_volt_outputs():
    config = AnalogForceConfig(voltage_range="0-5V", full_scale_force=50.0)

    values = convert_voltages_to_force([0.0, 1.25, 2.5, 5.0], config)

    assert values.tolist() == [0.0, 12.5, 25.0, 50.0]


def test_convert_voltages_to_force_preserves_signed_bipolar_voltage_outputs():
    config = AnalogForceConfig(voltage_range="-10-10V", full_scale_force=100.0)

    values = convert_voltages_to_force([-10.0, -5.0, 0.0, 10.0], config)

    assert values.tolist() == [-100.0, -50.0, 0.0, 100.0]


def test_convert_voltages_to_force_rejects_unknown_range():
    config = AnalogForceConfig(voltage_range="custom", full_scale_force=100.0)

    with pytest.raises(ValueError, match="Unsupported analog force voltage range"):
        convert_voltages_to_force([1.0], config)


def test_convert_voltages_to_force_accepts_numpy_rows():
    config = AnalogForceConfig(voltage_range="0-10V", full_scale_force=20.0)

    values = convert_voltages_to_force(np.array([1.0, 2.0, 3.0, 4.0]), config)

    assert values.tolist() == [2.0, 4.0, 6.0, 8.0]
