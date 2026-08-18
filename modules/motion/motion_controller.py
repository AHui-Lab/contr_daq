from pathlib import Path

from modules.motion.motion_command_thread import MotionCommandThread
from modules.motion.net_amc4xer import MotionProfile, NetAMC4XER
from utils.log import log
from modules.app_runtime import RuntimeStatus


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
    FORCE_HOLD_Z_SPEED_MM_S = 0.1
    MAX_FORCE_HOLD_STEP_MM = 0.0100
    MAX_FORCE_VERIFY_MOVE_MM = 0.0500
    BASE_DIR = Path(__file__).resolve().parents[2]
    dll_path = BASE_DIR / "dll" / "NET_AMC4XER.dll"

    def __init__(self, ui, runtime=None):
        self.ui = ui
        self.runtime = runtime

        self.motion = NetAMC4XER(
            dll_path=str(self.dll_path),
            dest_ip="192.168.1.30",
        )
        self.motion_worker = MotionCommandThread(self.motion)
        self.motion_worker.scan_finished.connect(self.on_scan_finished)
        self.motion_worker.start()
        self.scan_running = False
        self._scan_finished_callback = None

        self.ui.xPosButton.clicked.connect(lambda: self.move("X", +1))
        self.ui.xNegButton.clicked.connect(lambda: self.move("X", -1))
        self.ui.yPosButton.clicked.connect(lambda: self.move("Y", +1))
        self.ui.yNegButton.clicked.connect(lambda: self.move("Y", -1))
        self.ui.zPosButton.clicked.connect(lambda: self.move("Z", +1))
        self.ui.zNegButton.clicked.connect(lambda: self.move("Z", -1))
        self.ui.RPosButton.clicked.connect(lambda: self.move("R", +1))
        self.ui.RNegButton.clicked.connect(lambda: self.move("R", -1))

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

    def apply_force_hold_z_step(self, direction, distance_mm):
        """Issue one non-blocking Z micro-step from the scan worker thread."""
        step_mm = float(distance_mm)
        if int(direction) not in (-1, 1):
            raise ValueError("Force-hold Z direction must be +1 or -1")
        if step_mm <= 0 or step_mm > self.MAX_FORCE_HOLD_STEP_MM:
            raise ValueError(
                f"Force-hold Z step must be within 0 to {self.MAX_FORCE_HOLD_STEP_MM:g} mm"
            )

        config = self.AXIS_CONFIG["Z"]
        axis = config["axis"]
        state = self.motion.read_axis_state(axis)
        if state.emergency:
            raise RuntimeError("Motion controller emergency input is active")
        if state.run_state != 0:
            return False, "busy", int(state.position)

        length_pulse = max(1, round(step_mm * config["pulses_per_mm"]))
        profile = self._build_motion_profile(
            speed_mm_s=self.FORCE_HOLD_Z_SPEED_MM_S,
            pulses_per_mm=config["pulses_per_mm"],
            accel_mm_s2=config["accel_mm_s2"],
        )
        self.motion.enable_axis(axis)
        result = self.motion.move_relative(
            axis,
            0 if int(direction) > 0 else 1,
            length_pulse,
            profile,
        )
        if result == -1:
            raise ConnectionError("Force-hold Z motion command failed")
        log(
            f"[Force Hold] Z {'+' if direction > 0 else '-'}{step_mm:.4f} mm "
            f"({length_pulse} pulses)"
        )
        return True, "applied", int(state.position)

    def stop_force_hold_z(self):
        return self.motion.stop_axis(self.AXIS_CONFIG["Z"]["axis"])

    def queue_force_hold_z_step(self, direction, distance_mm):
        """Queue a guarded Z micro-step so UI timers never call hardware directly."""
        return self._queue_guarded_z_move(
            direction,
            distance_mm,
            max_distance_mm=self.MAX_FORCE_HOLD_STEP_MM,
            log_context="Force Commissioning",
        )

    def queue_force_verification_z_move(self, direction, distance_mm):
        """Queue a commissioning-only Z move with a separately bounded travel limit."""
        return self._queue_guarded_z_move(
            direction,
            distance_mm,
            max_distance_mm=self.MAX_FORCE_VERIFY_MOVE_MM,
            log_context="Force Verification",
        )

    def _queue_guarded_z_move(
        self,
        direction,
        distance_mm,
        *,
        max_distance_mm,
        log_context,
    ):
        step_mm = float(distance_mm)
        if int(direction) not in (-1, 1):
            raise ValueError("Force-hold Z direction must be +1 or -1")
        if step_mm <= 0 or step_mm > float(max_distance_mm):
            raise ValueError(
                f"Guarded Z move must be within 0 to {float(max_distance_mm):g} mm"
            )
        config = self.AXIS_CONFIG["Z"]
        length_pulse = max(1, round(step_mm * config["pulses_per_mm"]))
        profile = self._build_motion_profile(
            speed_mm_s=self.FORCE_HOLD_Z_SPEED_MM_S,
            pulses_per_mm=config["pulses_per_mm"],
            accel_mm_s2=config["accel_mm_s2"],
        )
        self.motion_worker.submit_move(
            config["axis"],
            int(direction),
            length_pulse,
            profile,
        )
        log(
            f"[{log_context}] queued Z "
            f"{'+' if direction > 0 else '-'}{step_mm:.4f} mm"
        )
        return True

    def request_force_hold_retract(self, distance_mm):
        """Queue a Z- retract; callers must independently verify Z direction first."""
        return self.queue_force_hold_z_step(-1, distance_mm)

    def request_force_hold_stop(self):
        """Request a Z-axis stop through the motion worker command queue."""
        self.motion_worker.stop_all_axes((self.AXIS_CONFIG["Z"]["axis"],))

    def start_scan(
        self,
        axis_name,
        direction,
        distance_mm,
        telemetry_interval_ms=10,
        on_capture_start=None,
        on_telemetry=None,
        on_capture_end=None,
        on_finished=None,
    ):
        if self.scan_running:
            return False

        axis, length_pulse, profile, speed_mm_s = self._motion_params(
            axis_name,
            distance_mm,
        )
        pulses_per_mm = self.AXIS_CONFIG[axis_name]["pulses_per_mm"]
        minimum_speed = max(profile.vo / pulses_per_mm, 0.01)
        timeout_s = distance_mm / minimum_speed + 5.0
        self._scan_finished_callback = on_finished
        self.motion_worker.submit_scan(
            axis,
            direction,
            length_pulse,
            profile,
            timeout_s,
            telemetry_interval_ms,
            on_capture_start,
            on_telemetry,
            on_capture_end,
        )

        self.lock_ui(True)
        self.scan_running = True
        if self.runtime is not None:
            self.runtime.set("motion", RuntimeStatus.RUNNING)
        log(
            f"[Scan] {axis_name} {'+' if direction > 0 else '-'} "
            f"{speed_mm_s:.2f} mm/s over {distance_mm:.3f} mm; "
            f"motion telemetry every {int(telemetry_interval_ms)} ms"
        )
        return True

    def on_scan_finished(self, completed, detail):
        self.scan_running = False
        self.lock_ui(False)
        if self.runtime is not None:
            clean_completion = completed and detail != "triangular"
            status = RuntimeStatus.READY if clean_completion else RuntimeStatus.WARNING
            self.runtime.set("motion", status, detail)
        callback = self._scan_finished_callback
        self._scan_finished_callback = None
        if callback is not None:
            callback(bool(completed), str(detail))

    def emergency_stop(self):
        print("[Motion] emergency stop")

        self.scan_running = False
        if self.runtime is not None:
            self.runtime.set("motion", RuntimeStatus.STOPPING)
        self.motion_worker.stop_scan()
        self.motion_worker.stop_all_axes(self.AXIS_MAP.values())

        self.lock_ui(False)
        if self.runtime is not None:
            self.runtime.set("motion", RuntimeStatus.READY)

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
