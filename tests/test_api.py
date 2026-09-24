"""Automated tests for the Fleet Monitor API.

Runnable with either:
    python -m unittest discover -s tests
    pytest
No third-party test framework is required (uses stdlib unittest), though
pytest will happily discover and run these same tests too.
"""

import os
import sys
import threading
import unittest
from datetime import timedelta

# Make `import fleet_monitor` work regardless of how the tests are launched.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fleet_monitor.main import app  # noqa: E402
from fleet_monitor.store import store, utcnow  # noqa: E402


class FleetMonitorTestCase(unittest.TestCase):
    def setUp(self):
        store.clear()
        self.client = app.test_client()

    def register(self, device_id="device-01", name="Lab Device 01"):
        return self.client.post("/devices", json={"id": device_id, "name": name})

    def heartbeat(self, device_id="device-01", **extra):
        payload = {"timestamp": utcnow().isoformat(), "status": "OK"}
        payload.update(extra)
        return self.client.post(f"/devices/{device_id}/heartbeat", json=payload)

    # ---- Registration -----------------------------------------------

    def test_register_device_succeeds_and_starts_offline(self):
        resp = self.register()
        self.assertEqual(resp.status_code, 201)
        body = resp.get_json()
        self.assertEqual(body["id"], "device-01")
        self.assertEqual(body["name"], "Lab Device 01")
        # No heartbeat has been sent yet, so a brand-new device is OFFLINE.
        self.assertEqual(body["status"], "OFFLINE")
        self.assertIsNone(body["last_heartbeat"])

    def test_register_duplicate_id_returns_409(self):
        self.register()
        resp = self.register()
        self.assertEqual(resp.status_code, 409)

    def test_register_missing_name_returns_422(self):
        resp = self.client.post("/devices", json={"id": "device-02"})
        self.assertEqual(resp.status_code, 422)

    def test_register_empty_id_returns_422(self):
        resp = self.client.post("/devices", json={"id": "  ", "name": "X"})
        self.assertEqual(resp.status_code, 422)

    def test_register_non_json_body_returns_422(self):
        resp = self.client.post(
            "/devices", data="not json", content_type="text/plain"
        )
        self.assertEqual(resp.status_code, 422)

    # ---- Heartbeats ----------------------------------------------------

    def test_heartbeat_marks_device_online(self):
        self.register()
        resp = self.heartbeat()
        self.assertEqual(resp.status_code, 200)
        body = resp.get_json()
        self.assertEqual(body["status"], "ONLINE")
        self.assertEqual(body["reported_status"], "OK")
        self.assertIsNotNone(body["last_heartbeat"])

    def test_heartbeat_for_unknown_device_returns_404(self):
        resp = self.heartbeat(device_id="does-not-exist")
        self.assertEqual(resp.status_code, 404)

    def test_heartbeat_stores_optional_metrics(self):
        self.register()
        self.heartbeat(cpu_usage=42, signal_strength=-71)
        resp = self.client.get("/devices/device-01")
        metrics = resp.get_json()["metrics"]
        self.assertEqual(metrics["cpu_usage"], 42)
        self.assertEqual(metrics["signal_strength"], -71)

    def test_heartbeat_without_timestamp_defaults_to_now(self):
        self.register()
        resp = self.client.post(
            "/devices/device-01/heartbeat", json={"status": "OK"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["status"], "ONLINE")

    def test_heartbeat_rejects_non_numeric_metric(self):
        self.register()
        resp = self.client.post(
            "/devices/device-01/heartbeat",
            json={"timestamp": utcnow().isoformat(), "cpu_usage": "high"},
        )
        self.assertEqual(resp.status_code, 422)

    # ---- Listing / details ----------------------------------------------

    def test_list_devices_returns_everything_registered(self):
        self.register("device-01", "A")
        self.register("device-02", "B")
        resp = self.client.get("/devices")
        ids = {d["id"] for d in resp.get_json()}
        self.assertEqual(ids, {"device-01", "device-02"})

    def test_get_unknown_device_returns_404(self):
        resp = self.client.get("/devices/missing")
        self.assertEqual(resp.status_code, 404)

    def test_filter_devices_by_status(self):
        self.register("device-01", "A")
        self.register("device-02", "B")
        self.heartbeat("device-01")
        resp = self.client.get("/devices?status=ONLINE")
        ids = {d["id"] for d in resp.get_json()}
        self.assertEqual(ids, {"device-01"})

    # ---- Summary ---------------------------------------------------------

    def test_summary_counts_online_and_offline(self):
        self.register("device-01", "A")
        self.register("device-02", "B")
        self.heartbeat("device-01")
        resp = self.client.get("/summary")
        body = resp.get_json()
        self.assertEqual(body, {"total": 2, "online": 1, "offline": 1})

    # ---- The 30-second ONLINE/OFFLINE rule ---------------------------

    def test_device_goes_offline_after_30_second_timeout(self):
        self.register()
        self.heartbeat()
        # Simulate time passing by moving the stored heartbeat into the past,
        # rather than sleeping the test for 30+ real seconds.
        device = store.get("device-01")
        device.last_heartbeat = utcnow() - timedelta(seconds=31)

        resp = self.client.get("/devices/device-01")
        self.assertEqual(resp.get_json()["status"], "OFFLINE")

    def test_device_stays_online_within_30_second_window(self):
        self.register()
        self.heartbeat()
        device = store.get("device-01")
        device.last_heartbeat = utcnow() - timedelta(seconds=29)

        resp = self.client.get("/devices/device-01")
        self.assertEqual(resp.get_json()["status"], "ONLINE")

    def test_device_with_no_heartbeat_is_offline(self):
        self.register()
        resp = self.client.get("/devices/device-01")
        self.assertEqual(resp.get_json()["status"], "OFFLINE")

    # ---- Concurrency -----------------------------------------------------

    def test_concurrent_heartbeats_do_not_crash_or_corrupt_state(self):
        self.register()

        errors = []

        def send_many():
            for _ in range(30):
                try:
                    resp = self.heartbeat()
                    if resp.status_code != 200:
                        errors.append(resp.status_code)
                except Exception as exc:  # pragma: no cover - failure path
                    errors.append(str(exc))

        threads = [threading.Thread(target=send_many) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        resp = self.client.get("/devices/device-01")
        self.assertEqual(resp.get_json()["status"], "ONLINE")


if __name__ == "__main__":
    unittest.main()
