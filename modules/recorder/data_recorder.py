import csv
import json
import os
import time
from datetime import datetime
from threading import RLock

import numpy as np


class DataRecorder:
    def __init__(self, save_dir="data"):
        self._lock = RLock()
        self.recording = False
        self.saving = False
        self.save_dir = save_dir
        os.makedirs(self.save_dir, exist_ok=True)
        self.group_id = 0
        self.reset_buffer()

    def reset_buffer(self):
        self.start_time = None
        self.daq_buffer = []
        self.force_buffer = []
        self.force_voltage_buffer = []
        self.iv_buffer = []
        self.motion_buffer = []
        self.spatial_header = []
        self.spatial_buffer = []
        self.led_summary_header = []
        self.led_summary_buffer = []
        self.daq_channels = []
        self.daq_sample_index = 0
        self.force_sample_index = 0
        self.force_voltage_sample_index = 0
        self.metadata = {}
        self.capture_end_clock = None
        self._clock = "wall"

    def start(self, metadata=None, start_monotonic=None):
        with self._lock:
            if self.recording or self.saving:
                return False

            self.recording = True
            self.group_id += 1
            self.reset_buffer()

            self._clock = "monotonic" if start_monotonic is not None else "wall"
            self.start_time = (
                float(start_monotonic)
                if start_monotonic is not None
                else time.time()
            )
            self.metadata = dict(metadata or {})
            print(f"[Recorder] Start recording group {self.group_id}")
            return True

    def stop(self):
        if not self.seal():
            return
        return self.save_sealed()

    def seal(self):
        with self._lock:
            if not self.recording:
                return False

            self.recording = False
            self.saving = True
            print(f"[Recorder] Stop recording group {self.group_id}")
            return True

    def save_sealed(self):
        try:
            return self.save()
        finally:
            self.cancel_save()

    def cancel_save(self):
        with self._lock:
            self.saving = False

    def set_capture_end(self, end_monotonic):
        with self._lock:
            self.capture_end_clock = float(end_monotonic)
            if self.start_time is None:
                return
            cutoff = self.capture_end_clock - self.start_time
            self.daq_buffer = [
                row for row in self.daq_buffer if float(row[0]) <= cutoff + 1e-9
            ]
            self.force_buffer = [
                row for row in self.force_buffer if float(row[0]) <= cutoff + 1e-9
            ]
            self.force_voltage_buffer = [
                row
                for row in self.force_voltage_buffer
                if float(row[0]) <= cutoff + 1e-9
            ]
            self.motion_buffer = [
                row for row in self.motion_buffer if float(row[0]) <= cutoff + 1e-9
            ]

    def update_metadata(self, values):
        with self._lock:
            self.metadata.update(dict(values))

    def set_save_dir(self, save_dir):
        path = os.fspath(save_dir or "data")
        with self._lock:
            if self.recording or self.saving:
                return False
            os.makedirs(path, exist_ok=True)
            self.save_dir = path
            return True

    def set_spatial_scan(self, analysis):
        with self._lock:
            self.spatial_header = list(analysis.spatial_header)
            self.spatial_buffer = [list(row) for row in analysis.spatial_rows]
            self.led_summary_header = list(analysis.led_summary_header)
            self.led_summary_buffer = [
                list(row) for row in analysis.led_summary_rows
            ]

    def add_daq_data(self, voltages):
        with self._lock:
            if not self.recording:
                return

            t = time.time() - self.start_time
            self.daq_buffer.append([t] + list(voltages))

    def add_daq_chunk(
        self,
        rows,
        sample_rate,
        channels=None,
        source_start_monotonic=None,
    ):
        rows = np.asarray(rows)
        if rows.size == 0:
            return
        if rows.ndim == 1:
            rows = rows.reshape(1, -1)

        with self._lock:
            if not self.recording:
                return

            if channels is not None:
                self.daq_channels = list(channels)

            count = len(rows)
            if source_start_monotonic is None:
                times = (
                    np.arange(self.daq_sample_index, self.daq_sample_index + count)
                    / sample_rate
                )
                selected_rows = rows
            else:
                absolute_times = (
                    float(source_start_monotonic)
                    + np.arange(count) / sample_rate
                )
                mask = self._capture_mask(absolute_times)
                times = absolute_times[mask] - self.start_time
                selected_rows = rows[mask]
            if len(selected_rows):
                self.daq_buffer.extend(
                    np.hstack((times.reshape(-1, 1), selected_rows)).tolist()
                )
            self.daq_sample_index += count

    def add_force_data(self, total_force, vals, source_monotonic=None):
        with self._lock:
            if not self.recording:
                return

            clock = time.time() if source_monotonic is None else float(source_monotonic)
            if not self._within_capture(clock):
                return
            t = clock - self.start_time
            self.force_buffer.append([t, total_force] + list(vals))

    def add_force_chunk(self, rows, sample_rate, source_start_monotonic=None):
        rows = np.asarray(rows)
        if rows.size == 0:
            return
        if rows.ndim == 1:
            rows = rows.reshape(1, -1)

        with self._lock:
            if not self.recording:
                return

            count = len(rows)
            if source_start_monotonic is None:
                times = (
                    np.arange(self.force_sample_index, self.force_sample_index + count)
                    / sample_rate
                )
                selected_rows = rows
            else:
                absolute_times = (
                    float(source_start_monotonic)
                    + np.arange(count) / sample_rate
                )
                mask = self._capture_mask(absolute_times)
                times = absolute_times[mask] - self.start_time
                selected_rows = rows[mask]
            if len(selected_rows):
                totals = np.sum(selected_rows, axis=1).reshape(-1, 1)
                self.force_buffer.extend(
                    np.hstack((times.reshape(-1, 1), totals, selected_rows)).tolist()
                )
            self.force_sample_index += count

    def add_force_voltage_chunk(self, rows, sample_rate, source_start_monotonic=None):
        """Record unfiltered NI voltage samples for calibration and diagnostics."""
        rows = np.asarray(rows)
        if rows.size == 0:
            return
        if rows.ndim == 1:
            rows = rows.reshape(1, -1)

        with self._lock:
            if not self.recording:
                return

            count = len(rows)
            if source_start_monotonic is None:
                times = (
                    np.arange(
                        self.force_voltage_sample_index,
                        self.force_voltage_sample_index + count,
                    )
                    / sample_rate
                )
                selected_rows = rows
            else:
                absolute_times = (
                    float(source_start_monotonic)
                    + np.arange(count) / sample_rate
                )
                mask = self._capture_mask(absolute_times)
                times = absolute_times[mask] - self.start_time
                selected_rows = rows[mask]
            if len(selected_rows):
                self.force_voltage_buffer.extend(
                    np.hstack((times.reshape(-1, 1), selected_rows)).tolist()
                )
            self.force_voltage_sample_index += count

    def add_motion_sample(self, source_monotonic, state):
        with self._lock:
            if not self.recording or not self._within_capture(source_monotonic):
                return
            self.motion_buffer.append(
                [
                    float(source_monotonic) - self.start_time,
                    int(state.position),
                    int(state.speed),
                    int(state.run_state),
                    int(state.io_state),
                    int(state.emergency),
                ]
            )

    def add_iv_point(self, channel, voltage, current_mA):
        with self._lock:
            if not self.recording:
                return

            t = time.time() - self.start_time
            self.iv_buffer.append([t, channel, voltage, current_mA])

    def save(self):
        with self._lock:
            if (
                not self.daq_buffer
                and not self.force_buffer
                and not self.force_voltage_buffer
                and not self.iv_buffer
                and not self.motion_buffer
                and not self.spatial_buffer
                and not self.led_summary_buffer
            ):
                print("[Recorder] No data to save")
                return {}

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            daq_header = None
            force_header = None
            saved_paths = {}

            if self.daq_buffer:
                daq_file = f"group{self.group_id}_daq_{timestamp}.csv"
                daq_path = os.path.join(self.save_dir, daq_file)

                ch_num = len(self.daq_buffer[0]) - 1
                names = self.daq_channels or [f"ch{i + 1}" for i in range(ch_num)]
                daq_header = ["time"] + names

                with open(daq_path, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(daq_header)
                    writer.writerows(self.daq_buffer)

                print(f"[Recorder] DAQ Saved -> {daq_path}")
                saved_paths["daq"] = daq_path

            if self.force_buffer:
                force_file = f"group{self.group_id}_force_{timestamp}.csv"
                force_path = os.path.join(self.save_dir, force_file)

                ch_num = len(self.force_buffer[0]) - 2
                force_header = ["time", "total_force(N)"] + [
                    f"P{i + 1}(N)" for i in range(ch_num)
                ]

                with open(force_path, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(force_header)
                    writer.writerows(self.force_buffer)

                print(f"[Recorder] Force Saved -> {force_path}")
                saved_paths["force"] = force_path

            if self.force_voltage_buffer:
                voltage_file = f"group{self.group_id}_force_voltage_{timestamp}.csv"
                voltage_path = os.path.join(self.save_dir, voltage_file)
                ch_num = len(self.force_voltage_buffer[0]) - 1
                voltage_header = ["time"] + [
                    f"P{i + 1}_raw(V)" for i in range(ch_num)
                ]

                with open(voltage_path, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(voltage_header)
                    writer.writerows(self.force_voltage_buffer)

                print(f"[Recorder] Force Voltage Saved -> {voltage_path}")
                saved_paths["force_voltage"] = voltage_path

            if self.iv_buffer:
                iv_file = f"group{self.group_id}_iv_{timestamp}.csv"
                iv_path = os.path.join(self.save_dir, iv_file)

                with open(iv_path, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["time", "channel", "voltage(V)", "current(mA)"])
                    writer.writerows(self.iv_buffer)

                print(f"[Recorder] IV Saved -> {iv_path}")
                saved_paths["iv"] = iv_path

            if self.motion_buffer:
                motion_file = f"group{self.group_id}_motion_{timestamp}.csv"
                motion_path = os.path.join(self.save_dir, motion_file)
                with open(motion_path, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(
                        ["time", "position_pulse", "speed_pps", "run_state", "io_state", "emergency"]
                    )
                    writer.writerows(self.motion_buffer)
                print(f"[Recorder] Motion Saved -> {motion_path}")
                saved_paths["motion"] = motion_path

            if self.spatial_buffer:
                spatial_file = f"group{self.group_id}_spatial_{timestamp}.csv"
                spatial_path = os.path.join(self.save_dir, spatial_file)
                with open(spatial_path, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(self.spatial_header)
                    writer.writerows(self.spatial_buffer)
                print(f"[Recorder] Spatial Scan Saved -> {spatial_path}")
                saved_paths["spatial"] = spatial_path

            if self.led_summary_buffer:
                summary_file = f"group{self.group_id}_led_summary_{timestamp}.csv"
                summary_path = os.path.join(self.save_dir, summary_file)
                with open(summary_path, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(self.led_summary_header)
                    writer.writerows(self.led_summary_buffer)
                print(f"[Recorder] LED Summary Saved -> {summary_path}")
                saved_paths["led_summary"] = summary_path

            if self.daq_buffer and self.force_buffer:
                merged_file = f"group{self.group_id}_merged_{timestamp}.csv"
                merged_path = os.path.join(self.save_dir, merged_file)
                merged_header = daq_header + ["force_time"] + force_header[1:]

                with open(merged_path, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(merged_header)
                    writer.writerows(self._merge_daq_with_force())

                print(f"[Recorder] Merged Saved -> {merged_path}")
                saved_paths["merged"] = merged_path

            if self.metadata:
                metadata_file = f"group{self.group_id}_metadata_{timestamp}.json"
                metadata_path = os.path.join(self.save_dir, metadata_file)
                metadata = dict(self.metadata)
                metadata["group_id"] = self.group_id
                metadata["files"] = {
                    name: os.path.basename(path)
                    for name, path in saved_paths.items()
                }
                with open(metadata_path, "w", encoding="utf-8") as f:
                    json.dump(metadata, f, ensure_ascii=False, indent=2)
                saved_paths["metadata"] = metadata_path

            return saved_paths

    def _capture_mask(self, absolute_times):
        mask = absolute_times >= self.start_time
        if self.capture_end_clock is not None:
            mask &= absolute_times <= self.capture_end_clock + 1e-9
        return mask

    def _within_capture(self, clock):
        if float(clock) < self.start_time:
            return False
        return (
            self.capture_end_clock is None
            or float(clock) <= self.capture_end_clock + 1e-9
        )

    def _merge_daq_with_force(self):
        merged = []
        force_idx = -1

        for daq_row in self.daq_buffer:
            daq_time = daq_row[0]
            while (
                force_idx + 1 < len(self.force_buffer)
                and self.force_buffer[force_idx + 1][0] <= daq_time
            ):
                force_idx += 1

            if force_idx >= 0:
                force_row = self.force_buffer[force_idx]
                merged.append(daq_row + force_row)
            else:
                force_width = len(self.force_buffer[0])
                merged.append(daq_row + [""] * force_width)

        return merged
