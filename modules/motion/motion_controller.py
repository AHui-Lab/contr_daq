# modules/motion/motion_controller.py

from modules.motion.net_amc4xer import NetAMC4XER
from utils.log import log   # 如果你有统一日志系统（可选）
from pathlib import Path
from modules.motion.MotionLoopThread import MotionLoopThread


class MotionController:
    AXIS_MAP = {
        "X": 1,
        "Y": 0,
        "Z": 3,
        "R": 2,
    }
    BASE_DIR = Path(__file__).resolve().parents[2]
    dll_path = BASE_DIR / "dll" / "NET_AMC4XER.dll"

    def __init__(self, ui):
        self.ui = ui
        self.loop_thread = None

        # ⚠️ 这里的 IP 请换成你真实的控制卡 IP
        self.motion = NetAMC4XER(
            dll_path=str(self.dll_path),
            dest_ip="192.168.1.30"
        )

        # 绑定按钮
        self.ui.xPosButton.clicked.connect(lambda: self.move("X", +1))
        self.ui.xNegButton.clicked.connect(lambda: self.move("X", -1))
        self.ui.yPosButton.clicked.connect(lambda: self.move("Y", +1))
        self.ui.yNegButton.clicked.connect(lambda: self.move("Y", -1))
        self.ui.zPosButton.clicked.connect(lambda: self.move("Z", +1))
        self.ui.zNegButton.clicked.connect(lambda: self.move("Z", -1))
        self.ui.RPosButton.clicked.connect(lambda: self.move("R", +1))
        self.ui.RNegButton.clicked.connect(lambda: self.move("R", -1))

        self.ui.Forward_circle.clicked.connect(lambda: self.start_loop(+1))
        self.ui.Backward_circle.clicked.connect(lambda: self.start_loop(-1))
        self.ui.Emergency_Stop.clicked.connect(self.emergency_stop)



    # -----------------------------
    # 点动（相对位移）
    # -----------------------------
    def move(self, axis_name: str, direction: int):
        axis = self.AXIS_MAP[axis_name]

        # SpinBox 单位：mm
        distance_mm = self.ui.distanceSpinBox.value()

        # mm → 脉冲
        if axis_name=="Z":
            length_pulse = self.mm_to_pulse_Z(distance_mm)
            speed = 1
        else:
            length_pulse = self.mm_to_pulse_X_Y_U(distance_mm)
            speed= self.ui.Speed_Setting_val.value()

        log(f"[Motion] {axis_name} {'+' if direction > 0 else '-'} {speed} {distance_mm} mm")
        #保证Z轴移动速度不变

        self.motion.enable_axis(axis)
        self.motion.move_relative(axis, 0 if direction > 0 else 1, length_pulse, speed)

    def move_single(self, axis_name, direction, distance_mm):
        axis = self.AXIS_MAP[axis_name]

        if axis_name == "Z":
            length_pulse = self.mm_to_pulse_Z(distance_mm)
            speed = 1
        else:
            length_pulse = self.mm_to_pulse_X_Y_U(distance_mm)
            speed = self.ui.Speed_Setting_val.value()

        self.motion.enable_axis(axis)
        self.motion.move_relative(
            axis,
            0 if direction > 0 else 1,
            length_pulse,
            speed
        )

    def start_loop(self, direction):
        if self.loop_thread and self.loop_thread.isRunning():
            return

        axis_name = self.ui.Axis_choice.currentText()  # "X" or "Y"
        times = self.ui.Circle_times.value()
        distance = self.ui.distanceSpinBox_2.value()
        gap = self.ui.Gap_time.value()


        self.loop_thread = MotionLoopThread(
            self,
            axis_name,
            direction,
            distance,
            times,
            gap
        )

        self.loop_thread.finished.connect(self.on_loop_finished)

        self.lock_ui(True)  # ⭐ 锁UI
        self.loop_thread.start()

    def on_loop_finished(self):
        self.lock_ui(False)
        print("[Motion] 循环完成")

    def emergency_stop(self):
        print("[Motion] 急停触发")

        # 停线程
        if self.loop_thread:
            self.loop_thread.stop()
            self.loop_thread = None

        # 停运动（调用硬件API）
        try:
            for axis in self.AXIS_MAP.values():
                self.motion.stop_axis(axis)  # ⚠️ 你的DLL函数名可能不同
        except Exception as e:
            print("急停失败:", e)

        self.lock_ui(False)

    def lock_ui(self, locked: bool):
        self.ui.Axis_choice.setEnabled(not locked)
        self.ui.Circle_times.setEnabled(not locked)
        self.ui.distanceSpinBox_2.setEnabled(not locked)
        self.ui.Gap_time.setEnabled(not locked)


        self.ui.Forward_circle.setEnabled(not locked)
        self.ui.Backward_circle.setEnabled(not locked)

        # 急停始终可用
        self.ui.Emergency_Stop.setEnabled(True)


    # -----------------------------
    # 单位换算
    # -----------------------------
    def mm_to_pulse_Z(self, mm: float) -> int:
        """
        根据你的机械参数修改：
        pulses_per_mm = 电机每转脉冲 × 减速比 / 丝杆导程
        """
        pulses_per_mm = 10959  # ⚠️ 示例值，请改成你的真实参数
        return int(mm * pulses_per_mm)

    def mm_to_pulse_X_Y_U(self, mm: float) -> int:
        """
        根据你的机械参数修改：
        pulses_per_mm = 电机每转脉冲 × 减速比 / 丝杆导程
        """
        pulses_per_mm = 2000  # ⚠️ 示例值，请改成你的真实参数
        return int(mm * pulses_per_mm)
