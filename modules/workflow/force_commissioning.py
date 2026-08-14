import csv
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from threading import RLock


@dataclass(frozen=True)
class ForceSafetyConfig:
    """Independent force limits used before any Z correction is considered."""

    total_high_n: float
    channel_high_n: float = 0.0
    imbalance_high_n: float = 0.0
    rise_rate_high_n_s: float = 0.0
    signal_timeout_s: float = 0.15
    imbalance_confirm_s: float = 0.05
    rise_rate_confirm_s: float = 0.02

    def validate(self) -> None:
        if not isfinite(self.total_high_n) or self.total_high_n <= 0:
            raise ValueError("Total-force safety limit must be greater than zero")
        optional_limits = (
            self.channel_high_n,
            self.imbalance_high_n,
            self.rise_rate_high_n_s,
        )
        if any(not isfinite(value) or value < 0 for value in optional_limits):
            raise ValueError("Optional force safety limits cannot be negative")
        if self.signal_timeout_s <= 0:
            raise ValueError("Force signal timeout must be greater than zero")
        if self.imbalance_confirm_s < 0 or self.rise_rate_confirm_s < 0:
            raise ValueError("Force safety confirmation times cannot be negative")


@dataclass(frozen=True)
class ForceSafetyDecision:
    kind: str
    reason: str
    total_force_n: float
    channel_forces_n: tuple[float, ...]
    max_channel_force_n: float
    max_channel_index: int
    imbalance_n: float
    rise_rate_n_s: float
    detail: str = ""


class ForceSafetySupervisor:
    """Stateful, controller-independent force signal safety supervisor."""

    FUTURE_TIMESTAMP_TOLERANCE_S = 0.02
    RETRACT_REASONS = frozenset(
        {"total_force_high", "channel_force_high", "force_rise_rate_high"}
    )

    def __init__(self, config=None):
        self._lock = RLock()
        self.config = config
        self._previous_sample_time = None
        self._previous_total = None
        self._imbalance_since = None
        self._rise_rate_since = None

    def arm(self, config: ForceSafetyConfig) -> None:
        config.validate()
        with self._lock:
            self.config = config
            self._reset_state()

    def reset(self) -> None:
        with self._lock:
            self._reset_state()

    def evaluate(
        self,
        total_force_n,
        channel_forces_n,
        sample_monotonic,
        now,
    ) -> ForceSafetyDecision:
        total = float(total_force_n) if total_force_n is not None else float("nan")
        sample_time = (
            float(sample_monotonic)
            if sample_monotonic is not None
            else float("nan")
        )
        now = float(now)
        try:
            channels = tuple(float(value) for value in channel_forces_n)
        except (TypeError, ValueError):
            channels = ()

        with self._lock:
            config = self.config
            if config is None:
                return self._decision(
                    "trip", "not_armed", total, channels, detail="Safety supervisor is not armed"
                )

            if (
                not isfinite(total)
                or not isfinite(sample_time)
                or not isfinite(now)
                or not channels
                or any(not isfinite(value) for value in channels)
            ):
                return self._decision(
                    "trip", "invalid_signal", total, channels, detail="Force signal is invalid"
                )
            if sample_time > now + self.FUTURE_TIMESTAMP_TOLERANCE_S:
                return self._decision(
                    "trip",
                    "invalid_timestamp",
                    total,
                    channels,
                    detail=(
                        "Force sample timestamp is ahead of the control clock by "
                        f"{sample_time - now:.6f} s"
                    ),
                )
            if now - sample_time > config.signal_timeout_s:
                return self._decision(
                    "trip", "stale_signal", total, channels, detail="Force signal is stale"
                )

            if total >= config.total_high_n:
                return self._decision(
                    "trip",
                    "total_force_high",
                    total,
                    channels,
                    detail=f"Total force {total:.3f} N reached {config.total_high_n:.3f} N",
                )

            max_channel = max(channels)
            max_index = channels.index(max_channel)
            if config.channel_high_n > 0 and max_channel >= config.channel_high_n:
                return self._decision(
                    "trip",
                    "channel_force_high",
                    total,
                    channels,
                    detail=(
                        f"P{max_index + 1} force {max_channel:.3f} N reached "
                        f"{config.channel_high_n:.3f} N"
                    ),
                )

            imbalance = max(channels) - min(channels)
            if config.imbalance_high_n > 0 and imbalance >= config.imbalance_high_n:
                if self._imbalance_since is None:
                    self._imbalance_since = now
                if now - self._imbalance_since >= config.imbalance_confirm_s:
                    return self._decision(
                        "trip",
                        "force_imbalance_high",
                        total,
                        channels,
                        detail=(
                            f"Channel spread {imbalance:.3f} N reached "
                            f"{config.imbalance_high_n:.3f} N"
                        ),
                    )
            else:
                self._imbalance_since = None

            rise_rate = 0.0
            is_new_sample = (
                self._previous_sample_time is None
                or sample_time > self._previous_sample_time + 1e-12
            )
            if is_new_sample and self._previous_sample_time is not None:
                elapsed = sample_time - self._previous_sample_time
                if elapsed > 0:
                    rise_rate = (total - self._previous_total) / elapsed

            if is_new_sample:
                self._previous_sample_time = sample_time
                self._previous_total = total
                if (
                    config.rise_rate_high_n_s > 0
                    and rise_rate >= config.rise_rate_high_n_s
                ):
                    if self._rise_rate_since is None:
                        self._rise_rate_since = sample_time
                    if (
                        sample_time - self._rise_rate_since
                        >= config.rise_rate_confirm_s
                    ):
                        return self._decision(
                            "trip",
                            "force_rise_rate_high",
                            total,
                            channels,
                            rise_rate=rise_rate,
                            detail=(
                                f"Force rise rate {rise_rate:.3f} N/s reached "
                                f"{config.rise_rate_high_n_s:.3f} N/s"
                            ),
                        )
                else:
                    self._rise_rate_since = None

            waiting = self._imbalance_since is not None or self._rise_rate_since is not None
            return self._decision(
                "wait" if waiting else "ok",
                "confirming_limit" if waiting else "within_limits",
                total,
                channels,
                rise_rate=rise_rate,
            )

    def _decision(
        self,
        kind,
        reason,
        total,
        channels,
        rise_rate=0.0,
        detail="",
    ):
        finite_channels = [value for value in channels if isfinite(value)]
        if finite_channels:
            max_channel = max(finite_channels)
            max_index = channels.index(max_channel)
            imbalance = max(finite_channels) - min(finite_channels)
        else:
            max_channel = float("nan")
            max_index = -1
            imbalance = float("nan")
        return ForceSafetyDecision(
            kind=str(kind),
            reason=str(reason),
            total_force_n=float(total),
            channel_forces_n=tuple(channels),
            max_channel_force_n=float(max_channel),
            max_channel_index=int(max_index),
            imbalance_n=float(imbalance),
            rise_rate_n_s=float(rise_rate),
            detail=str(detail),
        )

    def _reset_state(self):
        self._previous_sample_time = None
        self._previous_total = None
        self._imbalance_since = None
        self._rise_rate_since = None


class ForceCommissioningLog:
    COLUMNS = (
        "elapsed_s",
        "sample_monotonic",
        "total_force_n",
        "p1_n",
        "p2_n",
        "p3_n",
        "p4_n",
        "target_force_n",
        "error_n",
        "z_offset_mm",
        "action",
        "status",
    )

    def __init__(self, started_monotonic):
        self.started_monotonic = float(started_monotonic)
        self.rows = []

    def append(
        self,
        now,
        sample_monotonic,
        total_force_n,
        channel_forces_n,
        target_force_n=0.0,
        z_offset_mm=0.0,
        action="monitor",
        status="within_limits",
    ):
        channels = list(channel_forces_n)[:4]
        channels.extend([float("nan")] * (4 - len(channels)))
        target = float(target_force_n)
        total = float(total_force_n)
        self.rows.append(
            {
                "elapsed_s": float(now) - self.started_monotonic,
                "sample_monotonic": float(sample_monotonic),
                "total_force_n": total,
                "p1_n": channels[0],
                "p2_n": channels[1],
                "p3_n": channels[2],
                "p4_n": channels[3],
                "target_force_n": target,
                "error_n": target - total,
                "z_offset_mm": float(z_offset_mm),
                "action": str(action),
                "status": str(status),
            }
        )

    def save(self, path):
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=self.COLUMNS)
            writer.writeheader()
            writer.writerows(self.rows)
        return output
