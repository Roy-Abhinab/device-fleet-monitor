#!/usr/bin/env python3
"""Simulates a fleet of devices sending heartbeats to the Fleet Monitor API.

Usage:
    python simulator/simulate.py --url http://localhost:8000 --count 5 --interval 5

While running:
  - type a device id (e.g. "device-03") and press Enter to stop that
    device's heartbeats. It should show as OFFLINE via the API ~30s later.
  - type "list" to see which simulated devices are running/stopped.
  - type "quit" (or press Ctrl-C) to stop everything and exit.
"""

from __future__ import annotations

import argparse
import random
import threading
from datetime import datetime, timezone

import requests


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SimulatedDevice:
    def __init__(self, device_id: str, name: str, base_url: str, interval: float):
        self.device_id = device_id
        self.name = name
        self.base_url = base_url
        self.interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def register(self) -> None:
        resp = requests.post(
            f"{self.base_url}/devices",
            json={"id": self.device_id, "name": self.name},
            timeout=5,
        )
        # 409 just means a previous run already registered this device --
        # that's fine, we can still send it heartbeats.
        if resp.status_code not in (201, 409):
            resp.raise_for_status()

    def start(self) -> None:
        self.register()
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def is_stopped(self) -> bool:
        return self._stop.is_set()

    def _run(self) -> None:
        while not self._stop.is_set():
            payload = {
                "timestamp": utcnow_iso(),
                "status": "OK",
                "cpu_usage": round(random.uniform(5, 95), 1),
                "signal_strength": round(random.uniform(-90, -40), 1),
            }
            try:
                requests.post(
                    f"{self.base_url}/devices/{self.device_id}/heartbeat",
                    json=payload,
                    timeout=5,
                )
                print(f"[{self.device_id}] heartbeat sent")
            except requests.RequestException as exc:
                print(f"[{self.device_id}] heartbeat failed: {exc}")
            # wait() returns early if stop() is called, so shutdown is snappy
            self._stop.wait(self.interval)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--count", type=int, default=5, help="number of devices")
    parser.add_argument(
        "--interval", type=float, default=5.0, help="seconds between heartbeats"
    )
    args = parser.parse_args()

    devices = {}
    for i in range(1, args.count + 1):
        device_id = f"device-{i:02d}"
        device = SimulatedDevice(
            device_id, f"Simulated Device {i:02d}", args.url, args.interval
        )
        devices[device_id] = device
        device.start()

    print(f"Started {len(devices)} simulated devices against {args.url}")
    print("Commands: <device-id> to stop it, 'list' to see status, 'quit' to exit\n")

    try:
        while True:
            command = input("> ").strip()
            if not command:
                continue
            if command == "quit":
                break
            if command == "list":
                for device_id, device in devices.items():
                    state = "stopped" if device.is_stopped() else "running"
                    print(f"  {device_id}: {state}")
                continue
            if command in devices:
                devices[command].stop()
                print(f"Stopped {command}; it should go OFFLINE in ~30s")
            else:
                print(f"Unknown device id: {command!r} (try 'list')")
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        for device in devices.values():
            device.stop()
        print("Simulator exiting.")


if __name__ == "__main__":
    main()
