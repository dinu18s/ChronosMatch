"""Unit tests for ChronosMatch Risk Calculator, Backtesting Engine, and Scenario Analysis."""

import pytest
from chronosmatch.engine.risk_lab import (
    calculate_position_size,
    calculate_sma,
    calculate_ema,
    calculate_rsi,
    run_backtest,
    run_scenario_stress_test,
)


def test_position_sizing_calculation_standard():
    """Verify standard 2% risk rule calculation."""
    # ₹1,00,000 balance, 2% risk = ₹2,000 risk budget
    # Entry ₹1,000, Stop Loss ₹950 -> ₹50 price risk per share
    # With 0.05% fee, effective risk per share is approx 51.00
    res = calculate_position_size(
        account_balance=100000.0,
        entry_price=1000.0,
        stop_loss_price=950.0,
        risk_pct=2.0,
        target_price=1150.0,
        fee_pct=0.05,
    )

    assert res["max_risk_budget_inr"] == 2000.0
    assert res["recommended_shares"] == 39  # floor(2000 / ~51)
    assert res["max_loss_inr"] <= 2000.0
    assert res["potential_profit_inr"] > 5500.0
    assert res["risk_reward_ratio"] >= 2.5
    assert res["breakeven_price"] > 1000.0
    assert res["is_long"] is True


def test_position_sizing_input_validation():
    """Verify rejection of invalid parameters."""
    with pytest.raises(ValueError, match="Account balance must be greater than zero"):
        calculate_position_size(account_balance=-500, entry_price=100, stop_loss_price=90)

    with pytest.raises(ValueError, match="Entry price must be greater than zero"):
        calculate_position_size(account_balance=100000, entry_price=0, stop_loss_price=90)

    with pytest.raises(ValueError, match="Risk percentage must be between"):
        calculate_position_size(account_balance=100000, entry_price=100, stop_loss_price=90, risk_pct=0)

    with pytest.raises(ValueError, match="cannot be identical"):
        calculate_position_size(account_balance=100000, entry_price=100, stop_loss_price=100)


def test_sma_ema_rsi_indicators():
    """Verify technical indicator calculations."""
    prices = [100.0, 102.0, 104.0, 106.0, 108.0, 110.0, 105.0, 102.0, 98.0, 95.0, 100.0, 105.0, 110.0, 115.0, 120.0, 125.0]

    sma_5 = calculate_sma(prices, period=5)
    assert len(sma_5) == len(prices)
    assert sma_5[0] is None
    assert sma_5[3] is None
    assert sma_5[4] == sum(prices[:5]) / 5

    ema_5 = calculate_ema(prices, period=5)
    assert len(ema_5) == len(prices)
    assert ema_5[4] == sma_5[4]
    assert ema_5[5] is not None

    rsi_14 = calculate_rsi(prices, period=14)
    assert len(rsi_14) == len(prices)
    assert rsi_14[14] is not None
    assert 0.0 <= rsi_14[14] <= 100.0


def test_backtest_sma_crossover_execution_and_metrics():
    """Verify chronological bar-by-bar backtest without lookahead bias and fee deductions."""
    # Synthetic trending price wave: 30 bars
    prices = [
        100, 101, 102, 103, 105, 108, 112, 115, 120, 122, 125, 120, 115, 110, 105,
        102, 100, 98, 97, 96, 98, 102, 106, 110, 115, 120, 125, 128, 130, 135
    ]
    prices = [float(p) for p in prices]

    res = run_backtest(
        prices=prices,
        strategy="SMA_CROSSOVER",
        initial_capital=100000.0,
        fast_period=3,
        slow_period=6,
        fee_pct=0.05,
    )

    metrics = res["metrics"]
    assert "total_return_pct" in metrics
    assert "buy_and_hold_return_pct" in metrics
    assert "max_drawdown_pct" in metrics
    assert "win_rate_pct" in metrics
    assert "profit_factor" in metrics
    assert "exposure_time_pct" in metrics
    assert metrics["final_equity"] > 0
    assert len(res["equity_curve"]) == len(prices)
    assert len(res["drawdown_curve"]) == len(prices)

    # Verify transaction fees were deducted
    assert metrics["total_fees_paid"] > 0


def test_backtest_stop_loss_trigger():
    """Verify stop-loss execution during adverse price movements."""
    prices = [110.0, 105.0, 100.0, 98.0, 104.0, 110.0, 95.0, 85.0, 80.0, 75.0]

    res = run_backtest(
        prices=prices,
        strategy="SMA_CROSSOVER",
        initial_capital=100000.0,
        fast_period=2,
        slow_period=4,
        stop_loss_pct=5.0,  # 5% hard stop
        fee_pct=0.05,
    )

    trades = res["trades"]
    stop_trades = [t for t in trades if t["reason"] == "Stop Loss Hit"]
    assert len(stop_trades) >= 1
    assert stop_trades[0]["pnl"] < 0


def test_scenario_stress_testing():
    """Verify hypothetical portfolio stress testing shocks."""
    portfolio_cash = 40000.0
    holdings = {
        "RELIANCE": {"quantity": 20, "current_price": 1200.0, "avg_buy_price": 1150.0},
        "TCS": {"quantity": 10, "current_price": 2500.0, "avg_buy_price": 2400.0},
    }
    # Total holdings = 20*1200 + 10*2500 = 24,000 + 25,000 = 49,000
    # Total equity = 40,000 + 49,000 = 89,000

    res = run_scenario_stress_test(
        portfolio_cash=portfolio_cash,
        holdings=holdings,
        price_shock_pct=-15.0,  # -15% market drop
        volatility_shock_multiplier=1.5,
    )

    assert res["baseline_total_equity"] == 89000.0
    assert res["stressed_total_equity"] < 89000.0
    assert res["equity_loss_inr"] > 7000.0
    assert res["stressed_holdings_val"] < 49000.0
    assert res["cash_buffer_pct"] > 40.0
    assert len(res["position_impacts"]) == 2
    assert "disclaimer" in res


def test_api_risk_calculate_endpoint():
    """Verify FastAPI /api/risk/calculate endpoint."""
    from fastapi.testclient import TestClient
    from api.index import app

    client = TestClient(app)
    response = client.post(
        "/api/risk/calculate",
        json={
            "account_balance": 100000.0,
            "entry_price": 1000.0,
            "stop_loss_price": 950.0,
            "risk_pct": 2.0,
            "target_price": 1150.0,
            "fee_pct": 0.05,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["recommended_shares"] == 39
    assert data["max_loss_inr"] <= 2000.0
    assert data["breakeven_price"] > 1000.0


def test_api_backtest_run_endpoint():
    """Verify FastAPI /api/backtest/run endpoint."""
    from fastapi.testclient import TestClient
    from api.index import app

    client = TestClient(app)
    response = client.post(
        "/api/backtest/run",
        json={
            "prices": [100, 102, 105, 108, 112, 115, 120, 118, 115, 110, 105, 100, 95, 90, 85, 88, 92, 98, 105, 110],
            "strategy": "SMA_CROSSOVER",
            "fast_period": 3,
            "slow_period": 5,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "metrics" in data
    assert "total_return_pct" in data["metrics"]
    assert "equity_curve" in data


def test_api_stress_test_endpoint():
    """Verify FastAPI /api/risk/stress-test endpoint."""
    from fastapi.testclient import TestClient
    from api.index import app

    client = TestClient(app)
    response = client.post(
        "/api/risk/stress-test",
        json={
            "portfolio_cash": 60000.0,
            "holdings": {
                "RELIANCE": {"quantity": 10, "current_price": 2500.0, "avg_buy_price": 2400.0}
            },
            "price_shock_pct": -20.0,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["baseline_total_equity"] == 85000.0
    assert data["equity_loss_inr"] > 0
    assert "risk_rating" in data
