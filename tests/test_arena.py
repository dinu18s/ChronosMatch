"""Comprehensive automated test suite for Algorithmic Trading Arena & Agent Competition."""

import pytest
from fastapi.testclient import TestClient

from api.index import app
from chronosmatch.engine.arena import (
    AdaptiveAgent,
    AgentDecision,
    AgentType,
    ArenaCompetition,
    ConservativeAgent,
    HumanAgent,
    LiquidityHunterAgent,
    MarketCondition,
    MarketMakingAgent,
    MarketTick,
    MeanReversionAgent,
    MomentumAgent,
    OrderAction,
    calc_bollinger_bands,
    calc_momentum_roc,
    calc_rsi,
    calc_sma,
    generate_market_scenario,
    run_strategy_evolution_test,
)


@pytest.fixture
def client():
    return TestClient(app)


# =====================================================================
# 1. TECHNICAL INDICATORS & MARKET GENERATOR TESTS
# =====================================================================
def test_arena_indicators_math():
    """Verify indicators calculate correctly without lookahead bias."""
    prices = [100.0, 102.0, 101.0, 105.0, 107.0, 106.0, 110.0, 112.0]

    # SMA
    sma3 = calc_sma(prices, 3)
    assert sma3 == pytest.approx((106.0 + 110.0 + 112.0) / 3.0)
    assert calc_sma(prices, 20) is None  # Not enough data

    # Momentum ROC
    roc3 = calc_momentum_roc(prices, 3)
    # (112.0 - 107.0) / 107.0 * 100
    assert roc3 == pytest.approx(((112.0 - 107.0) / 107.0) * 100.0)

    # RSI
    rsi_val = calc_rsi(prices, 5)
    assert rsi_val is not None
    assert 0.0 <= rsi_val <= 100.0

    # Bollinger Bands
    long_series = [100.0 + i * 0.5 for i in range(25)]
    bb = calc_bollinger_bands(long_series, period=20, num_std=2.0)
    assert bb is not None
    lower, mid, upper = bb
    assert lower < mid < upper


def test_arena_market_scenario_generation():
    """Verify market scenario generation is deterministic and respects conditions."""
    ticks_1 = generate_market_scenario(seed=123, symbol="BTCUSDT", num_steps=50, condition=MarketCondition.TRENDING_BULL)
    ticks_2 = generate_market_scenario(seed=123, symbol="BTCUSDT", num_steps=50, condition=MarketCondition.TRENDING_BULL)

    assert len(ticks_1) == 50
    assert len(ticks_2) == 50
    # Deterministic equality
    for t1, t2 in zip(ticks_1, ticks_2):
        assert t1.step == t2.step
        assert t1.price == t2.price
        assert t1.best_bid == t2.best_bid
        assert t1.best_ask == t2.best_ask


# =====================================================================
# 2. INDEPENDENT AGENT LOGIC TESTS
# =====================================================================
def test_momentum_agent_decision():
    """Verify MomentumAgent enters on bullish crossover and holds/exits appropriately."""
    agent = MomentumAgent("mom1", "Momentum Test", AgentType.MOMENTUM, 100_000.0, {"fast_period": 3, "slow_period": 5, "roc_threshold": 0.1})

    # Warmup
    tick1 = MarketTick(1, 100.0, 101.0, 99.0, 50, 99.9, 100.1, 0.2, 20, 20, "BULL")
    d1 = agent.decide(tick1, [100.0])
    assert d1.action == OrderAction.HOLD
    assert d1.rule_triggered == "WARMUP_PERIOD"

    # Upward crossover: fast MA > slow MA and ROC > threshold
    history = [100.0, 100.5, 101.0, 103.0, 106.0, 110.0]
    tick2 = MarketTick(6, 110.0, 111.0, 109.0, 80, 109.9, 110.1, 0.2, 25, 25, "BULL")
    d2 = agent.decide(tick2, history)
    assert d2.action == OrderAction.BUY
    assert d2.proposed_qty > 0
    assert "BULLISH_CROSSOVER" in d2.rule_triggered


def test_mean_reversion_agent_decision():
    """Verify MeanReversionAgent buys oversold drops and closes at mean."""
    agent = MeanReversionAgent("mr1", "MeanRev Test", AgentType.MEAN_REVERSION, 100_000.0, {"bb_period": 5, "num_std": 1.5, "rsi_oversold": 35.0})

    # Plunge into oversold
    history = [100.0, 99.0, 98.0, 97.0, 96.0, 85.0]
    tick = MarketTick(6, 85.0, 86.0, 84.0, 90, 84.9, 85.1, 0.2, 30, 15, "RANGE")
    d = agent.decide(tick, history)
    assert d.action == OrderAction.BUY
    assert "OVERSOLD_PIERCE" in d.rule_triggered


def test_market_making_agent_decision():
    """Verify MarketMakingAgent quotes two-sided spreads and enforces inventory limits."""
    agent = MarketMakingAgent("mm1", "MM Test", AgentType.MARKET_MAKER, 100_000.0, {"half_spread_pct": 0.005, "max_inventory": 3.0, "quote_size": 1.0})

    # Normal quoting
    tick = MarketTick(1, 100.0, 101.0, 99.0, 50, 99.9, 100.1, 0.2, 20, 20, "RANGE")
    d = agent.decide(tick, [100.0])
    assert "QUOTING_PASSIVE_LADDER" in d.rule_triggered

    # Force inventory max limit
    agent.state.position_qty = 3.5
    d_limit = agent.decide(tick, [100.0])
    assert d_limit.action == OrderAction.SELL
    assert "INVENTORY_LIMIT_EXCEEDED" in d_limit.rule_triggered


def test_liquidity_hunter_agent_decision():
    """Verify LiquidityHunterAgent triggers on order book depth imbalance."""
    agent = LiquidityHunterAgent("lh1", "Hunter Test", AgentType.LIQUIDITY_HUNTER, 100_000.0, {"min_depth": 10, "imbalance_threshold": 0.30})

    # Massive bid imbalance (bids: 40, asks: 10 -> imbalance = 30/50 = +0.60)
    tick = MarketTick(1, 100.0, 101.0, 99.0, 80, 99.9, 100.1, 0.2, 40, 10, "BULL")
    d = agent.decide(tick, [100.0])
    assert d.action == OrderAction.BUY
    assert "BID_LIQUIDITY_SURGE" in d.rule_triggered


def test_conservative_agent_risk_guard():
    """Verify ConservativeAgent cuts loss when stop-loss threshold is breached."""
    agent = ConservativeAgent("cons1", "Cons Test", AgentType.CONSERVATIVE, 100_000.0, {"stop_loss_pct": 1.0, "take_profit_pct": 3.0})

    # Set up open long position at 100.0
    agent.state.position_qty = 5.0
    agent.state.avg_entry_price = 100.0

    # Price drops to 98.5 (down 1.5% > 1.0% stop-loss)
    tick_loss = MarketTick(5, 98.5, 99.0, 98.0, 40, 98.4, 98.6, 0.2, 20, 20, "BEAR")
    d = agent.decide(tick_loss, [100.0, 99.5, 99.0, 98.5])
    assert d.action == OrderAction.CLOSE
    assert "STOP_LOSS_GUARD" in d.rule_triggered


def test_adaptive_agent_regime_shift():
    """Verify AdaptiveAgent calculates efficiency ratio and switches regimes."""
    agent = AdaptiveAgent("adap1", "Adaptive Test", AgentType.ADAPTIVE, 100_000.0, {"regime_window": 5, "trend_threshold": 0.50})

    # Perfectly directional path: 100 -> 102 -> 104 -> 106 -> 108 (Efficiency = 1.0)
    history = [100.0, 102.0, 104.0, 106.0, 108.0]
    tick = MarketTick(5, 108.0, 109.0, 107.0, 60, 107.9, 108.1, 0.2, 25, 25, "BULL")
    d = agent.decide(tick, history)
    assert d.indicators["detected_regime"] == "TREND_FOLLOWING"
    assert d.indicators["efficiency_ratio"] == 1.0


def test_human_agent_discretionary():
    """Verify HumanAgent passes discretionary actions."""
    human = HumanAgent(initial_cash=100_000.0)
    tick = MarketTick(1, 100.0, 101.0, 99.0, 50, 99.9, 100.1, 0.2, 20, 20, "BULL")

    # Default is HOLD
    d_hold = human.decide(tick, [100.0])
    assert d_hold.action == OrderAction.HOLD

    # Queue manual BUY
    human.set_action(OrderAction.BUY, 2.5)
    d_buy = human.decide(tick, [100.0])
    assert d_buy.action == OrderAction.BUY
    assert d_buy.proposed_qty == 2.5
    assert "HUMAN_DISCRETIONARY_BUY" in d_buy.rule_triggered


# =====================================================================
# 3. MULTI-AGENT ARENA COMPETITION TESTS
# =====================================================================
def test_full_arena_competition():
    """Verify full multi-agent competition runs with all agents receiving identical market data."""
    comp = ArenaCompetition(
        seed=42,
        symbol="BTCUSDT",
        num_steps=60,
        initial_cash=100_000.0,
        condition=MarketCondition.TRENDING_BULL,
        include_human=True,
    )

    res = comp.run_full_competition()
    assert res["status"] == "success"
    assert res["seed"] == 42
    assert res["condition"] == "TRENDING_BULL"
    assert len(res["leaderboard"]) == 7  # 6 algos + 1 human

    # Verify starting capital equality across all agents
    for agent in comp.agents:
        assert agent.initial_cash == 100_000.0
        assert agent.state.equity_curve[0]["equity"] > 0

    # Verify rankings and debrief
    winner = res["winner"]
    assert "agent_id" in winner
    assert "total_return_pct" in winner
    assert len(res["debrief"]) > 20
    assert "equity_curves" in res
    assert "recent_decisions" in res


def test_arena_deterministic_reproducibility():
    """Verify competitions with identical seeds produce bit-exact identical returns and trade counts."""
    comp1 = ArenaCompetition(seed=777, symbol="BTCUSDT", num_steps=50, condition=MarketCondition.MEAN_REVERTING)
    res1 = comp1.run_full_competition()

    comp2 = ArenaCompetition(seed=777, symbol="BTCUSDT", num_steps=50, condition=MarketCondition.MEAN_REVERTING)
    res2 = comp2.run_full_competition()

    assert res1["winner"]["name"] == res2["winner"]["name"]
    for m1, m2 in zip(res1["leaderboard"], res2["leaderboard"]):
        assert m1["agent_id"] == m2["agent_id"]
        assert m1["total_return_pct"] == m2["total_return_pct"]
        assert m1["total_trades"] == m2["total_trades"]
        assert m1["max_drawdown_pct"] == m2["max_drawdown_pct"]


# =====================================================================
# 4. STRATEGY EVOLUTION LAB TESTS
# =====================================================================
def test_strategy_evolution_comparison():
    """Verify Strategy Evolution Lab compares baseline vs modified parameters with deltas."""
    res = run_strategy_evolution_test(
        seed=888,
        symbol="BTCUSDT",
        agent_type="MOMENTUM",
        condition="TRENDING_BULL",
        base_params={"fast_period": 5, "slow_period": 20},
        modified_params={"fast_period": 3, "slow_period": 10},
        num_steps=50,
        initial_cash=100_000.0,
    )

    assert res["status"] == "success"
    assert "original" in res
    assert "modified" in res
    assert "deltas" in res
    deltas = res["deltas"]
    assert "return_delta_pct" in deltas
    assert "drawdown_delta_pct" in deltas
    assert "win_rate_delta_pct" in deltas
    assert "trades_delta" in deltas


# =====================================================================
# 5. FASTAPI ROUTE INTEGRATION TESTS
# =====================================================================
def test_api_arena_presets(client):
    """Verify GET /api/arena/presets returns agent descriptions and conditions."""
    response = client.get("/api/arena/presets")
    assert response.status_code == 200
    data = response.json()
    assert "agents" in data
    assert "MOMENTUM" in data["agents"]
    assert "MEAN_REVERSION" in data["agents"]
    assert "MARKET_MAKER" in data["agents"]
    assert "conditions" in data
    assert "TRENDING_BULL" in data["conditions"]


def test_api_arena_run_competition(client):
    """Verify POST /api/arena/run-competition executes successfully."""
    payload = {
        "seed": 555,
        "symbol": "BTCUSDT",
        "num_steps": 40,
        "initial_cash": 50_000.0,
        "condition": "TRENDING_BULL",
        "selected_agents": ["MOMENTUM", "CONSERVATIVE"],
        "include_human": False,
    }
    response = client.post("/api/arena/run-competition", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert len(data["leaderboard"]) == 2
    assert "winner" in data
    assert "debrief" in data


def test_api_arena_compare_strategies(client):
    """Verify POST /api/arena/compare-strategies returns comparative metrics."""
    payload = {
        "seed": 333,
        "symbol": "BTCUSDT",
        "agent_type": "MEAN_REVERSION",
        "condition": "MEAN_REVERTING",
        "base_params": {"bb_period": 20, "num_std": 2.0},
        "modified_params": {"bb_period": 10, "num_std": 1.5},
        "num_steps": 40,
        "initial_cash": 100_000.0,
    }
    response = client.post("/api/arena/compare-strategies", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "deltas" in data
    assert "original" in data
    assert "modified" in data
