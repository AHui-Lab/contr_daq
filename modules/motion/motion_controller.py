from pathlib import Path

from modules.motion.motion_command_thread import MotionCommandThread
from modules.motion.net_amc4xer import NetAMC4XER
from utils.log import log


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

        self.motion = NetAMC4XER(
            dll_path=str(self.dll_path),
            dest_ip="192.168.1.30",
        )
        self.motion_worker = MotionCommandThread(self.motion)
        self.motion_worker.loop_finished.connect(self.on_loop_finished)
        self.motion_worker.start()
        self.loop_running = False

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

    def move(self, axis_name: str, direction: int):
        distance_mm = self.ui.distanceSpinBox.value()
        axis, length_pulse, speed = self._motion_params(axis_name, distance_mm)

        log(f"[Motion] {axis_name} {'+' if direction > 0 else '-'} {speed} {distance_mm} mm")
        self._start_move_thread(axis, direction, length_pulse, speed)

    def move_single(self, axis_name, direction, distance_mm):
        axis, length_pulse, speed = self._motion_params(axis_name, distance_mm)

        self.motion.enable_axis(axis)
        self.motion.move_relative(
            axis,
            0 if direction > 0 else 1,
            length_pulse,
            speed,
        )

    def start_loop(self, direction):
        if self.loop_running:
            return

        axis_name = self.ui.Axis_choice.currentText()
        times = self.ui.Circle_times.value()
        distance = self.ui.distanceSpinBox_2.value()
        gap = self.ui.Gap_time.value()
        axis, length_pulse, speed = self._motion_params(axis_name, distance)

        self.motion_worker.submit_loop(
            axis,
            direction,
            length_pulse,
            speed,
            times,
            gap,
        )

        self.lock_ui(True)
        self.loop_running = True

    def on_loop_finished(self):
        self.loop_running = False
        self.lock_ui(False)
        print("[Motion] loop completed")

    def emergency_stop(self):
        print("[Motion] emergency stop")

        self.loop_running = False
        self.motion_worker.stop_loop()
        self.motion_worker.stop_all_axes(self.AXIS_MAP.values())

        self.lock_ui(False)

    def lock_ui(self, locked: bool):
        self.ui.Axis_choice.setEnabled(not locked)
        self.ui.Circle_times.setEnabled(not locked)
        self.ui.distanceSpinBox_2.setEnabled(not locked)
        self.ui.Gap_time.setEnabled(not locked)

        self.ui.Forward_circle.setEnabled(not locked)
        self.ui.Backward_circle.setEnabled(not locked)

        self.ui.Emergency_Stop.setEnabled(True)

    def _motion_params(self, axis_name, distance_mm):
        axis = self.AXIS_MAP[axis_name]

        if axis_name == "Z":
            length_pulse = self.mm_to_pulse_Z(distance_mm)
            speed = 1
        else:
            length_pulse = self.mm_to_pulse_X_Y_U(distance_mm)
            speed = self.ui.Speed_Setting_val.value()

        return axis, length_pulse, speed

    def _start_move_thread(self, axis, direction, length_pulse, speed):
        self.motion_worker.submit_move(
            axis,
            direction,
            length_pulse,
            speed,
        )

    def shutdown(self):
        self.motion_worker.shutdown()

    def mm_to_pulse_Z(self, mm: float) -> int:
        pulses_per_mm = 10959
        return int(mm * pulses_per_mm)

    def mm_to_pulse_X_Y_U(self, mm: float) -> int:
        pulses_per_mm = 2000
        return int(mm * pulses_per_mm)
