from dataclasses import asdict, dataclass
from math import isfinite
from threading import RLock


@dataclass(frozen=True)
class ForceHoldConfig:
    enabled: bool = False
    fast_response: bool = False
    tolerance_n: float = 0.20
    z_step_mm: float = 0.0020
    control_interval_s: float = 0.15
    outside_confirm_s: float = 0.05
    measurement_window_s: float = 0.05
    signal_timeout_s: float = 0.25
    max_offset_mm: float = 0.0500
    hard_error_n: float = 1.0
    z_positive_increases_force: bool = True

    def validate(self) -> None:
        if self.tolerance_n <= 0:
            raise ValueError("Force-hold tolerance must be greater than zero")
        if self.z_step_mm <= 0:
            raise ValueError("Force-hold Z step must be greater than zero")
        if self.z_step_mm > self.max_offset_mm:
            raise ValueError("Force-hold Z step exceeds the total Z correction limit")
        if (
            self.control_interval_s <= 0
            or self.outside_confirm_s < 0
            or self.measurement_window_s <= 0
        ):
            raise ValueError("Force-hold timing values are invalid")
        if self.signal_timeout_s <= 0 or self.max_offset_mm <= 0:
            raise ValueError("Force-hold safety limits are invalid")
        if self.hard_error_n <= self.tolerance_n:
            raise ValueError("Force-hold hard error limit must exceed its tolerance")

    def metadata(self) -> dict:
        return {f"force_hold_{key}": value for key, value in asdict(self).items()}


@dataclass(frozen=True)
class ForceHoldDecision:
    kind: str
    measured_force_n: float
    target_force_n: float
    error_n: float
    direction: int = 0
    step_mm: float = 0.0
    reason: str = ""


class ForceHoldController:
    """Conservative dead-band force control for small Z corrections."""

    def __init__(self):
        self._lock = RLock()
        self.config = ForceHoldConfig()
        self.armed = False
        self.target_force_n = 0.0
        self.accumulated_offset_mm = 0.0
        self.correction_count = 0
        self.last_measured_force_n = 0.0
        self.last_error_n = 0.0
        self.last_reason = "disabled"
        self._outside_direction = 0
        self._outside_since = None
        self._last_attempt_at = float("-inf")

    def arm(self, config: ForceHoldConfig, target_force_n: float, now: float) -> None:
        config.validate()
        target = float(target_force_n)
        if not isfinite(target) or target <= 0:
            raise ValueError("Force-hold target must be positive")

        with self._lock:
            self.config = config
            self.armed = bool(config.enabled)
            self.target_force_n = target
            self.accumulated_offset_mm = 0.0
            self.correction_count = 0
            self.last_measured_force_n = target
            self.last_error_n = 0.0
            self.last_reason = "armed" if self.armed else "disabled"
            self._outside_direction = 0
            self._outside_since = None
            self._last_attempt_at = float(now)

    def disarm(self, reason: str = "disabled") -> None:
        with self._lock:
            self.armed = False
            self.last_reason = str(reason)
            self._outside_direction = 0
            self._outside_since = None

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
            target = self.target_force_n
            error = target - measured
            self.last_measured_force_n = measured
            self.last_error_n = error

            if not self.armed:
                return self._decision("idle", measured, error, reason="disabled")
            if not isfinite(measured) or not isfinite(sample_time):
                self.last_reason = "invalid_signal"
                return self._decision("abort", measured, error, reason=self.last_reason)
            if now - sample_time > self.config.signal_timeout_s:
                self.last_reason = "stale_signal"
                return self._decision("abort", measured, error, reason=self.last_reason)
            if abs(error) > self.config.hard_error_n:
                self.last_reason = "force_error_limit"
                return self._decision("abort", measured, error, reason=self.last_reason)
            if abs(error) <= self.config.tolerance_n:
                self._reset_outside("within_tolerance")
                return self._decision("hold", measured, error, reason=self.last_reason)

            force_direction = 1 if error > 0 else -1
            z_direction = (
                force_direction
                if self.config.z_positive_increases_force
                else -force_direction
            )
            if z_direction != self._outside_direction:
                self._outside_direction = z_direction
                self._outside_since = now
                self.last_reason = "confirming_error"
                return self._decision("wait", measured, error, reason=self.last_reason)
            if (
                self._outside_since is None
                or now - self._outside_since < self.config.outside_confirm_s
            ):
                self.last_reason = "confirming_error"
                return self._decision("wait", measured, error, reason=self.last_reason)
            if now - self._last_attempt_at < self.config.control_interval_s:
                self.last_reason = "settling"
                return self._decision("wait", measured, error, reason=self.last_reason)

            proposed_offset = (
                self.accumulated_offset_mm + z_direction * self.config.z_step_mm
            )
            if abs(proposed_offset) > self.config.max_offset_mm + 1e-12:
                self.last_reason = "z_travel_limit"
                return self._decision("abort", measured, error, reason=self.last_reason)

            self._last_attempt_at = now
            self.last_reason = "correction_requested"
            return self._decision(
                "correct",
                measured,
                error,
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
            self._outside_direction = 0
            self._outside_since = None

    def snapshot(self) -> dict:
        with self._lock:
            values = self.config.metadata()
            values.update(
                {
                    "force_hold_armed": self.armed,
                    "force_hold_target_n": self.target_force_n,
                    "force_hold_measured_n": self.last_measured_force_n,
                    "force_hold_error_n": self.last_error_n,
                    "force_hold_accumulated_z_mm": self.accumulated_offset_mm,
                    "force_hold_correction_count": self.correction_count,
                    "force_hold_status": self.last_reason,
                }
            )
            return values

    def _decision(
        self,
        kind,
        measured,
        error,
        direction=0,
        step_mm=0.0,
        reason="",
    ):
        return ForceHoldDecision(
            kind=str(kind),
            measured_force_n=float(measured),
            target_force_n=float(self.target_force_n),
            error_n=float(error),
            direction=int(direction),
            step_mm=float(step_mm),
            reason=str(reason),
        )

    def _reset_outside(self, reason):
        self._outside_direction = 0
        self._outside_since = None
        self.last_reason = str(reason)
