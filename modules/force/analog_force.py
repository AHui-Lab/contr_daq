from dataclasses import dataclass

import numpy as np


VOLTAGE_RANGE_LIMITS = {
    "0-10V": (0.0, 10.0),
    "0-5V": (0.0, 5.0),
    "-10-10V": (-10.0, 10.0),
    "-5-5V": (-5.0, 5.0),
}


@dataclass(frozen=True)
class AnalogForceConfig:
    voltage_range: str = "0-10V"
    full_scale_force: float = 98.0665

    @property
    def signal_voltage_limits(self) -> tuple[float, float]:
        """Configured transmitter output limits."""
        try:
            return VOLTAGE_RANGE_LIMITS[self.voltage_range]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported analog force voltage range: {self.voltage_range}"
            ) from exc

    @property
    def daq_input_limits(self) -> tuple[float, float]:
        """Bipolar NI input limits required for the selected output range."""
        low, high = self.signal_voltage_limits
        magnitude = max(abs(low), abs(high))
        return -magnitude, magnitude

    @property
    def force_per_volt(self) -> float:
        low, high = self.signal_voltage_limits
        magnitude = max(abs(low), abs(high))
        if magnitude <= 0 or self.full_scale_force <= 0:
            raise ValueError("Analog force full scale must be greater than zero")
        return self.full_scale_force / magnitude


def convert_voltages_to_force(voltages, config: AnalogForceConfig) -> np.ndarray:
    values = np.asarray(voltages, dtype=float)
    return values * config.force_per_volt
