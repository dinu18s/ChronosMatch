"""Convenience entry point to run pytest test suite across environments."""

import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
VENV_PYTEST = ROOT_DIR / ".venv" / ("Scripts" if sys.platform == "win32" else "bin") / "pytest"

def main():
    if VENV_PYTEST.exists():
        cmd = [str(VENV_PYTEST), "-ra", "-v"]
    else:
        # Fall back to uv run pytest or python -m pytest
        cmd = ["uv", "run", "pytest", "-ra", "-v"]

    print(f"Executing: {' '.join(cmd)}\n")
    res = subprocess.run(cmd, cwd=str(ROOT_DIR))
    sys.exit(res.returncode)

if __name__ == "__main__":
    main()
