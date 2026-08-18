class LedIndicatorManager:
    CHANNEL_COUNT = 16

    def __init__(self, ui, threshold_mA=1.0, config=None):
        self.ui = ui
        self.config = config
        self.threshold = threshold_mA
        self.apply_config()

    def apply_config(self):
        if self.config is not None:
            self.threshold = self.config.led_threshold_mA

    def channel_to_led_index(self, channel_index: int) -> int:
        return self.CHANNEL_COUNT - 1 - channel_index

    def set_led(self, index: int, on: bool):
        w = getattr(self.ui, f"led{index}Widget", None)
        if not w:
            return

        if on:
            w.setStyleSheet("""
                background-color: #2196F3;
                border: 1px solid #0D47A1;
                border-radius: 18px;
            """)
        else:
            w.setStyleSheet("""
                background-color: white;
                border: 1px solid #999;
                border-radius: 18px;
            """)

    def update_from_currents(self, currents: dict):
        """
        currents: {"ai0": current_mA, "ai1": current_mA, ...}
        Display order is reversed: leftmost LED is channel 16, rightmost is channel 1.
        """
        for ch, current in currents.items():
            try:
                channel_index = int(ch.replace("ai", ""))
            except ValueError:
                continue

            if not 0 <= channel_index < self.CHANNEL_COUNT:
                continue

            self.set_led(
                self.channel_to_led_index(channel_index),
                current > self.threshold,
            )

    def reset_all(self):
        for i in range(self.CHANNEL_COUNT):
            self.set_led(i, False)
