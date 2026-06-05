from queue import Empty, Queue

from PySide6.QtCore import QThread, Signal


class MotionCommandThread(QThread):
    loop_finished = Signal()

    def __init__(self, motion):
        super().__init__()
        self.motion = motion
        self._commands = Queue()
        self._running = True
        self._loop_running = True

    def submit_move(self, axis, direction, length_pulse, profile):
        self._commands.put(("move", axis, direction, length_pulse, profile))

    def submit_loop(self, axis, direction, length_pulse, profile, times, gap):
        self._loop_running = True
        self._commands.put(("loop", axis, direction, length_pulse, profile, times, gap))

    def stop_loop(self):
        self._loop_running = False

    def stop_all_axes(self, axes):
        self._commands.put(("stop_axes", tuple(axes)))

    def shutdown(self):
        self._running = False
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
            elif kind == "loop":
                self._execute_loop(*command[1:])
            elif kind == "stop_axes":
                for axis in command[1]:
                    self.motion.stop_axis(axis)
            elif kind == "shutdown":
                break

    def _execute_loop(self, axis, direction, length_pulse, profile, times, gap):
        for _ in range(times):
            if not self._running or not self._loop_running:
                break
            self._execute_move(axis, direction, length_pulse, profile)
            self.msleep(round(float(gap) * 1000))
        self.loop_finished.emit()

    def _execute_move(self, axis, direction, length_pulse, profile):
        self.motion.enable_axis(axis)
        self.motion.move_relative(
            axis,
            0 if direction > 0 else 1,
            length_pulse,
            profile,
        )
