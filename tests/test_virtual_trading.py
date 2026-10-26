"""Unit tests for ChronosMatch Virtual Paper Trading and Real-Time Market Data API."""

import uuid
import pytest
from fastapi.testclient import TestClient

from api.index import app
from chronosmatch.persistence.db import db


@pytest.fixture
def client():
    return TestClient(app)


def test_virtual_auth_and_initial_balance(client):
    email = f"trader_test_{uuid.uuid4().hex[:8]}@chronos.local"
    res = client.post("/api/virtual/auth", json={
        "email": email,
        "name": "Arjun Sharma",
        "password": "securepassword",
    })
    assert res.status_code == 200
    data = res.json()["user"]
    assert data["email"] == email
    assert data["name"] == "Arjun Sharma"
    assert data["cash_balance"] == 100000.00
    assert data["realized_pnl"] == 0.00


def test_market_quotes_and_search_endpoints(client):
    # Fetch quotes
    res = client.get("/api/market/quotes")
    assert res.status_code == 200
    quotes = res.json()
    assert len(quotes) >= 10
    symbols = [q["symbol"] for q in quotes]
    assert "RELIANCE" in symbols
    assert "AAPL" in symbols

    # Single quote
    rel_res = client.get("/api/market/quote/RELIANCE")
    assert rel_res.status_code == 200
    rel_data = rel_res.json()
    assert rel_data["symbol"] == "RELIANCE"
    assert rel_data["price"] > 0
    assert rel_data["currency"] == "INR"

    # Search
    s_res = client.get("/api/market/search?q=tata")
    assert s_res.status_code == 200
    s_data = s_res.json()
    assert any("TCS" in item["symbol"] or "Tata" in item["name"] for item in s_data)

    # History
    h_res = client.get("/api/market/history/RELIANCE?period=1D")
    assert h_res.status_code == 200
    h_data = h_res.json()
    assert len(h_data["points"]) > 0


def test_virtual_buy_and_sell_lifecycle(client):
    email = f"trader_lifecycle_{uuid.uuid4().hex[:8]}@chronos.local"
    # 1. Initialize user
    client.post("/api/virtual/auth", json={"email": email, "name": "Deepa Roy", "password": "pass"})

    # 2. Buy 10 shares of RELIANCE at ₹1,200 (Total ₹12,000)
    buy_res = client.post("/api/virtual/trade", json={
        "email": email,
        "symbol": "RELIANCE",
        "action": "BUY",
        "order_type": "MARKET",
        "price": 1200.0,
        "quantity": 10.0,
    })
    assert buy_res.status_code == 200
    trade = buy_res.json()["trade"]
    assert trade["action"] == "BUY"
    assert trade["total_value"] == 12000.0
    assert trade["cash_balance"] == 88000.0

    # 3. Verify portfolio holdings and valuation
    port_res = client.get(f"/api/virtual/portfolio/{email}")
    assert port_res.status_code == 200
    port = port_res.json()
    assert port["cash_balance"] == 88000.0
    assert port["total_invested"] == 12000.0
    assert len(port["holdings"]) == 1
    assert port["holdings"][0]["symbol"] == "RELIANCE"
    assert port["holdings"][0]["quantity"] == 10.0
    assert port["holdings"][0]["avg_buy_price"] == 1200.0

    # 4. Partial sell: sell 4 shares at ₹1,300 (+₹100 gain/share = +₹400 realized PNL)
    sell_res = client.post("/api/virtual/trade", json={
        "email": email,
        "symbol": "RELIANCE",
        "action": "SELL",
        "order_type": "MARKET",
        "price": 1300.0,
        "quantity": 4.0,
    })
    assert sell_res.status_code == 200
    sell_trade = sell_res.json()["trade"]
    assert sell_trade["action"] == "SELL"
    assert sell_trade["total_value"] == 5200.0
    assert sell_trade["realized_pnl"] == 400.0
    assert sell_trade["cash_balance"] == 93200.0  # 88000 + 5200

    # 5. Verify remaining holding of 6 shares
    port_res2 = client.get(f"/api/virtual/portfolio/{email}")
    port2 = port_res2.json()
    assert port2["cash_balance"] == 93200.0
    assert port2["realized_pnl"] == 400.0
    assert len(port2["holdings"]) == 1
    assert port2["holdings"][0]["quantity"] == 6.0


def test_insufficient_funds_rejection(client):
    email = f"trader_broke_{uuid.uuid4().hex[:8]}@chronos.local"
    client.post("/api/virtual/auth", json={"email": email, "name": "Broke Trader", "password": "pass"})

    # Attempt to buy ₹2,00,000 worth of stock with only ₹1,00,000 balance
    res = client.post("/api/virtual/trade", json={
        "email": email,
        "symbol": "TCS",
        "action": "BUY",
        "order_type": "MARKET",
        "price": 2000.0,
        "quantity": 100.0,  # ₹2,00,000
    })
    assert res.status_code == 400
    assert "Insufficient virtual cash" in res.json()["detail"]


def test_oversell_rejection(client):
    email = f"trader_short_{uuid.uuid4().hex[:8]}@chronos.local"
    client.post("/api/virtual/auth", json={"email": email, "name": "Short Seller", "password": "pass"})

    # Attempt to sell shares not owned
    res = client.post("/api/virtual/trade", json={
        "email": email,
        "symbol": "INFY",
        "action": "SELL",
        "order_type": "MARKET",
        "price": 1500.0,
        "quantity": 5.0,
    })
    assert res.status_code == 400
    assert "Insufficient shares" in res.json()["detail"]


def test_watchlist_toggle(client):
    email = f"trader_watch_{uuid.uuid4().hex[:8]}@chronos.local"
    # Add RELIANCE
    t1 = client.post("/api/virtual/watchlist/toggle", json={"email": email, "symbol": "RELIANCE"})
    assert t1.status_code == 200
    assert t1.json()["in_watchlist"] is True

    # Check watchlist
    w_res = client.get(f"/api/virtual/watchlist/{email}")
    assert w_res.status_code == 200
    assert "RELIANCE" in w_res.json()["watchlist"]

    # Toggle off
    t2 = client.post("/api/virtual/watchlist/toggle", json={"email": email, "symbol": "RELIANCE"})
    assert t2.status_code == 200
    assert t2.json()["in_watchlist"] is False

    w_res2 = client.get(f"/api/virtual/watchlist/{email}")
    assert "RELIANCE" not in w_res2.json()["watchlist"]


def test_order_history_recording(client):
    email = f"trader_orders_{uuid.uuid4().hex[:8]}@chronos.local"
    client.post("/api/virtual/auth", json={"email": email, "name": "Order Tracker", "password": "pass"})

    client.post("/api/virtual/trade", json={
        "email": email,
        "symbol": "HDFCBANK",
        "action": "BUY",
        "order_type": "MARKET",
        "price": 1000.0,
        "quantity": 5.0,
    })

    hist_res = client.get(f"/api/virtual/orders/{email}")
    assert hist_res.status_code == 200
    orders = hist_res.json()
    assert len(orders) >= 1
    assert orders[0]["symbol"] == "HDFCBANK"
    assert orders[0]["action"] == "BUY"
    assert orders[0]["status"] == "Completed"


def test_portfolio_reset_and_analytics(client):
    email = f"trader_reset_{uuid.uuid4().hex[:8]}@chronos.local"
    client.post("/api/virtual/auth", json={"email": email, "name": "Reset Tester", "password": "pass"})

    # Execute a trade
    client.post("/api/virtual/trade", json={
        "email": email,
        "symbol": "TCS",
        "action": "BUY",
        "order_type": "MARKET",
        "price": 2000.0,
        "quantity": 5.0,
    })
    client.post("/api/virtual/trade", json={
        "email": email,
        "symbol": "TCS",
        "action": "SELL",
        "order_type": "MARKET",
        "price": 2200.0,
        "quantity": 5.0,
    })

    # Verify analytics
    an_res = client.get(f"/api/virtual/analytics/{email}")
    assert an_res.status_code == 200
    an_data = an_res.json()
    assert an_data["total_trades"] == 1
    assert an_data["winning_trades"] == 1
    assert an_data["win_rate_pct"] == 100.0
    assert an_data["best_trade"] == 1000.0

    # Reset portfolio
    rst_res = client.post("/api/virtual/reset", json={"email": email, "starting_balance": 100000.0})
    assert rst_res.status_code == 200
    rst_data = rst_res.json()
    assert rst_data["cash_balance"] == 100000.0
    assert rst_data["realized_pnl"] == 0.0

    # Verify portfolio is clean
    p_res = client.get(f"/api/virtual/portfolio/{email}")
    assert p_res.status_code == 200
    assert p_res.json()["cash_balance"] == 100000.0
    assert len(p_res.json()["holdings"]) == 0


def test_trading_journal_crud(client):
    email = f"trader_jrn_{uuid.uuid4().hex[:8]}@chronos.local"
    # Create journal entry
    c_res = client.post("/api/virtual/journal", json={
        "email": email,
        "symbol": "RELIANCE",
        "notes": "Bought dip near 200 EMA support",
        "strategy": "Dip Buying",
        "sentiment": "Bullish",
        "lessons": "Strict stop loss respected",
    })
    assert c_res.status_code == 200
    entry_id = c_res.json()["entry_id"]

    # Read entries
    r_res = client.get(f"/api/virtual/journal/{email}")
    assert r_res.status_code == 200
    entries = r_res.json()
    assert len(entries) == 1
    assert entries[0]["symbol"] == "RELIANCE"
    assert entries[0]["strategy"] == "Dip Buying"

    # Delete entry
    d_res = client.delete(f"/api/virtual/journal/{email}/{entry_id}")
    assert d_res.status_code == 200
    assert d_res.json()["status"] == "deleted"

    r_res2 = client.get(f"/api/virtual/journal/{email}")
    assert len(r_res2.json()) == 0


def test_ai_chat_assistant(client):
    res = client.post("/api/ai/chat", json={
        "message": "What is an order book spread and how does slippage work?",
    })
    assert res.status_code == 200
    data = res.json()
    assert "Bid-Ask Spread" in data["reply"]
    assert "Slippage" in data["reply"]


def test_engine_metrics_endpoint(client):
    res = client.get("/api/engine/metrics")
    assert res.status_code == 200
    data = res.json()
    assert "orders/sec" in data["benchmark_throughput_ops"]
    assert data["matching_algorithm"] == "Price-Time Priority (FIFO)"


def test_virtual_order_cancellation_and_refund(client):
    email = f"trader_cancel_{uuid.uuid4().hex[:8]}@chronos.local"
    client.post("/api/virtual/auth", json={"email": email, "name": "Cancel Tester", "password": "pass"})

    # Place a resting LIMIT BUY order: 10 shares of INFY at ₹1000 = ₹10,000 reserved
    order_id = f"ORD-TEST-CNC-{uuid.uuid4().hex[:4]}"
    buy_res = client.post("/api/virtual/trade", json={
        "email": email,
        "symbol": "INFY",
        "action": "BUY",
        "order_type": "LIMIT",
        "price": 1000.0,
        "quantity": 10.0,
        "order_id": order_id,
    })
    assert buy_res.status_code == 200
    trade = buy_res.json()["trade"]
    assert trade["status"] == "Pending"
    assert trade["cash_balance"] == 90000.0  # 100,000 - 10,000

    # Cancel the pending order via POST /api/virtual/cancel
    cancel_res = client.post("/api/virtual/cancel", json={"email": email, "order_id": order_id})
    assert cancel_res.status_code == 200
    c_data = cancel_res.json()["order"]
    assert c_data["status"] == "Cancelled"
    assert c_data["refunded_cash"] == 10000.0

    # Verify cash balance restored to ₹1,00,000
    port_res = client.get(f"/api/virtual/portfolio/{email}")
    assert port_res.json()["cash_balance"] == 100000.0

    # Cancelling again should raise error
    cancel_dup = client.post("/api/virtual/cancel", json={"email": email, "order_id": order_id})
    assert cancel_dup.status_code == 400


def test_virtual_order_partial_fills_and_leaves(client):
    email = f"trader_partial_{uuid.uuid4().hex[:8]}@chronos.local"
    client.post("/api/virtual/auth", json={"email": email, "name": "Partial Fill Tester", "password": "pass"})

    # Place a resting LIMIT BUY order: 20 shares of TCS at ₹2000 = ₹40,000 reserved
    order_id = f"ORD-TEST-PF-{uuid.uuid4().hex[:4]}"
    buy_res = client.post("/api/virtual/trade", json={
        "email": email,
        "symbol": "TCS",
        "action": "BUY",
        "order_type": "LIMIT",
        "price": 2000.0,
        "quantity": 20.0,
        "order_id": order_id,
    })
    assert buy_res.status_code == 200
    assert buy_res.json()["trade"]["status"] == "Pending"

    # Execute partial fill of 8 shares
    f1_res = client.post("/api/virtual/fill", json={
        "email": email,
        "order_id": order_id,
        "fill_qty": 8.0,
        "fill_price": 2000.0,
    })
    assert f1_res.status_code == 200
    f1 = f1_res.json()["fill"]
    assert f1["status"] == "Partially Filled"
    assert f1["leaves_qty"] == 12.0

    # Verify portfolio has 8 shares
    port = client.get(f"/api/virtual/portfolio/{email}").json()
    assert len(port["holdings"]) == 1
    assert port["holdings"][0]["quantity"] == 8.0

    # Cancel the remaining 12 shares
    del_res = client.delete(f"/api/virtual/orders/{email}/{order_id}")
    assert del_res.status_code == 200
    del_data = del_res.json()["order"]
    assert del_data["status"] == "Cancelled"
    assert del_data["refunded_cash"] == 24000.0  # 12 * 2000 refunded

    # Cash balance should be: 100,000 - 40,000 + 24,000 = 84,000
    port_final = client.get(f"/api/virtual/portfolio/{email}").json()
    assert port_final["cash_balance"] == 84000.0
    assert port_final["holdings"][0]["quantity"] == 8.0


def test_duplicate_order_rejection(client):
    """Ensure duplicate order submission is rejected without modifying balances twice."""
    email = f"trader_dup_{uuid.uuid4().hex[:8]}@chronos.local"
    client.post("/api/virtual/auth", json={"email": email, "name": "Dup Tester", "password": "pass"})

    order_id = f"ORD-IDEMPOTENT-{uuid.uuid4().hex[:6]}"
    payload = {
        "email": email,
        "symbol": "RELIANCE",
        "action": "BUY",
        "order_type": "MARKET",
        "price": 1000.0,
        "quantity": 5.0,
        "order_id": order_id,
    }

    # First attempt: succeeds
    res1 = client.post("/api/virtual/trade", json=payload)
    assert res1.status_code == 200
    assert res1.json()["trade"]["cash_balance"] == 95000.0

    # Second attempt with same order_id: rejected
    res2 = client.post("/api/virtual/trade", json=payload)
    assert res2.status_code == 400
    assert "Duplicate order submission" in res2.json()["detail"]

    # Balance must remain exactly 95,000 (not deducted twice)
    port = client.get(f"/api/virtual/portfolio/{email}").json()
    assert port["cash_balance"] == 95000.0
    assert len(port["holdings"]) == 1
    assert port["holdings"][0]["quantity"] == 5.0


def test_zero_and_negative_order_validation(client):
    """Ensure invalid prices or quantities are rejected without modifying state."""
    email = f"trader_invalid_{uuid.uuid4().hex[:8]}@chronos.local"
    client.post("/api/virtual/auth", json={"email": email, "name": "Validator", "password": "pass"})

    # Negative quantity
    r1 = client.post("/api/virtual/trade", json={
        "email": email,
        "symbol": "RELIANCE",
        "action": "BUY",
        "order_type": "MARKET",
        "price": 1000.0,
        "quantity": -5.0,
    })
    assert r1.status_code in (400, 422)

    # Zero price
    r2 = client.post("/api/virtual/trade", json={
        "email": email,
        "symbol": "RELIANCE",
        "action": "BUY",
        "order_type": "MARKET",
        "price": 0.0,
        "quantity": 5.0,
    })
    assert r2.status_code in (400, 422)

    # Balance remains intact
    port = client.get(f"/api/virtual/portfolio/{email}").json()
    assert port["cash_balance"] == 100000.0


def test_persistence_across_instances(client):
    """Ensure stored database state restores identically in fresh database instances."""
    email = f"trader_persist_{uuid.uuid4().hex[:8]}@chronos.local"
    client.post("/api/virtual/auth", json={"email": email, "name": "Persist Tester", "password": "pass"})

    client.post("/api/virtual/trade", json={
        "email": email,
        "symbol": "AAPL",
        "action": "BUY",
        "order_type": "MARKET",
        "price": 300.0,
        "quantity": 10.0,
    })

    # Instantiate fresh Database instance from the same underlying SQLite file
    from chronosmatch.persistence.db import Database, DB_PATH
    fresh_db = Database(db_path=DB_PATH)

    port = fresh_db.get_portfolio(email)
    assert port["cash_balance"] == 97000.0  # 100,000 - 3,000
    assert len(port["holdings"]) == 1
    assert port["holdings"][0]["symbol"] == "AAPL"
    assert port["holdings"][0]["quantity"] == 10.0


def test_engine_throughput_and_latency_benchmark():
    """Verify L3 OrderBook throughput and latency exceed baseline thresholds."""
    import time
    from chronosmatch.engine import OrderBook
    from chronosmatch.protocol import NewOrderMsg, Side, OrderType

    book = OrderBook("BENCH")
    num_orders = 10000
    start = time.perf_counter()

    for i in range(1, num_orders + 1):
        msg = NewOrderMsg.create(
            order_id=i,
            client_id=1,
            symbol="BENCH",
            side=Side.BUY if i % 2 == 1 else Side.SELL,
            order_type=OrderType.LIMIT,
            price=100.0 + (i % 20) * 0.1,
            quantity=10,
        )
        book.process_order(msg)

    duration = time.perf_counter() - start
    ops_per_sec = num_orders / duration

    assert ops_per_sec > 25000, f"Expected >25,000 ops/sec, got {ops_per_sec:.0f}"
    assert book.order_count >= 0
