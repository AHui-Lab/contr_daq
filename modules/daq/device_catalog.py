"""NI device discovery and UI-safe device identifiers.

The combo-box label is presentation data.  NI-DAQmx must always receive the
unchanged device name stored as item data.
"""

from dataclasses import dataclass
from math import floor


@dataclass(frozen=True)
class NiDeviceInfo:
    name: str
    product_type: str
    is_simulated: bool
    ai_channels: tuple[str, ...]
    ao_channels: tuple[str, ...]
    max_single_channel_rate: float
    max_multi_channel_rate: float
    simultaneous_sampling: bool = False
    ao_voltage_ranges: tuple[tuple[float, float], ...] = ()

    @property
    def display_label(self) -> str:
        return f"{self.name} · SIM" if self.is_simulated else self.name

    def ai_rate_limit(self, channel_count: int = 1) -> int:
        channel_count = max(1, int(channel_count))
        single_rate = max(0.0, self.max_single_channel_rate)
        multi_rate = max(0.0, self.max_multi_channel_rate)
        if channel_count <= 1:
            rate = single_rate or multi_rate
        elif self.simultaneous_sampling:
            rate = multi_rate or single_rate
        else:
            aggregate_rate = multi_rate or single_rate
            rate = aggregate_rate / channel_count
            if single_rate:
                rate = min(single_rate, rate)
        return max(0, floor(rate))

    def has_ai_channel(self, channel: str) -> bool:
        return _channel_suffix(channel) in self.ai_channels

    def ao_range_for(self, minimum: float, maximum: float):
        low, high = sorted((float(minimum), float(maximum)))
        compatible = [
            voltage_range
            for voltage_range in self.ao_voltage_ranges
            if voltage_range[0] <= low and high <= voltage_range[1]
        ]
        if not compatible:
            return None
        return min(compatible, key=lambda item: item[1] - item[0])


def discover_ni_devices(system=None) -> tuple[NiDeviceInfo, ...]:
    """Return a stable snapshot without retaining NI-DAQmx device objects."""

    if system is None:
        from nidaqmx.system import System

        system = System.local()

    devices = []
    for device in system.devices:
        devices.append(
            NiDeviceInfo(
                name=str(device.name),
                product_type=str(_safe_value(device, "product_type", "Unknown NI device")),
                is_simulated=bool(_safe_value(device, "is_simulated", False)),
                ai_channels=_physical_channel_names(device, "ai_physical_chans"),
                ao_channels=_physical_channel_names(device, "ao_physical_chans"),
                max_single_channel_rate=float(
                    _safe_value(device, "ai_max_single_chan_rate", 0.0) or 0.0
                ),
                max_multi_channel_rate=float(
                    _safe_value(device, "ai_max_multi_chan_rate", 0.0) or 0.0
                ),
                simultaneous_sampling=bool(
                    _safe_value(device, "ai_simultaneous_sampling_supported", False)
                ),
                ao_voltage_ranges=_voltage_ranges(device, "ao_voltage_rngs"),
            )
        )
    return tuple(devices)


def selected_device_name(combo) -> str:
    """Read the NI identifier from a combo, with support for simple test doubles."""

    if combo is None:
        return ""
    current_data = getattr(combo, "currentData", None)
    if callable(current_data):
        data = current_data()
        if data not in (None, ""):
            return str(data)
    current_text = getattr(combo, "currentText", None)
    text = str(current_text()).strip() if callable(current_text) else ""
    return text.split(" · ", 1)[0].strip()


def capability_tooltip(info: NiDeviceInfo, translator=None) -> str:
    status_key = "device.simulated" if info.is_simulated else "device.connected"
    status = _translate(translator, status_key)
    rate = max(0, floor(info.max_multi_channel_rate))
    ao_ranges = ", ".join(
        f"{low:g} to {high:g} V" for low, high in info.ao_voltage_ranges
    ) or _translate(translator, "device.not_reported")
    return _translate(
        translator,
        "device.capabilities",
        name=info.name,
        product=info.product_type,
        status=status,
        ai=len(info.ai_channels),
        ao=len(info.ao_channels),
        rate=f"{rate:,}",
        ao_range=ao_ranges,
    )


def _physical_channel_names(device, attribute: str) -> tuple[str, ...]:
    collection = _safe_value(device, attribute, ())
    try:
        return tuple(_channel_suffix(channel.name) for channel in collection)
    except Exception:
        return ()


def _voltage_ranges(device, attribute: str) -> tuple[tuple[float, float], ...]:
    values = _safe_value(device, attribute, ())
    try:
        numbers = [float(value) for value in values]
    except Exception:
        return ()
    return tuple(
        (min(numbers[index], numbers[index + 1]), max(numbers[index], numbers[index + 1]))
        for index in range(0, len(numbers) - 1, 2)
    )


def _channel_suffix(channel: str) -> str:
    return str(channel).rsplit("/", 1)[-1]


def _safe_value(obj, attribute: str, default):
    try:
        return getattr(obj, attribute)
    except Exception:
        return default


def _translate(translator, key: str, **values) -> str:
    if translator is None:
        fallbacks = {
            "device.simulated": "Simulated NI device",
            "device.connected": "NI device",
            "device.not_reported": "not reported",
            "device.capabilities": (
                "{name} · {product}\n{status} · {ai} AI / {ao} AO\n"
                "AI aggregate rate: {rate} S/s\nAO ranges: {ao_range}"
            ),
        }
        return fallbacks[key].format(**values)
    return translator(key, **values)
