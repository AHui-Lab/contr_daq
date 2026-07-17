import pytest

from modules.workflow.scan_analysis import build_spatial_scan_analysis


def test_nonuniform_motion_is_mapped_to_led_bins_by_measured_position():
    daq_rows = [
        [index / 100.0, float(index)]
        for index in range(41)
    ]
    motion_rows = [
        [0.0, 0, 0, 0, 0, 0],
        [0.1, 100, 1000, 2, 0, 0],
        [0.2, 700, 6000, 2, 0, 0],
        [0.3, 1600, 9000, 3, 0, 0],
        [0.4, 2000, 4000, 4, 0, 0],
    ]

    analysis = build_spatial_scan_analysis(
        daq_rows=daq_rows,
        motion_rows=motion_rows,
        daq_channels=["ai0"],
        led_count=4,
        led_size_mm=0.5,
        pulses_per_mm=1000,
        direction=1,
        minimum_samples_per_led=1,
    )

    led_indices = [row[5] for row in analysis.spatial_rows]
    sample_counts = [row[3] for row in analysis.led_summary_rows]
    distances = [row[1] for row in analysis.spatial_rows]

    assert analysis.metadata["spatial_mapping_available"] is True
    assert analysis.metadata["led_bins_covered"] == 4
    assert set(led_indices) == {1, 2, 3, 4}
    assert sample_counts[0] > sample_counts[2]
    assert distances == sorted(distances)
    assert analysis.spatial_header[-1] == "ai0"


def test_negative_motion_unwraps_unsigned_controller_position():
    daq_rows = [[0.0, 1.0], [0.1, 2.0], [0.19, 3.0]]
    motion_rows = [
        [0.0, 100, 0, 0, 0, 0],
        [0.1, (1 << 32) - 100, 1000, 2, 0, 0],
        [0.2, (1 << 32) - 400, 0, 0, 0, 0],
    ]

    analysis = build_spatial_scan_analysis(
        daq_rows=daq_rows,
        motion_rows=motion_rows,
        daq_channels=["ai0"],
        led_count=1,
        led_size_mm=0.5,
        pulses_per_mm=1000,
        direction=-1,
        minimum_samples_per_led=1,
    )

    assert analysis.metadata["spatial_mapping_available"] is True
    assert analysis.metadata["measured_scan_distance_mm"] == pytest.approx(0.5)
    assert analysis.spatial_rows[-1][1] == pytest.approx(0.47)
    assert {row[5] for row in analysis.spatial_rows} == {1}


def test_spatial_mapping_reports_missing_motion_telemetry():
    analysis = build_spatial_scan_analysis(
        daq_rows=[[0.0, 1.0]],
        motion_rows=[],
        daq_channels=["ai0"],
        led_count=2,
        led_size_mm=1.0,
        pulses_per_mm=2000,
        direction=1,
    )

    assert analysis.spatial_rows == []
    assert analysis.metadata["spatial_mapping_available"] is False
    assert analysis.metadata["spatial_mapping_warning"] is True
    assert analysis.metadata["missing_led_indices"] == [1, 2]
