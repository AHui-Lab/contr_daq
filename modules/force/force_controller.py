# modules/force/force_controller.py
import numpy as np
from modules.force.force_thread import ForceThread
from modules.force.force_plot import ForcePlot
from modules.force.force_balance_plot import ForceBalancePlot
from utils.log import log   # 如果你有统一日志系统（可选）

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
        self.zero_buffer = []

        self.ui.forceStartButton.clicked.connect(self.toggle)
        self.ui.forceZeroButton.clicked.connect(self.zero)

    def toggle(self):
        if self.thread and self.thread.isRunning():
            self.stop()
        else:
            self.start()

    def start(self):
        self.plot.clear()
        self.zero_buffer.clear()

        self.thread = ForceThread(port="COM15", baudrate=9600)
        self.thread.data_ready.connect(self.on_data)
        self.thread.started_ok.connect(self.on_started)

        self.thread.start()



    def stop(self):
        if self.thread:
            self.thread.stop()
            self.thread = None

        self.running = False
        self.ui.forceStartButton.setText("开始")

    def zero(self):
        if len(self.zero_buffer) < 100:
            print("[Force] 数据不足，无法归零")
            return

        self.zero_offset = np.mean(self.zero_buffer[-100:], axis=0)

        print("[Force] 归零完成")

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
        vals = vals - self.zero_offset
        # ⭐ 做零点处理（放这里！）
        vals = vals - np.mean(self.zero_buffer[-100:], axis=0) if len(self.zero_buffer) >= 100 else vals

        self.latest_force = float(np.sum(vals))
        self.latest_vals = vals

        self.zero_buffer.append(vals)
        if len(self.zero_buffer) > 300:
            self.zero_buffer.pop(0)

    def update_ui(self):
        if not self.running or self.latest_vals is None:
            return

        # ===== 总力 =====
        self.ui.totalForceLabel.setText(f"总力: {self.latest_force:.2f}")

        # ===== 四通道 =====
        self.ui.Force1_Label.setText(f"P1: {self.latest_vals[0]:.2f}")
        self.ui.Force2_Label.setText(f"P2: {self.latest_vals[1]:.2f}")
        self.ui.Force3_Label.setText(f"P3: {self.latest_vals[2]:.2f}")
        self.ui.Force4_Label.setText(f"P4: {self.latest_vals[3]:.2f}")

        # ===== 只画总力 =====
        self.plot.add_point(self.latest_force)


