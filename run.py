"""Convenience entrypoint: `python run.py` starts the API on http://localhost:8000."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from fleet_monitor.main import app  # noqa: E402

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
