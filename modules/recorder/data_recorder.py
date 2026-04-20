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
        if not self.daq_buffer:
            print("[Recorder] No data to save")
            return

        filename = datetime.now().strftime(
            f"group{self.group_id}_daq_%Y%m%d_%H%M%S.csv"
        )

        path = os.path.join(self.save_dir, filename)

        ch_num = len(self.daq_buffer[0])
        header = [f"ch{i}" for i in range(ch_num)]

        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(self.daq_buffer)

        print(f"[Recorder] Saved → {path}")