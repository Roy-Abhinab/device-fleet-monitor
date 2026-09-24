"""Convenience entrypoint: `python run.py` starts the API on http://localhost:8000."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("fleet_monitor.main:app", host="0.0.0.0", port=8000, reload=False)
