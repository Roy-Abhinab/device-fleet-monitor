"""Mini Device Fleet Monitor API.

Endpoints:
    POST /devices                     register a device
    POST /devices/{device_id}/heartbeat   record a heartbeat
    GET  /devices                     list all devices (optionally filter by status)
    GET  /devices/{device_id}         get a single device's details
    GET  /summary                     fleet-wide online/offline counts
    GET  /health                      basic liveness check
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query

from .models import (
    DeviceDetailResponse,
    DeviceRegisterRequest,
    DeviceSummaryResponse,
    FleetSummaryResponse,
    HeartbeatRequest,
)
from .store import Device, store, utcnow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("fleet_monitor")

app = FastAPI(
    title="Mini Device Fleet Monitor",
    description="Tracks heartbeats from a fleet of simulated devices.",
    version="1.0.0",
)


def _to_summary(device: Device) -> DeviceSummaryResponse:
    return DeviceSummaryResponse(
        id=device.id,
        name=device.name,
        status=device.computed_status(),
        last_heartbeat=device.last_heartbeat,
    )


def _to_detail(device: Device) -> DeviceDetailResponse:
    return DeviceDetailResponse(
        id=device.id,
        name=device.name,
        status=device.computed_status(),
        last_heartbeat=device.last_heartbeat,
        registered_at=device.registered_at,
        reported_status=device.reported_status,
        metrics=device.metrics,
    )


@app.post("/devices", response_model=DeviceDetailResponse, status_code=201)
def register_device(payload: DeviceRegisterRequest) -> DeviceDetailResponse:
    """Register a new device. 409 if the id is already taken."""
    try:
        device = store.register(payload.id, payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    logger.info("registered device id=%s name=%s", device.id, device.name)
    return _to_detail(device)


@app.post("/devices/{device_id}/heartbeat", response_model=DeviceDetailResponse)
def receive_heartbeat(device_id: str, payload: HeartbeatRequest) -> DeviceDetailResponse:
    """Record a heartbeat for a registered device. 404 if unknown."""
    try:
        device = store.record_heartbeat(
            device_id,
            payload.timestamp,
            payload.status,
            payload.extra_metrics(),
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail=f"device '{device_id}' not found"
        ) from exc
    logger.info(
        "heartbeat device_id=%s reported_status=%s", device.id, payload.status
    )
    return _to_detail(device)


@app.get("/devices", response_model=List[DeviceSummaryResponse])
def list_devices(
    status: Optional[str] = Query(
        None,
        pattern="^(ONLINE|OFFLINE)$",
        description="Optional filter: ONLINE or OFFLINE",
    )
) -> List[DeviceSummaryResponse]:
    """List all registered devices with their current computed status."""
    summaries = [_to_summary(d) for d in store.list_all()]
    if status:
        summaries = [s for s in summaries if s.status == status]
    return summaries


@app.get("/devices/{device_id}", response_model=DeviceDetailResponse)
def get_device(device_id: str) -> DeviceDetailResponse:
    """Get full details for a single device. 404 if unknown."""
    device = store.get(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail=f"device '{device_id}' not found")
    return _to_detail(device)


@app.get("/summary", response_model=FleetSummaryResponse)
def fleet_summary() -> FleetSummaryResponse:
    """Fleet-wide counts of total/online/offline devices."""
    devices = store.list_all()
    online = sum(1 for d in devices if d.computed_status() == "ONLINE")
    total = len(devices)
    return FleetSummaryResponse(total=total, online=online, offline=total - online)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "time": utcnow().isoformat()}
