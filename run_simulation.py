"""Convenience entry point to run ChronosMatch market simulation."""

import sys
from pathlib import Path

# Add src to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from chronosmatch.simulation import main

if __name__ == "__main__":
    main()
