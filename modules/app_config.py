import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class AppConfig:
    ui_language: str = "en"
    operator_name: str = ""
    data_save_dir: str = "data"
    channel_count: int = 16
    default_sample_resistance_ohm: float = 100.0
    default_amplify_gain: float = 5.02
    led_threshold_mA: float = 0.2
    max_display_points: int = 1200
    daq_chunk_interval_s: float = 0.05
    min_daq_chunk_size: int = 100
    max_daq_chunk_size: int = 10000
    force_serial_port: str = "COM15"
    force_serial_baudrate: int = 9600
    force_safety_total_high_n: float = 0.0
    force_safety_channel_high_n: float = 0.0
    force_safety_imbalance_n: float = 0.0
    force_safety_rise_rate_n_s: float = 0.0
    force_safety_retract_enabled: bool = False
    force_safety_retract_mm: float = 0.002
    force_commission_tolerance_n: float = 0.2
    force_commission_z_step_mm: float = 0.0001
    force_commission_control_interval_s: float = 0.15
    force_commission_confirm_s: float = 0.05
    force_commission_max_offset_mm: float = 0.01
    camera_1_index: int = 0
    camera_2_index: int = 1
    sample_resistances_ohm: list[float] = field(default_factory=list)
    amplify_gains: list[float] = field(default_factory=list)

    def __post_init__(self):
        from modules.ui.i18n import normalize_language

        self.ui_language = normalize_language(self.ui_language)
        self.operator_name = str(self.operator_name or "").strip()
        self.data_save_dir = str(self.data_save_dir or "data").strip() or "data"
        self.force_serial_port = (
            str(self.force_serial_port or "COM15").strip() or "COM15"
        )
        self.force_serial_baudrate = max(int(self.force_serial_baudrate), 1)
        self.force_safety_total_high_n = max(
            float(self.force_safety_total_high_n), 0.0
        )
        self.force_safety_channel_high_n = max(
            float(self.force_safety_channel_high_n), 0.0
        )
        self.force_safety_imbalance_n = max(
            float(self.force_safety_imbalance_n), 0.0
        )
        self.force_safety_rise_rate_n_s = max(
            float(self.force_safety_rise_rate_n_s), 0.0
        )
        self.force_safety_retract_enabled = bool(
            self.force_safety_retract_enabled
        )
        self.force_safety_retract_mm = max(
            float(self.force_safety_retract_mm), 0.0001
        )
        self.force_commission_tolerance_n = max(
            float(self.force_commission_tolerance_n), 0.001
        )
        self.force_commission_z_step_mm = min(
            max(float(self.force_commission_z_step_mm), 0.0001),
            0.01,
        )
        self.force_commission_control_interval_s = max(
            float(self.force_commission_control_interval_s), 0.02
        )
        self.force_commission_confirm_s = max(
            float(self.force_commission_confirm_s), 0.0
        )
        self.force_commission_max_offset_mm = max(
            float(self.force_commission_max_offset_mm),
            self.force_commission_z_step_mm,
        )
        self.camera_1_index = max(int(self.camera_1_index), 0)
        self.camera_2_index = max(int(self.camera_2_index), 0)
        if not self.sample_resistances_ohm:
            self.sample_resistances_ohm = [
                self.default_sample_resistance_ohm
                for _ in range(self.channel_count)
            ]
        if not self.amplify_gains:
            self.amplify_gains = [
                self.default_amplify_gain
                for _ in range(self.channel_count)
            ]
        self.sample_resistances_ohm = self._normalized_channel_values(
            self.sample_resistances_ohm,
            self.default_sample_resistance_ohm,
        )
        self.amplify_gains = self._normalized_channel_values(
            self.amplify_gains,
            self.default_amplify_gain,
        )

    @classmethod
    def load(cls, path: str | Path) -> "AppConfig":
        config_path = Path(path)
        if not config_path.exists():
            return cls()

        with config_path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        valid_keys = cls.__dataclass_fields__.keys()
        filtered = {
            key: value
            for key, value in data.items()
            if key in valid_keys
        }
        return cls(**filtered)

    def save(self, path: str | Path):
        config_path = Path(path)
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("w", encoding="utf-8") as file:
            json.dump(asdict(self), file, ensure_ascii=False, indent=2)

    def reset_to_defaults(self):
        defaults = type(self)()
        for key, value in asdict(defaults).items():
            setattr(self, key, value)

    def current_mA(self, channel: str | int, voltage: float) -> float:
        index = self.channel_index(channel)
        resistance = self.sample_resistances_ohm[index]
        gain = self.amplify_gains[index]
        if resistance <= 0 or gain <= 0:
            return 0.0
        return float(voltage) / (resistance * gain) * 1000.0

    def channel_index(self, channel: str | int) -> int:
        if isinstance(channel, str):
            index = int(channel.replace("ai", ""))
        else:
            index = int(channel)
        if not 0 <= index < self.channel_count:
            raise ValueError(f"Channel index out of range: {channel}")
        return index

    def daq_chunk_size(self, sample_rate: int | float) -> int:
        size = round(float(sample_rate) * self.daq_chunk_interval_s)
        return max(
            self.min_daq_chunk_size,
            min(int(size), self.max_daq_chunk_size),
        )

    def _normalized_channel_values(
        self,
        values: list[float],
        default_value: float,
    ) -> list[float]:
        normalized = [float(value) for value in values[:self.channel_count]]
        while len(normalized) < self.channel_count:
            normalized.append(float(default_value))
        return normalized
