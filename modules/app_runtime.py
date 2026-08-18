from dataclasses import dataclass
from enum import Enum
from threading import RLock


class RuntimeStatus(str, Enum):
    DISCONNECTED = "disconnected"
    READY = "ready"
    CONNECTING = "connecting"
    RUNNING = "running"
    STOPPING = "stopping"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class RuntimeEntry:
    status: RuntimeStatus = RuntimeStatus.READY
    detail: str = ""


class RuntimeStateStore:
    SUBSYSTEMS = (
        "daq",
        "ao",
        "iv",
        "camera_1",
        "camera_2",
        "motion",
        "force",
        "recording",
        "scan",
    )

    def __init__(self):
        self._lock = RLock()
        self._entries = {name: RuntimeEntry() for name in self.SUBSYSTEMS}

    def set(self, subsystem: str, status: RuntimeStatus, detail: str = "") -> None:
        with self._lock:
            self._entries[subsystem] = RuntimeEntry(RuntimeStatus(status), str(detail))

    def get(self, subsystem: str) -> RuntimeEntry:
        with self._lock:
            return self._entries.get(subsystem, RuntimeEntry())

    def snapshot(self) -> dict[str, RuntimeEntry]:
        with self._lock:
            return dict(self._entries)

    def is_running(self, subsystem: str) -> bool:
        return self.get(subsystem).status == RuntimeStatus.RUNNING


class ResourceArbiter:
    """Prevents two controllers from owning the same NI subsystem."""

    def __init__(self):
        self._lock = RLock()
        self._owners: dict[str, str] = {}

    def acquire(self, owner: str, resources) -> tuple[bool, str]:
        requested = {resource for resource in resources if resource}
        with self._lock:
            conflicts = {
                resource: current_owner
                for resource in requested
                if (current_owner := self._owners.get(resource)) not in (None, owner)
            }
            if conflicts:
                detail = ", ".join(
                    f"{resource} is in use by {current_owner}"
                    for resource, current_owner in sorted(conflicts.items())
                )
                return False, detail
            for resource in requested:
                self._owners[resource] = owner
        return True, ""

    def release(self, owner: str) -> None:
        with self._lock:
            for resource, current_owner in list(self._owners.items()):
                if current_owner == owner:
                    self._owners.pop(resource, None)

    def snapshot(self) -> dict[str, str]:
        with self._lock:
            return dict(self._owners)


def ni_resource(device_or_channel: str, subsystem: str) -> str:
    device = (device_or_channel or "").split("/", 1)[0].strip()
    return f"ni:{device}:{subsystem}" if device else ""
