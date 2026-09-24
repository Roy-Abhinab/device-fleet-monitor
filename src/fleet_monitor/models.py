"""Request parsing/validation and response serialization helpers.

Deliberately dependency-free (no pydantic) so the whole project only needs
Flask + the standard library.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


class ValidationError(Exception):
    """Raised when a request body fails validation. The message is returned
    to the caller as-is, so keep it short and human-readable."""


def parse_timestamp(raw) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp string.

    Tolerates a trailing 'Z' (UTC), which datetime.fromisoformat only
    accepts natively on Python 3.11+; handling it manually keeps this
    working on older interpreters too.
    """
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise ValidationError("'timestamp' must be an ISO-8601 string")
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ValidationError(f"invalid 'timestamp': {raw!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@dataclass
class DeviceRegisterRequest:
    id: str
    name: str

    @classmethod
    def from_json(cls, body: Optional[dict]) -> "DeviceRegisterRequest":
        if not isinstance(body, dict):
            raise ValidationError("request body must be a JSON object")
        device_id = body.get("id")
        name = body.get("name")
        if not isinstance(device_id, str) or not device_id.strip():
            raise ValidationError("'id' is required and must be a non-empty string")
        if not isinstance(name, str) or not name.strip():
            raise ValidationError("'name' is required and must be a non-empty string")
        return cls(id=device_id.strip(), name=name.strip())


@dataclass
class HeartbeatRequest:
    timestamp: Optional[datetime]
    status: Optional[str]
    metrics: dict

    @classmethod
    def from_json(cls, body: Optional[dict]) -> "HeartbeatRequest":
        body = body or {}
        if not isinstance(body, dict):
            raise ValidationError("request body must be a JSON object")

        timestamp = parse_timestamp(body.get("timestamp"))

        status = body.get("status")
        if status is not None and not isinstance(status, str):
            raise ValidationError("'status' must be a string")

        metrics = {}
        for key in ("cpu_usage", "signal_strength"):
            value = body.get(key)
            if value is None:
                continue
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValidationError(f"'{key}' must be a number")
            metrics[key] = value

        return cls(timestamp=timestamp, status=status, metrics=metrics)


def device_to_summary(device) -> dict:
    return {
        "id": device.id,
        "name": device.name,
        "status": device.computed_status(),
        "last_heartbeat": (
            device.last_heartbeat.isoformat() if device.last_heartbeat else None
        ),
    }


def device_to_detail(device) -> dict:
    detail = device_to_summary(device)
    detail.update(
        {
            "registered_at": device.registered_at.isoformat(),
            "reported_status": device.reported_status,
            "metrics": device.metrics,
        }
    )
    return detail
