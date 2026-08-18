from queue import Empty, Queue
import time

from PySide6.QtCore import QThread, Signal


class MotionCommandThread(QThread):
    MOVE_COMPLETION_TIMEOUT_S = 5.0
    MOVE_POLL_INTERVAL_MS = 5
    move_finished = Signal(bool, str)
    scan_started = Signal()
    scan_progress = Signal(object)
    scan_finished = Signal(bool, str)

    def __init__(self, motion):
        super().__init__()
        self.motion = motion
        self._commands = Queue()
        self._running = True
        self._scan_running = False

    def submit_move(self, axis, direction, length_pulse, profile):
        self._commands.put(("move", axis, direction, length_pulse, profile))

    def submit_scan(
        self,
        axis,
        direction,
        length_pulse,
        profile,
        timeout_s,
        telemetry_interval_ms=10,
        on_capture_start=None,
        on_telemetry=None,
        on_capture_end=None,
    ):
        self._scan_running = True
        self._commands.put(
            (
                "scan",
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
        )

    def stop_scan(self):
        self._scan_running = False

    def stop_all_axes(self, axes):
        self._scan_running = False
        self._commands.put(("stop_axes", tuple(axes)))

    def shutdown(self):
        self._running = False
        self._scan_running = False
        self._commands.put(("shutdown",))

    def run(self):
        while self._running:
            try:
                command = self._commands.get(timeout=0.1)
            except Empty:
                continue

            kind = command[0]
            if kind == "move":
                self._execute_move(*command[1:])
            elif kind == "scan":
                self._execute_scan(*command[1:])
            elif kind == "stop_axes":
                for axis in command[1]:
                    self.motion.stop_axis(axis)
            elif kind == "shutdown":
                break

    def _execute_scan(
        self,
        axis,
        direction,
        length_pulse,
        profile,
        timeout_s,
        telemetry_interval_ms,
        on_capture_start,
        on_telemetry,
        on_capture_end,
    ):
        capture_started = False
        try:
            self.motion.enable_axis(axis)
            initial = self.motion.read_axis_state(axis)
            if initial.emergency:
                raise RuntimeError("Motion controller emergency input is active")
            if initial.run_state != 0:
                raise RuntimeError("Selected motion axis is already moving")

            capture_clock = time.perf_counter()
            if on_capture_start is not None:
                on_capture_start(capture_clock)
            capture_started = True
            if on_telemetry is not None:
                on_telemetry(capture_clock, initial)

            result = self.motion.move_relative(
                axis,
                0 if direction > 0 else 1,
                length_pulse,
                profile,
            )
            if result == -1:
                raise ConnectionError("Motion command failed")

            self.scan_started.emit()
            deadline = time.perf_counter() + max(float(timeout_s), 1.0)
            telemetry_interval_ms = max(
                1,
                min(int(telemetry_interval_ms), 50),
            )
            seen_motion = False
            while self._running and self._scan_running:
                state = self.motion.read_axis_state(axis)
                sample_clock = time.perf_counter()
                seen_motion = (
                    seen_motion
                    or state.run_state != 0
                    or state.position != initial.position
                )
                if on_telemetry is not None:
                    on_telemetry(sample_clock, state)
                self.scan_progress.emit(state)

                if state.emergency:
                    raise RuntimeError("Motion controller emergency input became active")
                if seen_motion and state.run_state == 0:
                    self._scan_running = False
                    if on_capture_end is not None:
                        on_capture_end(sample_clock)
                    detail = "triangular" if result == -2 else "completed"
                    self.scan_finished.emit(True, detail)
                    return
                if sample_clock >= deadline:
                    raise TimeoutError("Motion completion timeout")
                self.msleep(telemetry_interval_ms)

            self.motion.stop_axis(axis)
            end_clock = time.perf_counter()
            if capture_started and on_capture_end is not None:
                on_capture_end(end_clock)
            self.scan_finished.emit(False, "cancelled")
        except Exception as exc:
            try:
                self.motion.stop_axis(axis)
            except Exception:
                pass
            end_clock = time.perf_counter()
            if capture_started and on_capture_end is not None:
                on_capture_end(end_clock)
            self._scan_running = False
            self.scan_finished.emit(False, str(exc))

    def _execute_move(self, axis, direction, length_pulse, profile):
        try:
            initial = self.motion.read_axis_state(axis)
            if initial.emergency:
                raise RuntimeError("Motion controller emergency input is active")
            if initial.run_state != 0:
                raise RuntimeError("Selected motion axis is already moving")
            self.motion.enable_axis(axis)
            result = self.motion.move_relative(
                axis,
                0 if direction > 0 else 1,
                length_pulse,
                profile,
            )
            if result == -1:
                raise ConnectionError("Motion command failed")

            deadline = time.perf_counter() + self.MOVE_COMPLETION_TIMEOUT_S
            seen_motion = False
            while self._running:
                state = self.motion.read_axis_state(axis)
                seen_motion = (
                    seen_motion
                    or state.run_state != 0
                    or state.position != initial.position
                )
                if state.emergency:
                    raise RuntimeError(
                        "Motion controller emergency input became active"
                    )
                if seen_motion and state.run_state == 0:
                    self.move_finished.emit(True, "move completed")
                    return
                if time.perf_counter() >= deadline:
                    raise TimeoutError("Motion completion timeout")
                self.msleep(self.MOVE_POLL_INTERVAL_MS)
            raise RuntimeError("Motion worker stopped before move completed")
        except Exception as exc:
            try:
                self.motion.stop_axis(axis)
            except Exception:
                pass
            self.move_finished.emit(False, str(exc))
