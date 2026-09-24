import os
import sys

# Make `import fleet_monitor` work without needing PYTHONPATH set manually,
# regardless of whether tests are launched with pytest or `python -m unittest`.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
