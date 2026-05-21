import time
import os
import csv
from datetime import datetime


class DataRecorder:
    def __init__(self, save_dir="data"):
        self.recording = False

        self.save_dir = save_dir
        os.makedirs(self.save_dir, exist_ok=True)

        self.group_id = 0

        self.reset_buffer()

    def reset_buffer(self):
        self.start_time = None
        self.daq_buffer = []   # [time, ch1, ch2, ...]
        self.force_buffer = [] # [time, force]

    # ======================
    # 控制
    # ======================
    def start(self):
        if self.recording:
            return

        self.recording = True
        self.group_id += 1
        self.reset_buffer()

        self.start_time = time.time()
        print(f"[Recorder] Start recording group {self.group_id}")

    def stop(self):
        if not self.recording:
            return

        self.recording = False
        print(f"[Recorder] Stop recording group {self.group_id}")

        self.save()

    # ======================
    # 数据输入接口
    # ======================
    def add_daq_data(self, voltages):
        """
        voltages: list，例如 [v1, v2, v3 ...]
        """
        if not self.recording:
            return

        t = time.time() - self.start_time
        self.daq_buffer.append([t] + voltages)

    def add_force_data(self, timestamp, total_force, vals):
        if not self.recording:
            return

        # 示例：一行数据
        row = [
            timestamp,
            total_force,
            vals[0],
            vals[1],
            vals[2],
            vals[3],
        ]

        self.force_buffer.append(row)

    # ======================
    # 保存
    # ======================
    def save(self):
        if not self.daq_buffer and not self.force_buffer:
            print("[Recorder] No data to save")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # ======================
        # 保存 DAQ
        # ======================
        if self.daq_buffer:
            daq_file = f"group{self.group_id}_daq_{timestamp}.csv"
            daq_path = os.path.join(self.save_dir, daq_file)

            ch_num = len(self.daq_buffer[0]) - 1  # 减去 time
            header = ["time"] + [f"ch{i + 1}" for i in range(ch_num)]

            with open(daq_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(header)
                writer.writerows(self.daq_buffer)

            print(f"[Recorder] DAQ Saved → {daq_path}")

        # ======================
        # 保存 Force
        # ======================
        if self.force_buffer:
            force_file = f"group{self.group_id}_force_{timestamp}.csv"
            force_path = os.path.join(self.save_dir, force_file)

            header = ["time", "total_force", "P1", "P2", "P3", "P4"]

            with open(force_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(header)
                writer.writerows(self.force_buffer)

            print(f"[Recorder] Force Saved → {force_path}")