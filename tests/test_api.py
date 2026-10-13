"""Tests for ChronosMatch FastAPI endpoints and engine integration."""

import pytest
from fastapi.testclient import TestClient

from api.main import app
from chronosmatch.engine import OrderBook
from chronosmatch.protocol import NewOrderMsg, Side, OrderType, price_to_fixed


@pytest.fixture
def client():
    return TestClient(app)


def test_order_book_integration():
    book = OrderBook("ETHUSDT")
    order = NewOrderMsg.create(
        order_id=5001,
        client_id=1,
        symbol="ETHUSDT",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        price=3500.0,
        quantity=5,
    )
    reports = book.process_order(order)
    assert len(reports) == 1
    assert book.best_bid() == (price_to_fixed(3500.0), 5)


def test_api_root_endpoint(client):
    res = client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "online"
    assert "ChronosMatch" in data["service"]


def test_api_health_endpoint(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_api_bbo_endpoint(client):
    res = client.get("/api/bbo/BTCUSDT")
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "BTCUSDT"
    assert "best_bid" in data
    assert "best_ask" in data


def test_api_depth_endpoint(client):
    res = client.get("/api/depth/BTCUSDT?depth=5")
    assert res.status_code == 200
    data = res.json()
    assert data["symbol"] == "BTCUSDT"
    assert len(data["bids"]) > 0
    assert len(data["asks"]) > 0


def test_api_place_and_cancel_order(client):
    # Place a limit buy order far below market
    place_payload = {
        "order_id": 99001,
        "client_id": 42,
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_type": "LIMIT",
        "price": 50000.0,
        "quantity": 3,
        "tif": "GTC",
    }
    res = client.post("/api/order", json=place_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "processed"
    assert data["order_id"] == 99001
    assert len(data["execution_reports"]) == 1
    assert data["execution_reports"][0]["exec_type"] == "NEW"

    # Cancel the resting order
    del_res = client.delete("/api/order/BTCUSDT/99001")
    assert del_res.status_code == 200
    del_data = del_res.json()
    assert del_data["status"] == "cancelled"
    assert del_data["order_id"] == 99001
