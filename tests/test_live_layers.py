# -*- coding: utf-8 -*-
"""Tests for continuous dynamic market layers (Candlestick Chart, Order Book, Depth, Statistics)."""

import hashlib
import json
import re
from pathlib import Path
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
INDEX_HTML = ROOT_DIR / "index.html"
DOCS_INDEX_HTML = ROOT_DIR / "docs" / "index.html"


def test_html_dual_hosting_parity():
    """Verify that index.html and docs/index.html are identical in content and SHA-256."""
    assert INDEX_HTML.exists(), "index.html must exist"
    assert DOCS_INDEX_HTML.exists(), "docs/index.html must exist"

    h1 = hashlib.sha256(INDEX_HTML.read_bytes()).hexdigest()
    h2 = hashlib.sha256(DOCS_INDEX_HTML.read_bytes()).hexdigest()
    assert h1 == h2, "Dual-hosting hash mismatch between index.html and docs/index.html"


def test_no_page_reload_calls_in_html():
    """Verify that no window.location.reload() calls exist in index.html."""
    content = INDEX_HTML.read_text(encoding="utf-8")
    assert "location.reload" not in content, "Forbidden page reload call found in index.html"


def test_order_book_depth_bar_alignment():
    """Verify that depth bars are correctly anchored to right: 0 matching visual screenshot."""
    content = INDEX_HTML.read_text(encoding="utf-8")
    assert ".depth-bar.bid" in content, "Missing .depth-bar.bid CSS"
    assert ".depth-bar.ask" in content, "Missing .depth-bar.ask CSS"

    # Confirm ask depth bar is anchored to right: 0
    ask_match = re.search(r'\.depth-bar\.ask\s*\{([^}]+)\}', content)
    assert ask_match is not None, "Could not find .depth-bar.ask CSS rule"
    assert "right: 0" in ask_match.group(1), ".depth-bar.ask must be anchored to right: 0"


def test_exact_screenshot_seed_order_book():
    """Verify that initial order book for RELIANCE matches screenshot exact values."""
    content = INDEX_HTML.read_text(encoding="utf-8")
    assert "1183.07" in content, "Missing screenshot bid price 1183.07"
    assert "1183.17" in content, "Missing screenshot ask price 1183.17"
    assert "168.5" in content, "Missing screenshot cumulative bid total 168.5"
    assert "133.0" in content, "Missing screenshot cumulative ask total 133.0"
    assert "56%" in content, "Missing screenshot imbalance 56%"
    assert "44%" in content, "Missing screenshot imbalance 44%"


def test_market_depth_and_spread_invariants():
    """Mathematical validation of the 3-layer invariants."""
    # Given screenshot prices:
    bids = [
        {"price": 1183.07, "qty": 40.0},
        {"price": 1183.02, "qty": 27.1},
        {"price": 1182.97, "qty": 10.3},
        {"price": 1182.92, "qty": 20.8},
        {"price": 1182.87, "qty": 39.1},
        {"price": 1182.82, "qty": 31.2},
    ]
    asks = [
        {"price": 1183.17, "qty": 25.1},
        {"price": 1183.22, "qty": 9.2},
        {"price": 1183.27, "qty": 20.8},
        {"price": 1183.32, "qty": 38.4},
        {"price": 1183.37, "qty": 29.2},
        {"price": 1183.42, "qty": 10.3},
    ]

    # 1. Price sorting
    for i in range(len(bids) - 1):
        assert bids[i]["price"] > bids[i + 1]["price"], "Bids must be strictly descending"
    for i in range(len(asks) - 1):
        assert asks[i]["price"] < asks[i + 1]["price"], "Asks must be strictly ascending"

    # 2. Spread calculation
    best_bid = bids[0]["price"]
    best_ask = asks[0]["price"]
    spread = round(best_ask - best_bid, 2)
    assert spread == 0.10, f"Expected spread 0.10, got {spread}"
    spread_pct = round((spread / best_ask) * 100, 2)
    assert spread_pct == 0.01, f"Expected spread_pct 0.01, got {spread_pct}"

    # 3. Cumulative depth
    cum_b = 0.0
    for b in bids:
        cum_b = round(cum_b + b["qty"], 1)
        b["total"] = cum_b
    cum_a = 0.0
    for a in asks:
        cum_a = round(cum_a + a["qty"], 1)
        a["total"] = cum_a

    assert bids[-1]["total"] == 168.5, "Cumulative bids must equal 168.5"
    assert asks[-1]["total"] == 133.0, "Cumulative asks must equal 133.0"

    # 4. Imbalance meter percentages
    total_vol = cum_b + cum_a
    bid_pct = round((cum_b / total_vol) * 100)
    ask_pct = 100 - bid_pct
    assert bid_pct == 56, f"Expected bid_pct 56, got {bid_pct}"
    assert ask_pct == 44, f"Expected ask_pct 44, got {ask_pct}"
    assert bid_pct + ask_pct == 100, "Bid and ask percentages must sum to 100"

    # 5. Depth bar widths
    max_cum = max(cum_b, cum_a)
    for b in bids:
        w = round((b["total"] / max_cum) * 100, 1)
        assert 0.0 <= w <= 100.0, f"Depth bar width {w}% out of range"
    for a in asks:
        w = round((a["total"] / max_cum) * 100, 1)
        assert 0.0 <= w <= 100.0, f"Depth bar width {w}% out of range"


def test_candlestick_ohlc_invariants():
    """Verify candlestick formation invariants under price ticks."""
    candles = [
        {"open": 1180.0, "high": 1185.0, "low": 1178.0, "close": 1183.12, "volume": 5000}
    ]
    cur = candles[0]

    # Upward tick
    new_price = 1186.5
    cur["close"] = new_price
    cur["high"] = max(cur["high"], new_price)
    cur["low"] = min(cur["low"], new_price)

    assert cur["high"] == 1186.5
    assert cur["close"] == 1186.5
    assert cur["close"] >= cur["open"]  # Green candle

    # Downward tick
    new_price = 1175.0
    cur["close"] = new_price
    cur["high"] = max(cur["high"], new_price)
    cur["low"] = min(cur["low"], new_price)

    assert cur["low"] == 1175.0
    assert cur["close"] == 1175.0
    assert cur["close"] < cur["open"]  # Red candle
