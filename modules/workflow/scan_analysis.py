from dataclasses import dataclass

import numpy as np


UINT32_MODULUS = 1 << 32
UINT32_HALF_RANGE = 1 << 31


@dataclass
class SpatialScanAnalysis:
    spatial_header: list[str]
    spatial_rows: list[list]
    led_summary_header: list[str]
    led_summary_rows: list[list]
    metadata: dict


def build_spatial_scan_analysis(
    daq_rows,
    motion_rows,
    daq_channels,
    led_count,
    led_size_mm,
    pulses_per_mm,
    direction,
    minimum_samples_per_led=20,
):
    led_count = int(led_count)
    led_size_mm = float(led_size_mm)
    pulses_per_mm = float(pulses_per_mm)
    direction = 1 if int(direction) >= 0 else -1
    channel_names = list(daq_channels or [])
    spatial_header = [
        "time_s",
        "distance_mm",
        "position_pulse",
        "speed_mm_s",
        "motion_state",
        "led_index",
        *channel_names,
    ]
    summary_header = [
        "led_index",
        "start_mm",
        "end_mm",
        "sample_count",
        "time_start_s",
        "time_end_s",
        "mean_speed_mm_s",
        "constant_speed_fraction",
        *[f"{name}_mean_v" for name in channel_names],
        *[f"{name}_peak_v" for name in channel_names],
    ]

    invalid_detail = _validate_inputs(
        daq_rows,
        motion_rows,
        led_count,
        led_size_mm,
        pulses_per_mm,
    )
    if invalid_detail:
        return _unavailable_analysis(
            spatial_header,
            summary_header,
            led_count,
            invalid_detail,
        )

    daq = np.asarray(daq_rows, dtype=float)
    motion = np.asarray(motion_rows, dtype=float)
    if daq.ndim == 1:
        daq = daq.reshape(1, -1)
    if motion.ndim == 1:
        motion = motion.reshape(1, -1)

    actual_channel_count = max(0, daq.shape[1] - 1)
    channel_names = _normalized_channel_names(channel_names, actual_channel_count)
    spatial_header = spatial_header[:6] + channel_names
    summary_header = summary_header[:8] + [
        *[f"{name}_mean_v" for name in channel_names],
        *[f"{name}_peak_v" for name in channel_names],
    ]

    motion = motion[np.isfinite(motion[:, 0]) & np.isfinite(motion[:, 1])]
    if len(motion) < 2:
        return _unavailable_analysis(
            spatial_header,
            summary_header,
            led_count,
            "fewer than two valid motion telemetry rows",
        )
    motion = motion[np.argsort(motion[:, 0], kind="stable")]
    unique_times = np.concatenate(([True], np.diff(motion[:, 0]) > 1e-12))
    motion = motion[unique_times]
    if len(motion) < 2:
        return _unavailable_analysis(
            spatial_header,
            summary_header,
            led_count,
            "motion telemetry does not contain a time interval",
        )

    daq = daq[np.isfinite(daq[:, 0])]
    if not len(daq):
        return _unavailable_analysis(
            spatial_header,
            summary_header,
            led_count,
            "DAQ rows do not contain valid timestamps",
        )
    daq = daq[np.argsort(daq[:, 0], kind="stable")]

    motion_times = motion[:, 0]
    raw_positions = np.mod(
        np.rint(motion[:, 1]).astype(np.int64),
        UINT32_MODULUS,
    )
    unwrapped_positions = _unwrap_uint32_positions(raw_positions)
    relative_distance = (
        direction
        * (unwrapped_positions - unwrapped_positions[0])
        / pulses_per_mm
    )
    motion_speeds = np.abs(motion[:, 2]) / pulses_per_mm
    motion_states = np.rint(motion[:, 3]).astype(int)

    daq_times = daq[:, 0]
    interpolated_positions = np.interp(
        daq_times,
        motion_times,
        unwrapped_positions.astype(float),
    )
    interpolated_distance = (
        direction
        * (interpolated_positions - float(unwrapped_positions[0]))
        / pulses_per_mm
    )
    interpolated_speed = np.interp(daq_times, motion_times, motion_speeds)
    nearest_motion_indices = _nearest_indices(motion_times, daq_times)
    interpolated_states = motion_states[nearest_motion_indices]

    scan_distance_mm = led_count * led_size_mm
    position_tolerance = max(1.0 / pulses_per_mm, led_size_mm * 1e-6)
    valid = (
        (daq_times >= motion_times[0])
        & (daq_times <= motion_times[-1])
        & (interpolated_distance >= -position_tolerance)
        & (interpolated_distance <= scan_distance_mm + position_tolerance)
    )
    if not np.any(valid):
        return _unavailable_analysis(
            spatial_header,
            summary_header,
            led_count,
            "no DAQ samples overlap the measured scan travel",
        )

    selected_times = daq_times[valid]
    selected_distance = np.clip(
        interpolated_distance[valid],
        0.0,
        scan_distance_mm,
    )
    selected_positions = interpolated_positions[valid]
    selected_speed = interpolated_speed[valid]
    selected_states = interpolated_states[valid]
    selected_signals = daq[valid, 1:]
    led_indices = np.minimum(
        (selected_distance / led_size_mm).astype(int),
        led_count - 1,
    )

    spatial_rows = [
        [
            float(selected_times[index]),
            float(selected_distance[index]),
            float(selected_positions[index]),
            float(selected_speed[index]),
            int(selected_states[index]),
            int(led_indices[index] + 1),
            *selected_signals[index].tolist(),
        ]
        for index in range(len(selected_times))
    ]

    led_summary_rows = []
    sample_counts = []
    for led_index in range(led_count):
        led_mask = led_indices == led_index
        sample_count = int(np.count_nonzero(led_mask))
        sample_counts.append(sample_count)
        start_mm = led_index * led_size_mm
        end_mm = start_mm + led_size_mm
        if sample_count:
            led_times = selected_times[led_mask]
            led_speeds = selected_speed[led_mask]
            led_states = selected_states[led_mask]
            led_signals = selected_signals[led_mask]
            means = np.mean(led_signals, axis=0).tolist()
            peaks = np.max(led_signals, axis=0).tolist()
            led_summary_rows.append(
                [
                    led_index + 1,
                    start_mm,
                    end_mm,
                    sample_count,
                    float(led_times[0]),
                    float(led_times[-1]),
                    float(np.mean(led_speeds)),
                    float(np.mean(led_states == 3)),
                    *means,
                    *peaks,
                ]
            )
        else:
            led_summary_rows.append(
                [
                    led_index + 1,
                    start_mm,
                    end_mm,
                    0,
                    "",
                    "",
                    "",
                    "",
                    *([""] * (actual_channel_count * 2)),
                ]
            )

    telemetry_gaps = np.diff(motion_times)
    motion_steps = np.abs(np.diff(relative_distance))
    missing_led_indices = [
        index + 1 for index, count in enumerate(sample_counts) if count == 0
    ]
    minimum_actual = min(sample_counts, default=0)
    maximum_actual = max(sample_counts, default=0)
    mean_actual = float(np.mean(sample_counts)) if sample_counts else 0.0
    max_motion_step_mm = float(np.max(motion_steps)) if len(motion_steps) else 0.0
    warnings = []
    if missing_led_indices:
        warnings.append(
            f"{len(missing_led_indices)} LED bins have no DAQ samples"
        )
    if minimum_actual < int(minimum_samples_per_led):
        warnings.append(
            f"minimum {minimum_actual} samples/LED is below "
            f"{int(minimum_samples_per_led)}"
        )
    if max_motion_step_mm > led_size_mm / 2.0:
        warnings.append(
            f"maximum motion telemetry step {max_motion_step_mm:.4f} mm "
            f"exceeds half an LED width"
        )

    metadata = {
        "spatial_mapping_available": True,
        "spatial_mapping_method": "linear interpolation of motion telemetry",
        "spatial_mapping_warning": bool(warnings),
        "spatial_mapping_detail": "; ".join(warnings) or "ok",
        "spatial_leds_distinguishable": not warnings,
        "spatial_rows": len(spatial_rows),
        "led_bins_expected": led_count,
        "led_bins_covered": led_count - len(missing_led_indices),
        "missing_led_indices": missing_led_indices,
        "minimum_samples_per_led_actual": minimum_actual,
        "maximum_samples_per_led_actual": maximum_actual,
        "mean_samples_per_led_actual": mean_actual,
        "motion_telemetry_rows": len(motion),
        "motion_telemetry_mean_gap_s": float(np.mean(telemetry_gaps)),
        "motion_telemetry_max_gap_s": float(np.max(telemetry_gaps)),
        "motion_telemetry_max_step_mm": max_motion_step_mm,
        "measured_scan_distance_mm": float(np.max(relative_distance)),
    }
    return SpatialScanAnalysis(
        spatial_header=spatial_header,
        spatial_rows=spatial_rows,
        led_summary_header=summary_header,
        led_summary_rows=led_summary_rows,
        metadata=metadata,
    )


def _validate_inputs(
    daq_rows,
    motion_rows,
    led_count,
    led_size_mm,
    pulses_per_mm,
):
    if led_count <= 0 or led_size_mm <= 0 or pulses_per_mm <= 0:
        return "invalid LED geometry or motion scale"
    if daq_rows is None or len(daq_rows) == 0:
        return "DAQ stream is empty"
    if motion_rows is None or len(motion_rows) < 2:
        return "motion telemetry is unavailable"
    return ""


def _unavailable_analysis(
    spatial_header,
    summary_header,
    led_count,
    detail,
):
    return SpatialScanAnalysis(
        spatial_header=list(spatial_header),
        spatial_rows=[],
        led_summary_header=list(summary_header),
        led_summary_rows=[],
        metadata={
            "spatial_mapping_available": False,
            "spatial_mapping_method": "linear interpolation of motion telemetry",
            "spatial_mapping_warning": True,
            "spatial_mapping_detail": str(detail),
            "spatial_leds_distinguishable": False,
            "spatial_rows": 0,
            "led_bins_expected": int(led_count),
            "led_bins_covered": 0,
            "missing_led_indices": list(range(1, int(led_count) + 1)),
        },
    )


def _normalized_channel_names(names, count):
    normalized = list(names[:count])
    while len(normalized) < count:
        normalized.append(f"ch{len(normalized) + 1}")
    return normalized


def _unwrap_uint32_positions(raw_positions):
    raw_positions = np.asarray(raw_positions, dtype=np.int64)
    if len(raw_positions) < 2:
        return raw_positions.copy()
    deltas = (
        (np.diff(raw_positions) + UINT32_HALF_RANGE) % UINT32_MODULUS
        - UINT32_HALF_RANGE
    )
    return np.concatenate(
        ([raw_positions[0]], raw_positions[0] + np.cumsum(deltas))
    )


def _nearest_indices(reference_times, query_times):
    right = np.searchsorted(reference_times, query_times, side="left")
    right = np.clip(right, 0, len(reference_times) - 1)
    left = np.clip(right - 1, 0, len(reference_times) - 1)
    use_right = (
        np.abs(reference_times[right] - query_times)
        < np.abs(query_times - reference_times[left])
    )
    return np.where(use_right, right, left)
