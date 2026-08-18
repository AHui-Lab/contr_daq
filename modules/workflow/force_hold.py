from dataclasses import asdict, dataclass
from math import isfinite
from threading import RLock


@dataclass(frozen=True)
class ForceHoldConfig:
    """Fixed-period force-derivative damping configuration."""

    enabled: bool = False
    derivative_interval_s: float = 0.10
    derivative_deadband_n_s: float = 1.0
    z_step_mm: float = 0.0005
    measurement_window_s: float = 0.05
    signal_timeout_s: float = 0.25
    max_offset_mm: float = 0.0500
    hard_error_n: float = 2.0
    z_positive_increases_force: bool = True

    def validate(self) -> None:
        if self.derivative_interval_s <= 0:
            raise ValueError("Force-derivative time step must be greater than zero")
        if self.derivative_deadband_n_s < 0:
            raise ValueError("Force-derivative deadband cannot be negative")
        if self.z_step_mm <= 0:
            raise ValueError("Force-control Z step must be greater than zero")
        if self.z_step_mm > self.max_offset_mm:
            raise ValueError("Force-control Z step exceeds the total Z correction limit")
        if self.measurement_window_s <= 0:
            raise ValueError("Force averaging window must be greater than zero")
        if self.measurement_window_s > self.derivative_interval_s:
            raise ValueError(
                "Force averaging window cannot exceed the derivative time step"
            )
        if self.signal_timeout_s <= 0 or self.max_offset_mm <= 0:
            raise ValueError("Force-control safety limits are invalid")
        if self.hard_error_n <= 0:
            raise ValueError("Force-control maximum target deviation must be positive")

    def metadata(self) -> dict:
        values = {f"force_hold_{key}": value for key, value in asdict(self).items()}
        values["force_hold_control_mode"] = "derivative"
        return values


@dataclass(frozen=True)
class ForceHoldDecision:
    kind: str
    measured_force_n: float
    target_force_n: float
    error_n: float
    derivative_n_s: float = 0.0
    sample_interval_s: float = 0.0
    direction: int = 0
    step_mm: float = 0.0
    reason: str = ""


class ForceHoldController:
    """Damp force changes using a fixed-period sign controller.

    A positive dF/dt commands the configured force-decreasing Z direction; a
    negative dF/dt commands the force-increasing direction. The confirmed load
    remains only as an independent absolute-deviation safety reference.
    """

    def __init__(self):
        self._lock = RLock()
        self.config = ForceHoldConfig()
        self.armed = False
        self.target_force_n = 0.0
        self.accumulated_offset_mm = 0.0
        self.correction_count = 0
        self.last_measured_force_n = 0.0
        self.last_error_n = 0.0
        self.last_derivative_n_s = 0.0
        self.last_reason = "disabled"
        self._previous_force_n = None
        self._previous_sample_monotonic = None
        self._next_derivative_at = None

    def arm(self, config: ForceHoldConfig, target_force_n: float, now: float) -> None:
        config.validate()
        target = float(target_force_n)
        if not isfinite(target) or target <= 0:
            raise ValueError("Force-control safety reference must be positive")

        with self._lock:
            self.config = config
            self.armed = bool(config.enabled)
            self.target_force_n = target
            self.accumulated_offset_mm = 0.0
            self.correction_count = 0
            self.last_measured_force_n = target
            self.last_error_n = 0.0
            self.last_derivative_n_s = 0.0
            self.last_reason = "armed" if self.armed else "disabled"
            self._previous_force_n = None
            self._previous_sample_monotonic = None
            self._next_derivative_at = float(now)

    def disarm(self, reason: str = "disabled") -> None:
        with self._lock:
            self.armed = False
            self.last_reason = str(reason)
            self._previous_force_n = None
            self._previous_sample_monotonic = None
            self._next_derivative_at = None

    def evaluate(
        self,
        measured_force_n: float,
        sample_monotonic: float,
        now: float,
    ) -> ForceHoldDecision:
        measured = float(measured_force_n)
        sample_time = float(sample_monotonic)
        now = float(now)

        with self._lock:
            error = self.target_force_n - measured
            self.last_measured_force_n = measured
            self.last_error_n = error

            invalid = not isfinite(measured) or not isfinite(sample_time)
            if not self.armed:
                return self._decision("idle", measured, error, reason="disabled")
            if invalid:
                return self._abort(measured, error, "invalid_signal")
            if now - sample_time > self.config.signal_timeout_s:
                return self._abort(measured, error, "stale_signal")
            if abs(error) > self.config.hard_error_n:
                return self._abort(measured, error, "force_error_limit")

            if self._previous_force_n is None:
                self._previous_force_n = measured
                self._previous_sample_monotonic = sample_time
                self._next_derivative_at = now + self.config.derivative_interval_s
                self.last_reason = "collecting_baseline"
                return self._decision(
                    "wait", measured, error, reason=self.last_reason
                )

            next_at = float(self._next_derivative_at)
            if now + 1e-12 < next_at:
                self.last_reason = "sampling_interval"
                return self._decision(
                    "wait", measured, error, reason=self.last_reason
                )
            if sample_time <= float(self._previous_sample_monotonic) + 1e-12:
                self.last_reason = "waiting_new_sample"
                return self._decision(
                    "wait", measured, error, reason=self.last_reason
                )

            fixed_dt = self.config.derivative_interval_s
            derivative = (measured - float(self._previous_force_n)) / fixed_dt
            self.last_derivative_n_s = derivative
            self._previous_force_n = measured
            self._previous_sample_monotonic = sample_time
            if now - next_at >= fixed_dt:
                self._next_derivative_at = now + fixed_dt
            else:
                self._next_derivative_at = next_at + fixed_dt

            if abs(derivative) <= self.config.derivative_deadband_n_s:
                self.last_reason = "derivative_deadband"
                return self._decision(
                    "hold",
                    measured,
                    error,
                    derivative=derivative,
                    sample_interval=fixed_dt,
                    reason=self.last_reason,
                )

            force_direction = -1 if derivative > 0 else 1
            z_direction = (
                force_direction
                if self.config.z_positive_increases_force
                else -force_direction
            )
            proposed_offset = (
                self.accumulated_offset_mm + z_direction * self.config.z_step_mm
            )
            if abs(proposed_offset) > self.config.max_offset_mm + 1e-12:
                return self._abort(
                    measured,
                    error,
                    "z_travel_limit",
                    derivative=derivative,
                    sample_interval=fixed_dt,
                )

            self.last_reason = "correction_requested"
            return self._decision(
                "correct",
                measured,
                error,
                derivative=derivative,
                sample_interval=fixed_dt,
                direction=z_direction,
                step_mm=self.config.z_step_mm,
                reason=self.last_reason,
            )

    def accept(self, decision: ForceHoldDecision) -> None:
        if decision.kind != "correct":
            raise ValueError("Only a correction decision can be accepted")
        with self._lock:
            if not self.armed:
                return
            self.accumulated_offset_mm += decision.direction * decision.step_mm
            self.correction_count += 1
            self.last_reason = "correction_applied"

    def snapshot(self) -> dict:
        with self._lock:
            values = self.config.metadata()
            values.update(
                {
                    "force_hold_armed": self.armed,
                    "force_hold_target_n": self.target_force_n,
                    "force_hold_measured_n": self.last_measured_force_n,
                    "force_hold_error_n": self.last_error_n,
                    "force_hold_derivative_n_s": self.last_derivative_n_s,
                    "force_hold_accumulated_z_mm": self.accumulated_offset_mm,
                    "force_hold_correction_count": self.correction_count,
                    "force_hold_status": self.last_reason,
                }
            )
            return values

    def _abort(
        self,
        measured,
        error,
        reason,
        derivative=0.0,
        sample_interval=0.0,
    ):
        self.last_reason = str(reason)
        return self._decision(
            "abort",
            measured,
            error,
            derivative=derivative,
            sample_interval=sample_interval,
            reason=self.last_reason,
        )

    def _decision(
        self,
        kind,
        measured,
        error,
        derivative=0.0,
        sample_interval=0.0,
        direction=0,
        step_mm=0.0,
        reason="",
    ):
        return ForceHoldDecision(
            kind=str(kind),
            measured_force_n=float(measured),
            target_force_n=float(self.target_force_n),
            error_n=float(error),
            derivative_n_s=float(derivative),
            sample_interval_s=float(sample_interval),
            direction=int(direction),
            step_mm=float(step_mm),
            reason=str(reason),
        )
