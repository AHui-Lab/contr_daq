import csv
import os
import time
from datetime import datetime
from threading import RLock

import numpy as np


class DataRecorder:
    def __init__(self, save_dir="data"):
        self._lock = RLock()
        self.recording = False
        self.save_dir = save_dir
        os.makedirs(self.save_dir, exist_ok=True)
        self.group_id = 0
        self.reset_buffer()

    def reset_buffer(self):
        self.start_time = None
        self.daq_buffer = []
        self.force_buffer = []
        self.iv_buffer = []
        self.daq_channels = []
        self.daq_sample_index = 0
        self.force_sample_index = 0

    def start(self):
        with self._lock:
            if self.recording:
                return

            self.recording = True
            self.group_id += 1
            self.reset_buffer()

            self.start_time = time.time()
            print(f"[Recorder] Start recording group {self.group_id}")

    def stop(self):
        with self._lock:
            if not self.recording:
                return

            self.recording = False
            print(f"[Recorder] Stop recording group {self.group_id}")
            self.save()

    def add_daq_data(self, voltages):
        with self._lock:
            if not self.recording:
                return

            t = time.time() - self.start_time
            self.daq_buffer.append([t] + list(voltages))

    def add_daq_chunk(self, rows, sample_rate, channels=None):
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
            times = (
                np.arange(self.daq_sample_index, self.daq_sample_index + count)
                / sample_rate
            ).reshape(-1, 1)
            self.daq_buffer.extend(np.hstack((times, rows)).tolist())
            self.daq_sample_index += count

    def add_force_data(self, total_force, vals):
        with self._lock:
            if not self.recording:
                return

            t = time.time() - self.start_time
            self.force_buffer.append([t, total_force] + list(vals))

    def add_force_chunk(self, rows, sample_rate):
        rows = np.asarray(rows)
        if rows.size == 0:
            return
        if rows.ndim == 1:
            rows = rows.reshape(1, -1)

        with self._lock:
            if not self.recording:
                return

            count = len(rows)
            times = (
                np.arange(self.force_sample_index, self.force_sample_index + count)
                / sample_rate
            ).reshape(-1, 1)
            totals = np.sum(rows, axis=1).reshape(-1, 1)
            self.force_buffer.extend(np.hstack((times, totals, rows)).tolist())
            self.force_sample_index += count

    def add_iv_point(self, channel, voltage, current_mA):
        with self._lock:
            if not self.recording:
                return

            t = time.time() - self.start_time
            self.iv_buffer.append([t, channel, voltage, current_mA])

    def save(self):
        with self._lock:
            if not self.daq_buffer and not self.force_buffer and not self.iv_buffer:
                print("[Recorder] No data to save")
                return

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            daq_header = None
            force_header = None

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

            if self.iv_buffer:
                iv_file = f"group{self.group_id}_iv_{timestamp}.csv"
                iv_path = os.path.join(self.save_dir, iv_file)

                with open(iv_path, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["time", "channel", "voltage(V)", "current(mA)"])
                    writer.writerows(self.iv_buffer)

                print(f"[Recorder] IV Saved -> {iv_path}")

            if self.daq_buffer and self.force_buffer:
                merged_file = f"group{self.group_id}_merged_{timestamp}.csv"
                merged_path = os.path.join(self.save_dir, merged_file)
                merged_header = daq_header + ["force_time"] + force_header[1:]

                with open(merged_path, "w", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(merged_header)
                    writer.writerows(self._merge_daq_with_force())

                print(f"[Recorder] Merged Saved -> {merged_path}")

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
