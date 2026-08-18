from dataclasses import dataclass


@dataclass(frozen=True)
class AppState:
    daq_running: bool = False
    ao_running: bool = False
    iv_running: bool = False
    camera_1_running: bool = False
    camera_2_running: bool = False
    motion_running: bool = False
    force_running: bool = False
    recording: bool = False

    @property
    def any_running(self) -> bool:
        return any(
            (
                self.daq_running,
                self.ao_running,
                self.iv_running,
                self.camera_1_running,
                self.camera_2_running,
                self.motion_running,
                self.force_running,
                self.recording,
            )
        )

    @property
    def summary(self) -> dict[str, str]:
        return {
            "daq": "Sampling" if self.daq_running else "Idle",
            "camera": self._camera_summary(),
            "motion": "Scanning" if self.motion_running else "Ready",
            "force": "Streaming" if self.force_running else "Idle",
            "recording": "On" if self.recording else "Off",
        }

    def _camera_summary(self) -> str:
        if self.camera_1_running and self.camera_2_running:
            return "Both"
        if self.camera_1_running:
            return "Camera 1"
        if self.camera_2_running:
            return "Camera 2"
        return "Idle"
