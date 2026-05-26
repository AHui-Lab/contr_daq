import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "config_force_sensor.py"


def load_config_module():
    spec = importlib.util.spec_from_file_location("config_force_sensor", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_write_single_register_frames_match_manual_examples():
    config = load_config_module()

    assert config.write_single_register_frame(0x0005, 0x5AA5).hex(" ").upper() == (
        "01 10 00 05 00 01 02 5A A5 5C DE"
    )
    assert config.write_single_register_frame(0x0001, 0x0007).hex(" ").upper() == (
        "01 10 00 01 00 01 02 00 07 E6 43"
    )
    assert config.write_single_register_frame(0x0022, 0x0008).hex(" ").upper() == (
        "01 10 00 22 00 01 02 00 08 A1 14"
    )


def test_read_holding_register_frame_matches_four_channel_gross_weight_command():
    config = load_config_module()

    assert config.read_holding_register_frame(0x01C2, 8).hex(" ").upper() == (
        "01 03 01 C2 00 08 E4 0C"
    )


def test_fast_response_profile_contains_expected_sensor_settings():
    config = load_config_module()

    register_values = {
        step.register: step.value
        for step in config.FAST_RESPONSE_PROFILE
        if step.kind == "write_register"
    }

    assert register_values[0x0005] == 0x5AA5
    assert register_values[0x0001] == 0x0007
    assert register_values[0x0022] == 0x0003
    assert register_values[0x0023] == 0x0003
    assert register_values[0x0060] == 0x0000
