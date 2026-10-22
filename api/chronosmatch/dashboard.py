"""Trading Terminal Dashboard HTML loader for ChronosMatch."""

from pathlib import Path


def get_dashboard_html() -> str:
    """Load latest modern trading terminal HTML from root or fallback to embedded template."""
    candidates = [
        Path(__file__).resolve().parent.parent.parent.parent / "index.html",
        Path(__file__).resolve().parent.parent.parent / "index.html",
        Path("index.html"),
    ]
    for c in candidates:
        if c.exists():
            try:
                return c.read_text(encoding="utf-8")
            except Exception:
                pass
    return "<html><body><h1>ChronosMatch Dashboard</h1></body></html>"
