"""Automated tests for ChronosMatch Corporate Actions Simulator module."""

import pytest
from fastapi.testclient import TestClient
from api.index import app
from chronosmatch.persistence.db import Database, calculate_corporate_action
import tempfile
from pathlib import Path


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp_dir:
        db_path = Path(tmp_dir) / "test_corporate.db"
        test_db = Database(db_path=db_path)
        yield test_db


def test_corporate_actions_events_catalog(client):
    """Verify the corporate action events catalog returns all expected simulated actions."""
    response = client.get("/api/corporate-actions/events")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    events = data["events"]
    assert len(events) >= 7

    # All events must be marked as simulated
    for ev in events:
        assert ev["is_simulated"] is True
        assert "id" in ev
        assert "symbol" in ev
        assert "action_type" in ev
        assert "parameters" in ev

    action_types = {ev["action_type"] for ev in events}
    expected_types = {"DIVIDEND", "STOCK_SPLIT", "REVERSE_SPLIT", "BONUS_ISSUE", "RIGHTS_ISSUE", "BUYBACK", "SYMBOL_CHANGE"}
    assert expected_types.issubset(action_types)


def test_deterministic_corporate_action_math():
    """Verify mathematical properties: zero artificial profit on splits & bonus issues."""
    # 2:1 Stock Split
    res_split = calculate_corporate_action(
        action_type="STOCK_SPLIT",
        parameters={"split_from": 1, "split_to": 2},
        current_qty=50.0,
        current_avg=1000.0,
        current_cash=20000.0,
        market_price=1000.0,
    )
    assert res_split["after"]["quantity"] == 100.0
    assert res_split["after"]["avg_buy_price"] == 500.0
    assert res_split["after"]["total_invested"] == 50000.0
    assert res_split["impact"]["valuation_impact"] == 0.0

    # 1:1 Bonus Issue
    res_bonus = calculate_corporate_action(
        action_type="BONUS_ISSUE",
        parameters={"bonus_shares": 1, "existing_shares": 1},
        current_qty=50.0,
        current_avg=1000.0,
        current_cash=20000.0,
        market_price=1000.0,
    )
    assert res_bonus["after"]["quantity"] == 100.0
    assert res_bonus["after"]["avg_buy_price"] == 500.0
    assert res_bonus["after"]["total_invested"] == 50000.0
    assert res_bonus["impact"]["valuation_impact"] == 0.0

    # 1:5 Reverse Split
    res_rev = calculate_corporate_action(
        action_type="REVERSE_SPLIT",
        parameters={"from_shares": 5, "to_shares": 1},
        current_qty=100.0,
        current_avg=200.0,
        current_cash=10000.0,
        market_price=200.0,
    )
    assert res_rev["after"]["quantity"] == 20.0
    assert res_rev["after"]["avg_buy_price"] == 1000.0
    assert res_rev["impact"]["valuation_impact"] == 0.0


def test_simulate_endpoint(client):
    """Test POST /api/corporate-actions/simulate preview calculation."""
    payload = {
        "symbol": "RELIANCE",
        "action_type": "DIVIDEND",
        "parameters": {"dividend_per_share": 10.0},
        "current_quantity": 50.0,
        "current_avg_price": 1180.0,
        "current_cash": 100000.0,
        "market_price": 1180.0,
    }
    response = client.post("/api/corporate-actions/simulate", json=payload)
    assert response.status_code == 200
    res = response.json()["simulation"]
    assert res["impact"]["cash_adjustment"] == 500.0
    assert res["after"]["cash_balance"] == 100500.0
    assert res["after"]["quantity"] == 50.0


def test_database_apply_corporate_actions(temp_db):
    """Test full database lifecycle: user creation, trading, applying actions, and duplicate prevention."""
    email = "trader@chronosmatch.io"
    temp_db.create_user(email, "Trader One", "SecurePass123!")
    temp_db.reset_account(email, starting_balance=100000.0)

    # Buy 100 shares of RELIANCE @ ₹1,000 (Cost ₹100,000, cash balance becomes 0)
    temp_db.execute_virtual_trade(
        email=email,
        symbol="RELIANCE",
        action="BUY",
        order_type="MARKET",
        quantity=100.0,
        price=1000.0,
    )

    port = temp_db.get_portfolio(email)
    assert len(port["holdings"]) == 1
    assert port["holdings"][0]["quantity"] == 100.0
    assert port["holdings"][0]["avg_buy_price"] == 1000.0

    # 1. Apply Cash Dividend: ₹10/share
    div_res = temp_db.apply_corporate_action(
        email=email,
        action_id="SIM-DIV-TEST-01",
        symbol="RELIANCE",
        action_type="DIVIDEND",
        parameters={"dividend_per_share": 10.0},
    )
    assert div_res["status"] == "applied"
    assert div_res["impact"]["cash_adjustment"] == 1000.0
    acct = temp_db.get_account(email)
    assert acct["cash_balance"] == 1000.0

    # 2. Prevent duplicate application of the same action ID
    with pytest.raises(ValueError, match="already been applied"):
        temp_db.apply_corporate_action(
            email=email,
            action_id="SIM-DIV-TEST-01",
            symbol="RELIANCE",
            action_type="DIVIDEND",
            parameters={"dividend_per_share": 10.0},
        )

    # 3. Apply 2:1 Stock Split
    split_res = temp_db.apply_corporate_action(
        email=email,
        action_id="SIM-SPLIT-TEST-01",
        symbol="RELIANCE",
        action_type="STOCK_SPLIT",
        parameters={"split_from": 1, "split_to": 2},
    )
    assert split_res["status"] == "applied"
    assert split_res["after"]["quantity"] == 200.0
    assert split_res["after"]["avg_buy_price"] == 500.0

    port = temp_db.get_portfolio(email)
    assert port["holdings"][0]["quantity"] == 200.0
    assert port["holdings"][0]["avg_buy_price"] == 500.0

    # 4. Check history retrieval
    history = temp_db.get_corporate_actions(email)
    assert len(history) == 2
    assert history[0]["id"] in ["SIM-DIV-TEST-01", "SIM-SPLIT-TEST-01"]


def test_rights_issue_insufficient_cash(temp_db):
    """Verify rights issue fails cleanly if cash balance is insufficient to pay subscription price."""
    email = "tight_budget@chronosmatch.io"
    temp_db.create_user(email, "Budget Trader", "Pass1234!")
    temp_db.reset_account(email, starting_balance=100.0)  # only ₹100 cash

    # Manually seed a holding of 100 shares
    with temp_db.get_connection() as conn:
        conn.execute(
            "INSERT INTO holdings (email, symbol, quantity, avg_buy_price, total_invested, updated_at) "
            "VALUES (?, 'BHARTIARTL', 100, 800, 80000, '2026-11-06T00:00:00Z')",
            (email,),
        )

    # Exercise 10 rights @ ₹535 = ₹5,350 needed, but cash is ₹100
    with pytest.raises(ValueError, match="Insufficient cash balance"):
        temp_db.apply_corporate_action(
            email=email,
            action_id="SIM-RIGHTS-FAIL-01",
            symbol="BHARTIARTL",
            action_type="RIGHTS_ISSUE",
            parameters={"rights_shares": 1, "for_shares": 10, "subscription_price": 535.0, "exercised_shares": 10},
        )


def test_buyback_and_symbol_change(temp_db):
    """Verify stock buyback and symbol change operations."""
    email = "corp_actions@chronosmatch.io"
    temp_db.create_user(email, "Corp Trader", "Pass1234!")
    temp_db.reset_account(email, starting_balance=10000.0)

    # Seed 100 shares of WIPRO @ 400
    with temp_db.get_connection() as conn:
        conn.execute(
            "INSERT INTO holdings (email, symbol, quantity, avg_buy_price, total_invested, updated_at) "
            "VALUES (?, 'WIPRO', 100, 400, 40000, '2026-11-06T00:00:00Z')",
            (email,),
        )

    # Tender 25 shares for buyback @ 450
    bb_res = temp_db.apply_corporate_action(
        email=email,
        action_id="SIM-BB-WIPRO-01",
        symbol="WIPRO",
        action_type="BUYBACK",
        parameters={"buyback_price": 450.0, "tendered_shares": 25.0},
    )
    assert bb_res["status"] == "applied"
    assert bb_res["after"]["quantity"] == 75.0
    # Proceeds = 25 * 450 = 11250. Cash: 10000 + 11250 = 21250
    acct = temp_db.get_account(email)
    assert acct["cash_balance"] == 21250.0

    # Seed MOTHERSUM and test symbol change to MOTHERSON
    with temp_db.get_connection() as conn:
        conn.execute(
            "INSERT INTO holdings (email, symbol, quantity, avg_buy_price, total_invested, updated_at) "
            "VALUES (?, 'MOTHERSUM', 50, 120, 6000, '2026-11-06T00:00:00Z')",
            (email,),
        )

    sym_res = temp_db.apply_corporate_action(
        email=email,
        action_id="SIM-SYM-01",
        symbol="MOTHERSUM",
        action_type="SYMBOL_CHANGE",
        parameters={"new_symbol": "MOTHERSON"},
    )
    assert sym_res["status"] == "applied"
    port = temp_db.get_portfolio(email)
    holding_symbols = [h["symbol"] for h in port["holdings"]]
    assert "MOTHERSON" in holding_symbols
    assert "MOTHERSUM" not in holding_symbols


def test_api_apply_duplicate_prevention(client):
    """Verify POST /api/corporate-actions/apply prevents duplicate execution."""
    import uuid
    test_id = f"SIM-API-TEST-DUP-{uuid.uuid4().hex[:8]}"
    payload = {
        "action_id": test_id,
        "symbol": "RELIANCE",
        "action_type": "DIVIDEND",
        "parameters": {"dividend_per_share": 5.0},
        "current_quantity": 100.0,
        "current_avg_price": 1000.0,
        "current_cash": 50000.0,
        "email": "demo@chronosmatch.io",
    }
    # First application succeeds
    res1 = client.post("/api/corporate-actions/apply", json=payload)
    assert res1.status_code == 200

    # Second application with same action_id fails with 409 Conflict
    res2 = client.post("/api/corporate-actions/apply", json=payload)
    assert res2.status_code == 409
    assert "already been applied" in res2.json()["detail"]
