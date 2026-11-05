# -*- coding: utf-8 -*-
"""Comprehensive tests for ChronosMatch Developer API Playground endpoints."""

import uuid
import pytest
from fastapi.testclient import TestClient

from api.index import app
from chronosmatch.persistence.db import db


@pytest.fixture
def client():
    return TestClient(app)


def test_api_market_instruments(client):
    """Verify GET /api/market/instruments returns catalog of trading instruments."""
    res = client.get("/api/market/instruments")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["count"] > 0
    assert isinstance(data["instruments"], list)
    symbols = [inst["symbol"] for inst in data["instruments"]]
    assert "RELIANCE" in symbols
    assert "TCS" in symbols


def test_api_market_quote(client):
    """Verify GET /api/market/quote/{symbol} returns current price metrics."""
    res = client.get("/api/market/quote/RELIANCE")
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "RELIANCE"
    assert "price" in data
    assert data["price"] > 0
    assert "change_pct" in data


def test_api_market_depth(client):
    """Verify GET /api/market/depth/{symbol} returns L2 bids and asks."""
    res = client.get("/api/market/depth/RELIANCE?depth=5")
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "RELIANCE"
    assert len(data["bids"]) <= 5
    assert len(data["asks"]) <= 5
    if data["bids"]:
        assert "price" in data["bids"][0]
        assert "quantity" in data["bids"][0]


def test_api_market_bbo(client):
    """Verify GET /api/market/bbo/{symbol} returns best bid and ask."""
    res = client.get("/api/market/bbo/RELIANCE")
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "RELIANCE"
    assert "best_bid" in data
    assert "best_ask" in data


def test_api_virtual_order_lifecycle(client):
    """Verify order lifecycle: submit order -> inspect status -> cancel order."""
    email = f"dev_playground_{uuid.uuid4().hex[:8]}@chronos.local"
    # 1. Register account
    reg = client.post("/api/virtual/register", json={
        "email": email,
        "name": "Dev Playground Tester",
        "password": "Password123!",
    })
    assert reg.status_code == 200

    # 2. Submit simulated LIMIT BUY order
    trade_res = client.post("/api/virtual/trade", json={
        "email": email,
        "symbol": "RELIANCE",
        "action": "BUY",
        "order_type": "LIMIT",
        "price": 1000.0,
        "quantity": 5.0,
    })
    assert trade_res.status_code == 200
    trade_data = trade_res.json()
    assert trade_data["status"] == "success"
    order_id = trade_data["trade"]["order_id"]
    assert order_id is not None

    # 3. Retrieve order status by single order ID
    order_res = client.get(f"/api/virtual/orders/{email}/{order_id}")
    assert order_res.status_code == 200
    order_info = order_res.json()
    assert order_info["status"] == "ok"
    assert order_info["order"]["order_id"] == order_id
    assert order_info["order"]["symbol"] == "RELIANCE"
    assert order_info["order"]["quantity"] == 5.0

    # 4. Cancel the resting order
    cancel_res = client.post("/api/virtual/cancel", json={
        "email": email,
        "order_id": order_id,
    })
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "success"

    # 5. Check order status is updated to Cancelled
    cancelled_res = client.get(f"/api/virtual/orders/{email}/{order_id}")
    assert cancelled_res.status_code == 200
    assert cancelled_res.json()["order"]["status"] == "Cancelled"


def test_api_virtual_account_and_portfolio(client):
    """Verify GET /api/virtual/account/{email} and portfolio endpoints."""
    email = f"account_dev_{uuid.uuid4().hex[:8]}@chronos.local"
    client.post("/api/virtual/register", json={
        "email": email,
        "name": "API Developer",
        "password": "DevPassword123!",
    })

    # Account summary
    acc_res = client.get(f"/api/virtual/account/{email}")
    assert acc_res.status_code == 200
    acc_data = acc_res.json()
    assert acc_data["status"] == "ok"
    assert acc_data["email"] == email
    assert acc_data["portfolio"]["cash_balance"] == 100000.00

    # Portfolio holdings
    port_res = client.get(f"/api/virtual/portfolio/{email}")
    assert port_res.status_code == 200
    port_data = port_res.json()
    assert port_data["cash_balance"] == 100000.00
    assert isinstance(port_data["holdings"], list)


def test_api_error_handling(client):
    """Verify proper 404 and 400 error responses for invalid developer API requests."""
    # Unknown order for user
    res = client.get("/api/virtual/orders/test@example.com/non-existent-order-12345")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"].lower()

    # Invalid order placement parameters
    res_bad = client.post("/api/virtual/trade", json={
        "email": "test@example.com",
        "symbol": "RELIANCE",
        "action": "INVALID_ACTION",
        "price": -100.0,
        "quantity": 0,
    })
    assert res_bad.status_code in (400, 422)


def test_websocket_endpoint(client):
    """Verify WebSocket connection and initial handshake event."""
    with client.websocket_connect("/api/market/ws") as websocket:
        data = websocket.receive_json()
        assert data["type"] == "connection_status"
        assert data["status"] == "connected"


def test_api_journal_endpoint(client):
    """Verify trade journal endpoint returns executed trade history."""
    email = f"journal_dev_{uuid.uuid4().hex[:8]}@chronos.local"
    res = client.get(f"/api/virtual/journal/{email}")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_api_instruments_search(client):
    """Verify searching instruments returns matching tickers."""
    res = client.get("/api/market/search?q=TCS")
    assert res.status_code == 200
    data = res.json()
    assert any(inst["symbol"] == "TCS" for inst in data)
