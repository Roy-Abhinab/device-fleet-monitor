"""In-memory, thread-safe storage and status logic for the device fleet."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional

# A device is ONLINE if a heartbeat has arrived within this many seconds.
ONLINE_THRESHOLD_SECONDS = 30


def utcnow() -> datetime:
    """Timezone-aware current time (UTC). Centralised so it's easy to see
    everywhere the "current time" concept is used, and to keep all stored
    timestamps timezone-aware (naive/aware comparisons throw at runtime)."""
    return datetime.now(timezone.utc)


@dataclass
class Device:
    id: str
    name: str
    registered_at: datetime
    last_heartbeat: Optional[datetime] = None
    reported_status: Optional[str] = None
    metrics: dict = field(default_factory=dict)

    def computed_status(self, now: Optional[datetime] = None) -> str:
        """ONLINE/OFFLINE derived from last_heartbeat, computed at read time
        rather than stored, so it's always correct and there is no background
        job or timer to keep in sync."""
        now = now or utcnow()
        if self.last_heartbeat is None:
            return "OFFLINE"
        age_seconds = (now - self.last_heartbeat).total_seconds()
        return "ONLINE" if age_seconds <= ONLINE_THRESHOLD_SECONDS else "OFFLINE"


class DeviceStore:
    """Thread-safe in-memory device registry.

    A single lock guards every read/mutation of the underlying dict. Given
    the expected scale of this exercise (a handful of simulated devices)
    a coarse-grained lock is simple, correct, and fast enough. See the
    README's "Known limitations" section for how this would change for a
    real, persistent, multi-process deployment.
    """

    def __init__(self) -> None:
        self._devices: Dict[str, Device] = {}
        self._lock = threading.Lock()

    def register(self, device_id: str, name: str) -> Device:
        with self._lock:
            if device_id in self._devices:
                raise ValueError(f"device '{device_id}' is already registered")
            device = Device(id=device_id, name=name, registered_at=utcnow())
            self._devices[device_id] = device
            return device

    def record_heartbeat(
        self,
        device_id: str,
        timestamp: Optional[datetime],
        reported_status: Optional[str],
        metrics: dict,
    ) -> Device:
        with self._lock:
            device = self._devices.get(device_id)
            if device is None:
                raise KeyError(device_id)
            device.last_heartbeat = timestamp or utcnow()
            if reported_status is not None:
                device.reported_status = reported_status
            if metrics:
                device.metrics.update(metrics)
            return device

    def get(self, device_id: str) -> Optional[Device]:
        with self._lock:
            return self._devices.get(device_id)

    def list_all(self):
        with self._lock:
            # Return a shallow copy of the list so callers iterating over it
            # aren't affected by concurrent registrations.
            return list(self._devices.values())

    def clear(self) -> None:
        """Used by tests to reset state between cases."""
        with self._lock:
            self._devices.clear()


# Single process-wide store. Fine for this exercise; see README for how a
# real deployment would swap this for a persistent backend.
store = DeviceStore()
