# modules/force/force_controller.py
import numpy as np
from modules.force.force_thread import ForceThread
from modules.force.force_plot import ForcePlot
from modules.force.force_balance_plot import ForceBalancePlot
from utils.log import log   # 如果你有统一日志系统（可选）
from modules.recorder.data_recorder import DataRecorder
import time
from collections import deque

class ForceController:
    def __init__(self, ui):
        self.ui = ui

        self.running=False
        self.latest_force = 0.0
        self.latest_vals = None

        # self.balance_plot = ForceBalancePlot(
        #     self.ui.forcePlotWidget_2
        # )
        self.zero_offset = np.zeros(4)
        self.plot = ForcePlot(self.ui.forcePlotWidget, time_window=10.0)
        self.thread = None
        self.zero_buffer = deque(maxlen=300)

        self.ui.forceStartButton.clicked.connect(self.toggle)
        self.ui.forceZeroButton.clicked.connect(self.zero)

        self.ui.recorderStartButton.clicked.connect(self.start_record)
        self.ui.recorderStopButton.clicked.connect(self.stop_record)
        self.recorder = DataRecorder()


    def start_record(self):
        if self.thread is None:
            print("[Recorder] 请先启动DAQ")
            return

        self.recorder.start()

    def stop_record(self):
        self.recorder.stop()


    def toggle(self):
        if self.thread and self.thread.isRunning():
            self.stop()
        else:
            self.start()

    def start(self):
        self.plot.clear()
        self.zero_buffer.clear()
        self.zero_offset = np.zeros(4)

        self.thread = ForceThread(port="COM15", baudrate=9600)
        self.thread.data_ready.connect(self.on_data)
        self.thread.started_ok.connect(self.on_started)

        self.thread.start()



    def stop(self):
        if self.thread:
            self.thread.stop()
            self.thread = None
            self.latest_force = 0.0

        self.running = False
        self.ui.forceStartButton.setText("开始")

    def zero(self):
        if len(self.zero_buffer) < 30:
            print("[Force] 数据不足，无法归零")
            return

        data = np.array(self.zero_buffer)

        window = data[-30:]  # ⭐ 最近窗口
        half = 15

        first_half = window[:half]
        second_half = window[half:]

        mean1 = np.mean(first_half, axis=0)
        mean2 = np.mean(second_half, axis=0)

        # ⭐ 条件1：窗口内稳定（噪声小）
        if np.std(window) > 0.02:
            print("[Force] 波动过大，归零失败")
            return

        # ⭐ 条件2：没有趋势变化（关键）
        if np.linalg.norm(mean2 - mean1) > 0.03:
            print("[Force] 数据仍在变化，归零失败")
            return

        # ⭐ 满足条件 → 归零
        self.zero_offset = np.mean(window, axis=0)

        print("[Force] 快速归零完成")

    def on_started(self, ok):
        if ok:
            self.running = True
            self.ui.forceStartButton.setText("停止")
        else:
            self.running = False
            self.thread = None
            self.ui.forceStartButton.setText("开始")
            print("[Force] 启动失败")

    def on_data(self, total_force, vals):
        vals = np.array(vals)

        # ⭐ 先存原始值（用于归零）
        self.zero_buffer.append(vals)

        # ⭐ 零点修正
        corrected_vals = vals - self.zero_offset
        corrected_vals = corrected_vals * 0.00981
        corrected_total = float(np.sum(corrected_vals))

        self.latest_vals = corrected_vals
        self.latest_force = corrected_total

        # =============================
        # ⭐⭐ 新增：数据保存（核心）
        # =============================
        if self.recorder.recording:
            self.recorder.add_force_data(
                timestamp=time.time(),
                total_force=corrected_total,
                vals=corrected_vals.tolist()
            )

    def update_ui(self):
        if not self.running or self.latest_vals is None:
            return

        # ===== 总力 =====
        self.ui.totalForceLabel.setText(f"总力: {self.latest_force:.2f}")

        # ===== 四通道 =====
        #self.ui.Force1_Label.setText(f"P1: {self.latest_vals[0]:.2f}")
        #self.ui.Force2_Label.setText(f"P2: {self.latest_vals[1]:.2f}")
        #self.ui.Force3_Label.setText(f"P3: {self.latest_vals[2]:.2f}")
        #self.ui.Force4_Label.setText(f"P4: {self.latest_vals[3]:.2f}")

        # ===== 只画总力 =====
        self.plot.add_point(self.latest_force)


