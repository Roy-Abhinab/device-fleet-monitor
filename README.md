# Mini Device Fleet Monitor

A small HTTP service that tracks heartbeats from a fleet of devices and
reports each device's ONLINE/OFFLINE status, plus a fleet-wide summary.
Built for the Round 2 campus hiring exercise.

## What it does

- Devices register themselves once (`POST /devices`).
- Each device periodically sends a heartbeat (`POST /devices/{id}/heartbeat`)
  with a timestamp and optional status/metrics.
- An operator can list the fleet (`GET /devices`), inspect one device
  (`GET /devices/{id}`), or get aggregate counts (`GET /summary`).
- A device is **ONLINE** if its last heartbeat was within the last **30
  seconds**, and **OFFLINE** otherwise. This is computed on every read, not
  stored, so it's always correct and there's no background job to keep in
  sync.
- A `simulator/` script drives 5+ fake devices against the API so you can
  watch this behavior happen live.

## Design / architecture

```
device-fleet-monitor/
├── run.py                       # `python run.py` starts the API on :8000
├── src/fleet_monitor/
│   ├── store.py                 # Device dataclass + thread-safe in-memory store
│   ├── models.py                # Request validation & response serialization (no 3rd-party validator)
│   └── main.py                  # Flask app: routes, error handling, logging
├── tests/test_api.py            # unittest suite (also pytest-discoverable)
└── simulator/simulate.py        # multi-device heartbeat simulator
```

**Stack:** Flask + the Python standard library. No database, no ORM, no
request-validation library (e.g. pydantic) — validation is a few explicit
`if` checks in `models.py`. For a 3-hour exercise with a handful of
endpoints, this keeps the dependency footprint tiny (`Flask` + `requests`
for the simulator) and the whole request/response path easy to read in one
sitting.

**State:** a single `DeviceStore` holds devices in a plain `dict`, guarded
by one `threading.Lock`. All reads and writes go through the store, so
there's one place that owns concurrency correctness (see
`test_concurrent_heartbeats_do_not_crash_or_corrupt_state` in the test
suite). Status is derived, not stored: `Device.computed_status()` compares
`last_heartbeat` against "now" at request time using the 30-second rule.

**Why Flask over something async (FastAPI/etc.):** for this project's
scope — a handful of simple, low-concurrency JSON endpoints — a
synchronous framework is simpler to reason about and test, and needs no
extra ASGI server. See "What I'd improve" below for how this would change
at real scale.

## Prerequisites

- Python 3.9+
- `pip`

## Build (install dependencies)

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

(Only `Flask` and `requests` are actually required to run the app and
simulator; `pytest` in `requirements.txt` is optional — the tests also run
with the standard library's `unittest`, see below.)

## Run the application

```bash
python run.py
```

This starts the API at `http://localhost:8000`. Confirm it's up:

```bash
curl http://localhost:8000/health
```

## Run the simulator

In a second terminal, with the API already running:

```bash
python simulator/simulate.py --url http://localhost:8000 --count 5 --interval 5
```

This registers 5 devices (`device-01` … `device-05`) and sends a heartbeat
from each every 5 seconds. While it's running:

- Type a device id (e.g. `device-03`) + Enter to stop that device's
  heartbeats. Check `GET /devices/device-03` ~30s later and it will show
  `"status": "OFFLINE"`.
- Type `list` to see which simulated devices are currently running/stopped.
- Type `quit` (or Ctrl-C) to stop everything.

Flags: `--url` (API base URL), `--count` (number of devices), `--interval`
(seconds between heartbeats).

## Run the tests

Either works, no third-party test runner required:

```bash
python -m unittest discover -s tests -v
```

```bash
pytest tests/ -v          # if you installed the optional pytest dependency
```

18 tests cover: registration (success, duplicate-id conflict, validation
errors), heartbeat handling (success, unknown device, optional metrics,
missing timestamp, invalid metric type), listing and filtering, the
`/summary` counts, the 30-second ONLINE/OFFLINE rule (both sides of the
boundary, and a device that's never sent a heartbeat), and a concurrency
test that fires heartbeats from 5 threads at once.

## Example API requests

```bash
# Register a device
curl -X POST http://localhost:8000/devices \
  -H "Content-Type: application/json" \
  -d '{"id": "device-01", "name": "Lab Device 01"}'

# Send a heartbeat
curl -X POST http://localhost:8000/devices/device-01/heartbeat \
  -H "Content-Type: application/json" \
  -d '{"timestamp": "2026-09-24T10:30:00Z", "status": "OK", "cpu_usage": 42, "signal_strength": -71}'

# List devices (optionally filter: ?status=ONLINE or ?status=OFFLINE)
curl http://localhost:8000/devices

# Get one device
curl http://localhost:8000/devices/device-01

# Fleet summary
curl http://localhost:8000/summary
```

## Assumptions

- A device must be registered before it can send a heartbeat (an unknown
  device's heartbeat returns `404`, matching the spec's registration
  requirement).
- `id` must be unique; registering an existing id returns `409 Conflict`
  rather than silently overwriting it.
- If a heartbeat omits `timestamp`, the server's current time is used
  instead of rejecting the request, since the spec marks extra fields
  optional and a device is more likely to have a clock skew issue than to
  intentionally omit a timestamp.
- `cpu_usage` and `signal_strength` are stored as opaque numeric metrics
  (last value wins) and aren't validated against a "sensible" range, since
  the spec doesn't define one.
- The 30-second ONLINE window is a fixed constant
  (`store.ONLINE_THRESHOLD_SECONDS`), not configurable via the API, since
  the spec states it as a fixed rule.

## Known limitations

- **In-memory only**: all state is lost on restart. Fine for a 3-hour
  exercise and for the simulator's purposes; not suitable for production.
- **Single process**: the `threading.Lock` guarantees correctness within
  one process, but running multiple instances behind a load balancer would
  each have their own, inconsistent view of the fleet.
- **No auth**: any caller can register devices or post heartbeats for any
  device id. There's no way to prove a heartbeat actually came from the
  device it claims to be.
- **No pagination**: `GET /devices` returns the entire fleet in one
  response, which wouldn't scale to a very large fleet.
- **Minimal input limits**: there's no cap on metric value ranges, string
  lengths, or request body size beyond Flask's defaults.

## What I'd improve with one more day

- Swap the in-memory store for a real backend (Redis would be a natural
  fit for heartbeat/TTL-style data; Postgres if device metadata needs to
  be queryable/relational) so state survives restarts and multiple API
  instances can share one view of the fleet.
- Add authentication for heartbeats (e.g. an API key or token issued at
  registration) so devices can't spoof each other's heartbeats.
- Add pagination and sorting to `GET /devices` for large fleets.
- Add structured (JSON) logging and a few basic metrics (heartbeat rate,
  request latency) suitable for scraping by a monitoring system.
- Containerize with Docker and add a small `docker-compose.yml` that
  starts the API and the simulator together for a one-command demo.
- Push status computation into a lightweight background sweep (or a
  pub/sub notification) so an operator UI could get push updates instead
  of polling `GET /devices`.

## AI Usage

I used Claude while building this project. Specifically:

- Scaffolded the overall project structure (store/models/routes split,
  test layout, simulator) and generated the first draft of each file.
- Used it to write the bulk of the `unittest` test suite, including the
  approach for testing the 30-second timeout without a real 30-second
  sleep (moving a device's stored `last_heartbeat` into the past instead).
- One thing I changed from the first draft: the initial implementation
  used FastAPI + pydantic. I switched it to Flask + a small hand-rolled
  validation module in `models.py`, since that's the stack I could
  actually run and verify in my environment, and it also keeps the
  project's dependencies to just Flask and requests.
- Before submitting, I personally ran the full test suite
  (`python -m unittest discover -s tests -v`, 18/18 passing) and ran the
  simulator end-to-end against a live server for 35+ seconds to watch a
  stopped device actually flip to `OFFLINE` after the timeout, rather than
  just trusting that the code should work.

**Note for whoever is filling in their own copy of this section:** replace
the bullet points above with what you *personally* did — which parts you
wrote yourself vs. generated, what you changed or rejected, and what you
verified by actually running it before submitting. That's the point of
this section per the assignment.
