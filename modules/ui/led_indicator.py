class LedIndicatorManager:
    def __init__(self, ui, threshold_mA=1.0):
        self.ui = ui
        self.threshold = threshold_mA

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
        """
        for ch, current in currents.items():
            try:
                idx = int(ch.replace("ai", ""))
            except ValueError:
                continue

            self.set_led(idx, current > self.threshold)

    def reset_all(self):
        for i in range(16):
            self.set_led(i, False)
