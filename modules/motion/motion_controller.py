# modules/motion/motion_controller.py

from modules.motion.net_amc4xer import NetAMC4XER
from utils.log import log   # 如果你有统一日志系统（可选）


class MotionController:
    AXIS_MAP = {
        "X": 1,
        "Y": 0,
        "Z": 3,
    }

    def __init__(self, ui):
        self.ui = ui

        # ⚠️ 这里的 IP 请换成你真实的控制卡 IP
        self.motion = NetAMC4XER(
            dll_path="F:/桌面/contr_daq/contr_daq/NET_AMC4XER.dll",
            dest_ip="192.168.1.30"
        )

        # 绑定按钮
        self.ui.xPosButton.clicked.connect(lambda: self.move("X", +1))
        self.ui.xNegButton.clicked.connect(lambda: self.move("X", -1))
        self.ui.yPosButton.clicked.connect(lambda: self.move("Y", +1))
        self.ui.yNegButton.clicked.connect(lambda: self.move("Y", -1))
        self.ui.zPosButton.clicked.connect(lambda: self.move("Z", +1))
        self.ui.zNegButton.clicked.connect(lambda: self.move("Z", -1))

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
        else:
            length_pulse = self.mm_to_pulse_X_Y_U(distance_mm)


        log(f"[Motion] {axis_name} {'+' if direction > 0 else '-'} {distance_mm} mm")

        self.motion.enable_axis(axis)
        self.motion.move_relative(axis, 0 if direction > 0 else 1, length_pulse)

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
