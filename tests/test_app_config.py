import pytest

from modules.app_config import AppConfig


def test_current_conversion_uses_per_channel_resistance_and_gain():
    config = AppConfig(
        sample_resistances_ohm=[100.0 for _ in range(16)],
        amplify_gains=[5.0 for _ in range(16)],
    )
    config.sample_resistances_ohm[3] = 200.0
    config.amplify_gains[3] = 10.0

    assert config.current_mA("ai0", 1.0) == pytest.approx(2.0)
    assert config.current_mA("ai3", 1.0) == pytest.approx(0.5)


def test_daq_chunk_size_scales_with_sample_rate_and_is_bounded():
    config = AppConfig(daq_chunk_interval_s=0.05)

    assert config.daq_chunk_size(1000) == 100
    assert config.daq_chunk_size(100000) == 5000
    assert config.daq_chunk_size(1_000_000) == 10000


def test_config_can_be_saved_and_loaded(tmp_path):
    path = tmp_path / "config.json"
    config = AppConfig(
        led_threshold_mA=3.5,
        max_display_points=1200,
        operator_name="Operator A",
        data_save_dir="D:/experiment-data",
    )
    config.sample_resistances_ohm[0] = 220.0
    config.amplify_gains[0] = 8.0

    config.save(path)
    loaded = AppConfig.load(path)

    assert loaded.led_threshold_mA == pytest.approx(3.5)
    assert loaded.max_display_points == 1200
    assert loaded.operator_name == "Operator A"
    assert loaded.data_save_dir == "D:/experiment-data"
    assert loaded.sample_resistances_ohm[0] == pytest.approx(220.0)
    assert loaded.amplify_gains[0] == pytest.approx(8.0)


def test_config_can_reset_to_defaults():
    config = AppConfig(led_threshold_mA=9.0, max_display_points=999)
    config.sample_resistances_ohm[0] = 220.0

    config.reset_to_defaults()

    assert config.led_threshold_mA == pytest.approx(AppConfig().led_threshold_mA)
    assert config.max_display_points == AppConfig().max_display_points
    assert config.sample_resistances_ohm[0] == pytest.approx(
        AppConfig().default_sample_resistance_ohm
    )


def test_empty_output_directory_falls_back_to_data():
    config = AppConfig(operator_name="  User  ", data_save_dir="  ")

    assert config.operator_name == "User"
    assert config.data_save_dir == "data"
