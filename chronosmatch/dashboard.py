"""High-Frequency Trading Terminal Dashboard HTML generator for ChronosMatch."""

from pathlib import Path

_INDEX_HTML_PATH = Path(__file__).resolve().parent.parent / "index.html"


def get_dashboard_html() -> str:
    """Return the frontend dashboard HTML, synchronized with index.html."""
    if _INDEX_HTML_PATH.exists():
        return _INDEX_HTML_PATH.read_text(encoding="utf-8")
    return "<html><body><h1>ChronosMatch Dashboard</h1></body></html>"
