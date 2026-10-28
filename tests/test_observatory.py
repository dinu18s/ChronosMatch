"""Comprehensive unit tests for Order-Book Event Observatory & Microstructure Liquidity Lab."""

import pytest
from fastapi.testclient import TestClient

from api.index import app
from chronosmatch.engine.observatory import (
    EventObservatoryEngine,
    run_deterministic_experiment,
    simulate_price_impact,
)
from chronosmatch.protocol.messages import CancelOrderMsg, NewOrderMsg
from chronosmatch.protocol.types import OrderType, Side


@pytest.fixture
def client():
    return TestClient(app)


# =====================================================================
# 1. EVENT OBSERVATORY ENGINE TESTS
# =====================================================================
def test_observatory_new_limit_order():
    """Verify limit order placement records NEW_LIMIT event with before/after state."""
    obs = EventObservatoryEngine("BTCUSDT")

    order = NewOrderMsg.create(
        order_id=101,
        client_id=1,
        symbol="BTCUSDT",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        price=60000.0,
        quantity=5,
    )
    events = obs.process_order_with_event(order)

    assert len(events) == 1
    ev = events[0]
    assert ev["event_type"] == "NEW_LIMIT"
    assert ev["side"] == "BUY"
    assert ev["price"] == 60000.0
    assert ev["quantity"] == 5
    assert ev["delta"]["liquidity_change"] == +5
    assert ev["delta"]["bid_levels_changed"] is True
    assert ev["bbo_after"]["best_bid"] == 60000.0
    assert ev["bbo_after"]["best_bid_qty"] == 5


def test_observatory_execution_and_partial_fill():
    """Verify resting limit followed by crossing order creates TRADE events."""
    obs = EventObservatoryEngine("BTCUSDT")

    # Resting ask: 10 units @ 60100.0
    ask_order = NewOrderMsg.create(
        order_id=201,
        client_id=2,
        symbol="BTCUSDT",
        side=Side.SELL,
        order_type=OrderType.LIMIT,
        price=60100.0,
        quantity=10,
    )
    obs.process_order_with_event(ask_order)

    # Aggressive crossing buy: 4 units @ 60100.0 (full fill of incoming buy order)
    buy_order = NewOrderMsg.create(
        order_id=202,
        client_id=1,
        symbol="BTCUSDT",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        price=60100.0,
        quantity=4,
    )
    events = obs.process_order_with_event(buy_order)

    assert len(events) == 1
    trade_ev = events[0]
    assert trade_ev["event_type"] == "TRADE_FULL"
    assert trade_ev["side"] == "BUY"
    assert trade_ev["price"] == 60100.0
    assert trade_ev["quantity"] == 4
    assert trade_ev["delta"]["liquidity_change"] == -4
    # Remaining resting ask should now be 6 units
    assert trade_ev["bbo_after"]["best_ask"] == 60100.0
    assert trade_ev["bbo_after"]["best_ask_qty"] == 6

    # Aggressive crossing buy that exceeds resting ask (partial match then rest)
    buy_order_2 = NewOrderMsg.create(
        order_id=203,
        client_id=1,
        symbol="BTCUSDT",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        price=60100.0,
        quantity=9,  # 6 match against ask, 3 rest as limit
    )
    events_2 = obs.process_order_with_event(buy_order_2)
    assert len(events_2) == 2
    assert events_2[0]["event_type"] == "TRADE_PARTIAL"
    assert events_2[0]["quantity"] == 6
    assert events_2[1]["event_type"] == "NEW_LIMIT"
    assert events_2[1]["quantity"] == 3


def test_observatory_cancel_order():
    """Verify order cancellation logs CANCEL event and updates depth."""
    obs = EventObservatoryEngine("BTCUSDT")

    order = NewOrderMsg.create(
        order_id=301,
        client_id=1,
        symbol="BTCUSDT",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        price=59900.0,
        quantity=8,
    )
    obs.process_order_with_event(order)
    assert obs.book.order_count == 1

    cancel_msg = CancelOrderMsg.create(
        order_id=301,
        client_id=1,
        symbol="BTCUSDT",
    )
    events = obs.process_cancel_with_event(cancel_msg)

    assert len(events) == 1
    c_ev = events[0]
    assert c_ev["event_type"] == "CANCEL"
    assert c_ev["order_id"] == 301
    assert c_ev["quantity"] == 8
    assert c_ev["delta"]["liquidity_change"] == -8
    assert c_ev["bbo_after"]["best_bid"] is None
    assert obs.book.order_count == 0


# =====================================================================
# 2. PRICE IMPACT LABORATORY TESTS
# =====================================================================
def test_price_impact_simulation_buy():
    """Verify price impact calculation walking up ask ladder."""
    depth_data = {
        "bids": [
            {"price": 100.0, "quantity": 10},
            {"price": 99.0, "quantity": 20},
        ],
        "asks": [
            {"price": 102.0, "quantity": 10},
            {"price": 103.0, "quantity": 15},
            {"price": 105.0, "quantity": 25},
        ],
    }

    # Small order: 5 units (fits completely in level 1 @ 102.0)
    small_res = simulate_price_impact(depth_data, side="BUY", quantity=5)
    assert small_res["filled_quantity"] == 5
    assert small_res["vwap"] == 102.0
    assert small_res["levels_consumed"] == 1
    assert small_res["remaining_liquidity"] == 45
    # Mid-price = (100 + 102) / 2 = 101.0
    # Slippage vs mid = (102 - 101) / 101 = ~0.99% = ~99 bps
    assert small_res["mid_price"] == 101.0
    assert small_res["slippage_bps"] > 0

    # Large order: 20 units (consumes 10 @ 102 and 10 @ 103)
    # Total cost = 10*102 + 10*103 = 1020 + 1030 = 2050 -> VWAP = 102.5
    large_res = simulate_price_impact(depth_data, side="BUY", quantity=20)
    assert large_res["filled_quantity"] == 20
    assert large_res["vwap"] == 102.5
    assert large_res["levels_consumed"] == 2
    assert large_res["remaining_liquidity"] == 30
    assert large_res["slippage_bps"] > small_res["slippage_bps"]
    assert len(large_res["ladder_fills"]) == 2


def test_price_impact_simulation_sell():
    """Verify price impact calculation walking down bid ladder."""
    depth_data = {
        "bids": [
            {"price": 200.0, "quantity": 5},
            {"price": 198.0, "quantity": 10},
            {"price": 195.0, "quantity": 20},
        ],
        "asks": [
            {"price": 202.0, "quantity": 10},
        ],
    }

    # Sell 10 units: 5 @ 200, 5 @ 198
    # Total proceeds = 5*200 + 5*198 = 1000 + 990 = 1990 -> VWAP = 199.0
    res = simulate_price_impact(depth_data, side="SELL", quantity=10)
    assert res["filled_quantity"] == 10
    assert res["vwap"] == 199.0
    assert res["levels_consumed"] == 2
    assert res["unfilled_quantity"] == 0


def test_price_impact_insufficient_liquidity():
    """Verify partial execution when requested quantity exceeds available book depth."""
    depth_data = {
        "bids": [{"price": 50.0, "quantity": 5}],
        "asks": [{"price": 52.0, "quantity": 10}],
    }

    res = simulate_price_impact(depth_data, side="BUY", quantity=25)
    assert res["requested_quantity"] == 25
    assert res["filled_quantity"] == 10
    assert res["unfilled_quantity"] == 15
    assert res["levels_consumed"] == 1
    assert res["remaining_liquidity"] == 0


# =====================================================================
# 3. DETERMINISTIC EXPERIMENT & RESEARCH REPORT TESTS
# =====================================================================
def test_deterministic_experiment_reproducibility():
    """Verify that running with identical seed yields bit-for-bit identical results."""
    res1 = run_deterministic_experiment(seed=777, symbol="BTCUSDT", num_events=50)
    res2 = run_deterministic_experiment(seed=777, symbol="BTCUSDT", num_events=50)

    assert res1["status"] == "success"
    assert res2["status"] == "success"

    # Event count must match
    assert len(res1["events"]) == len(res2["events"])

    # First and last events must match identically
    assert res1["events"][0]["event_type"] == res2["events"][0]["event_type"]
    assert res1["events"][0]["price"] == res2["events"][0]["price"]
    assert res1["events"][-1]["event_id"] == res2["events"][-1]["event_id"]

    # Research metrics must match
    rep1 = res1["research_report"]
    rep2 = res2["research_report"]
    assert rep1["total_orders_submitted"] == rep2["total_orders_submitted"]
    assert rep1["total_executed_quantity"] == rep2["total_executed_quantity"]
    assert rep1["total_cancelled_quantity"] == rep2["total_cancelled_quantity"]
    assert rep1["fill_rate_pct"] == rep2["fill_rate_pct"]
    assert rep1["spread_distribution"] == rep2["spread_distribution"]

    # Different seeds should produce distinct outcomes
    res_diff = run_deterministic_experiment(seed=999, symbol="BTCUSDT", num_events=50)
    assert res_diff["research_report"]["total_orders_submitted"] != rep1["total_orders_submitted"] or \
           res_diff["events"][-1]["price"] != res1["events"][-1]["price"]


def test_research_report_microstructure_metrics():
    """Verify research report contains all expected statistical and benchmark fields."""
    res = run_deterministic_experiment(seed=123, symbol="ETHUSDT", num_events=60)
    rep = res["research_report"]

    assert rep["seed"] == 123
    assert rep["instrument"] == "ETHUSDT"
    assert rep["total_events_processed"] > 0
    assert 0.0 <= rep["fill_rate_pct"] <= 100.0

    # Spread distribution
    assert "min_spread" in rep["spread_distribution"]
    assert "mean_spread" in rep["spread_distribution"]
    assert rep["spread_distribution"]["min_spread"] <= rep["spread_distribution"]["max_spread"]

    # Benchmark metrics
    bench = rep["measured_benchmark"]
    assert bench["throughput_events_per_sec"] > 0
    assert bench["mean_latency_microseconds"] > 0
    assert "High-resolution monotonic timer" in bench["benchmark_methodology"]


# =====================================================================
# 4. FASTAPI ENDPOINTS TESTS
# =====================================================================
def test_api_observatory_run_experiment(client):
    """Verify /api/observatory/run-experiment endpoint responds with complete payload."""
    payload = {
        "seed": 42,
        "symbol": "BTCUSDT",
        "num_events": 40,
        "arrival_rate": 1.0,
        "price_spread_pct": 0.05,
        "cancel_rate_pct": 15.0,
    }
    resp = client.post("/api/observatory/run-experiment", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "success"
    assert "events" in data
    assert "research_report" in data
    assert "timeline_series" in data
    assert "final_book" in data
    assert len(data["events"]) > 0


def test_api_observatory_price_impact(client):
    """Verify /api/observatory/price-impact endpoint responds correctly."""
    payload = {
        "depth_data": {
            "bids": [{"price": 100.0, "quantity": 10}],
            "asks": [{"price": 102.0, "quantity": 15}, {"price": 104.0, "quantity": 20}],
        },
        "side": "BUY",
        "quantity": 20,
    }
    resp = client.post("/api/observatory/price-impact", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["side"] == "BUY"
    assert data["requested_quantity"] == 20
    assert data["filled_quantity"] == 20
    assert data["vwap"] > 102.0
    assert data["levels_consumed"] == 2
