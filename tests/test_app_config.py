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
        force_serial_port="COM7",
        force_serial_baudrate=19200,
        force_safety_total_high_n=12.5,
        force_safety_retract_enabled=True,
        force_commission_z_step_mm=0.0005,
        force_commission_verify_distance_mm=0.003,
        force_commission_verify_delta_n=0.3,
        camera_1_index=2,
        camera_2_index=5,
    )
    config.sample_resistances_ohm[0] = 220.0
    config.amplify_gains[0] = 8.0

    config.save(path)
    loaded = AppConfig.load(path)

    assert loaded.led_threshold_mA == pytest.approx(3.5)
    assert loaded.max_display_points == 1200
    assert loaded.operator_name == "Operator A"
    assert loaded.data_save_dir == "D:/experiment-data"
    assert loaded.force_serial_port == "COM7"
    assert loaded.force_serial_baudrate == 19200
    assert loaded.force_safety_total_high_n == pytest.approx(12.5)
    assert loaded.force_safety_retract_enabled is True
    assert loaded.force_commission_z_step_mm == pytest.approx(0.0005)
    assert loaded.force_commission_verify_distance_mm == pytest.approx(0.003)
    assert loaded.force_commission_verify_delta_n == pytest.approx(0.3)
    assert loaded.camera_1_index == 2
    assert loaded.camera_2_index == 5
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


def test_force_verification_settings_are_bounded_for_safe_quantized_measurement():
    config = AppConfig(
        force_commission_verify_distance_mm=1.0,
        force_commission_verify_delta_n=0.02,
    )

    assert config.force_commission_verify_distance_mm == pytest.approx(0.01)
    assert config.force_commission_verify_delta_n == pytest.approx(0.1)
