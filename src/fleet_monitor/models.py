"""Pydantic request/response schemas for the Fleet Monitor API."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DeviceRegisterRequest(BaseModel):
    id: str = Field(..., min_length=1, description="Unique device identifier")
    name: str = Field(..., min_length=1, description="Human-readable device name")


class HeartbeatRequest(BaseModel):
    timestamp: Optional[datetime] = None
    status: Optional[str] = None
    cpu_usage: Optional[float] = None
    signal_strength: Optional[float] = None

    def extra_metrics(self) -> dict:
        """Collects the optional metric fields into a single dict so the
        store doesn't need to know about each field individually."""
        metrics = {}
        if self.cpu_usage is not None:
            metrics["cpu_usage"] = self.cpu_usage
        if self.signal_strength is not None:
            metrics["signal_strength"] = self.signal_strength
        return metrics


class DeviceSummaryResponse(BaseModel):
    id: str
    name: str
    status: str
    last_heartbeat: Optional[datetime] = None


class DeviceDetailResponse(DeviceSummaryResponse):
    registered_at: datetime
    reported_status: Optional[str] = None
    metrics: dict = {}


class FleetSummaryResponse(BaseModel):
    total: int
    online: int
    offline: int
