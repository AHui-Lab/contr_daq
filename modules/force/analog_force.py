from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class AnalogForceConfig:
    voltage_range: str = "0-10V"
    full_scale_force: float = 98.0665


def convert_voltages_to_force(voltages, config: AnalogForceConfig) -> np.ndarray:
    values = np.asarray(voltages, dtype=float)

    if config.voltage_range == "0-10V":
        scale = config.full_scale_force / 10.0
    elif config.voltage_range == "0-5V":
        scale = config.full_scale_force / 5.0
    elif config.voltage_range == "-10-10V":
        scale = config.full_scale_force / 10.0
    elif config.voltage_range == "-5-5V":
        scale = config.full_scale_force / 5.0
    else:
        raise ValueError(f"Unsupported analog force voltage range: {config.voltage_range}")

    return values * scale
