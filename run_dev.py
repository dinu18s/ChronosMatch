"""Cross-platform launcher for ChronosMatch dev and production servers."""

import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent


def find_python():
    """Locate the virtual environment Python interpreter if available."""
    if sys.platform == "win32":
        venv_py = ROOT_DIR / ".venv" / "Scripts" / "python.exe"
    else:
        venv_py = ROOT_DIR / ".venv" / "bin" / "python"

    if venv_py.exists():
        return str(venv_py)
    return sys.executable


def main():
    reload_flag = "--reload" if "--no-reload" not in sys.argv else ""
    port = "8000"
    for i, arg in enumerate(sys.argv):
        if arg == "--port" and i + 1 < len(sys.argv):
            port = sys.argv[i + 1]

    py_exe = find_python()
    cmd = [py_exe, "-m", "uvicorn", "api.index:app", "--host", "0.0.0.0", "--port", port]
    if reload_flag:
        cmd.append(reload_flag)

    print("=" * 65)
    print("  ChronosMatch: Zero-Copy HFT Engine Server")
    print(f"  Live at: http://localhost:{port}")
    print(f"  Docs at: http://localhost:{port}/docs")
    print("=" * 65)
    print(f"Executing: {' '.join(cmd)}\n")

    try:
        subprocess.run(cmd, cwd=str(ROOT_DIR))
    except KeyboardInterrupt:
        print("\nChronosMatch server stopped.")


if __name__ == "__main__":
    main()
