"""Mini Device Fleet Monitor API.

Endpoints:
    POST /devices                          register a device
    POST /devices/<device_id>/heartbeat    record a heartbeat
    GET  /devices                          list all devices (optional ?status= filter)
    GET  /devices/<device_id>              get a single device's details
    GET  /summary                          fleet-wide online/offline counts
    GET  /health                           basic liveness check
"""

from __future__ import annotations

import logging

from flask import Flask, jsonify, request

from .models import (
    DeviceRegisterRequest,
    HeartbeatRequest,
    ValidationError,
    device_to_detail,
    device_to_summary,
)
from .store import store, utcnow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger("fleet_monitor")


def create_app() -> Flask:
    app = Flask(__name__)

    @app.errorhandler(ValidationError)
    def handle_validation_error(exc: ValidationError):
        return jsonify({"error": str(exc)}), 422

    @app.post("/devices")
    def register_device():
        payload = DeviceRegisterRequest.from_json(request.get_json(silent=True))
        try:
            device = store.register(payload.id, payload.name)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 409
        logger.info("registered device id=%s name=%s", device.id, device.name)
        return jsonify(device_to_detail(device)), 201

    @app.post("/devices/<device_id>/heartbeat")
    def receive_heartbeat(device_id: str):
        payload = HeartbeatRequest.from_json(request.get_json(silent=True))
        try:
            device = store.record_heartbeat(
                device_id, payload.timestamp, payload.status, payload.metrics
            )
        except KeyError:
            return jsonify({"error": f"device '{device_id}' not found"}), 404
        logger.info(
            "heartbeat device_id=%s reported_status=%s", device.id, payload.status
        )
        return jsonify(device_to_detail(device)), 200

    @app.get("/devices")
    def list_devices():
        status_filter = request.args.get("status")
        if status_filter is not None and status_filter not in ("ONLINE", "OFFLINE"):
            return jsonify({"error": "'status' must be ONLINE or OFFLINE"}), 422
        summaries = [device_to_summary(d) for d in store.list_all()]
        if status_filter:
            summaries = [s for s in summaries if s["status"] == status_filter]
        return jsonify(summaries), 200

    @app.get("/devices/<device_id>")
    def get_device(device_id: str):
        device = store.get(device_id)
        if device is None:
            return jsonify({"error": f"device '{device_id}' not found"}), 404
        return jsonify(device_to_detail(device)), 200

    @app.get("/summary")
    def fleet_summary():
        devices = store.list_all()
        online = sum(1 for d in devices if d.computed_status() == "ONLINE")
        total = len(devices)
        return (
            jsonify({"total": total, "online": online, "offline": total - online}),
            200,
        )

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "time": utcnow().isoformat()}), 200

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
