from pathlib import Path

from modules.motion.motion_command_thread import MotionCommandThread
from modules.motion.net_amc4xer import MotionProfile, NetAMC4XER
from utils.log import log


class MotionController:
    AXIS_CONFIG = {
        "X": {"axis": 1, "pulses_per_mm": 2000, "accel_mm_s2": 20},
        "Y": {"axis": 0, "pulses_per_mm": 2000, "accel_mm_s2": 20},
        "Z": {"axis": 3, "pulses_per_mm": 10959, "accel_mm_s2": 5},
        "R": {"axis": 2, "pulses_per_mm": 2000, "accel_mm_s2": 20},
    }
    AXIS_MAP = {name: config["axis"] for name, config in AXIS_CONFIG.items()}
    MIN_SPEED_MM_S = 0.1
    MAX_SPEED_MM_S = 100.0
    START_SPEED_RATIO = 0.1
    MIN_START_SPEED_MM_S = 0.1
    MIN_RAMP_TIME_MS = 100
    MAX_RAMP_TIME_MS = 1000
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
        axis, length_pulse, profile, speed_mm_s = self._motion_params(axis_name, distance_mm)

        log(
            f"[Motion] {axis_name} {'+' if direction > 0 else '-'} "
            f"{speed_mm_s:.2f} mm/s {distance_mm} mm "
            f"(Vo={profile.vo}, Vt={profile.vt}, "
            f"Acc={profile.acc_time} ms, Dec={profile.dec_time} ms)"
        )
        self._start_move_thread(axis, direction, length_pulse, profile)

    def move_single(self, axis_name, direction, distance_mm):
        axis, length_pulse, profile, _speed_mm_s = self._motion_params(axis_name, distance_mm)

        self.motion.enable_axis(axis)
        self.motion.move_relative(
            axis,
            0 if direction > 0 else 1,
            length_pulse,
            profile,
        )

    def start_loop(self, direction):
        if self.loop_running:
            return

        axis_name = self.ui.Axis_choice.currentText()
        times = self.ui.Circle_times.value()
        distance = self.ui.distanceSpinBox_2.value()
        gap = self.ui.Gap_time.value()
        axis, length_pulse, profile, _speed_mm_s = self._motion_params(axis_name, distance)

        self.motion_worker.submit_loop(
            axis,
            direction,
            length_pulse,
            profile,
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
        config = self.AXIS_CONFIG[axis_name]
        speed_mm_s = self._clamp_speed_mm_s(self.ui.Speed_Setting_val.value())
        length_pulse = self.mm_to_pulse(distance_mm, config["pulses_per_mm"])
        profile = self._build_motion_profile(
            speed_mm_s=speed_mm_s,
            pulses_per_mm=config["pulses_per_mm"],
            accel_mm_s2=config["accel_mm_s2"],
        )

        return config["axis"], length_pulse, profile, speed_mm_s

    def _start_move_thread(self, axis, direction, length_pulse, profile):
        self.motion_worker.submit_move(
            axis,
            direction,
            length_pulse,
            profile,
        )

    def shutdown(self):
        self.motion_worker.shutdown()

    def mm_to_pulse(self, mm: float, pulses_per_mm: int) -> int:
        return int(mm * pulses_per_mm)

    def mm_to_pulse_Z(self, mm: float) -> int:
        return self.mm_to_pulse(mm, self.AXIS_CONFIG["Z"]["pulses_per_mm"])

    def mm_to_pulse_X_Y_U(self, mm: float) -> int:
        return self.mm_to_pulse(mm, self.AXIS_CONFIG["X"]["pulses_per_mm"])

    def _build_motion_profile(
        self,
        speed_mm_s: float,
        pulses_per_mm: int,
        accel_mm_s2: float,
    ) -> MotionProfile:
        vt = max(1, round(speed_mm_s * pulses_per_mm))
        start_speed_mm_s = min(
            max(self.MIN_START_SPEED_MM_S, speed_mm_s * self.START_SPEED_RATIO),
            speed_mm_s - 0.01,
        )
        start_speed_mm_s = max(0.01, start_speed_mm_s)
        vo = max(1, min(round(start_speed_mm_s * pulses_per_mm), vt - 1))

        ramp_time_ms = round((speed_mm_s - start_speed_mm_s) / accel_mm_s2 * 1000)
        ramp_time_ms = self._clamp_int(
            ramp_time_ms,
            self.MIN_RAMP_TIME_MS,
            self.MAX_RAMP_TIME_MS,
        )

        return MotionProfile(
            vo=vo,
            vt=vt,
            acc_time=ramp_time_ms,
            dec_time=ramp_time_ms,
        )

    def _clamp_speed_mm_s(self, speed_mm_s: float) -> float:
        return max(self.MIN_SPEED_MM_S, min(float(speed_mm_s), self.MAX_SPEED_MM_S))

    @staticmethod
    def _clamp_int(value: int, minimum: int, maximum: int) -> int:
        return max(minimum, min(value, maximum))
