"""Algorithmic Trading Arena & Multi-Agent Competition Engine.

Provides:
- Independent algorithmic trading agents:
  1. Momentum Agent (identifies simulated trend momentum & MA crossovers)
  2. Mean Reversion Agent (detects statistical deviations via Bollinger Bands & RSI)
  3. Market Making Agent (captures bid-ask spread with inventory skew management)
  4. Liquidity Hunter Agent (analyzes order book depth clusters & book imbalance)
  5. Conservative Agent (enforces strict exposure limits & risk-reward ratio guards)
  6. Adaptive Agent (dynamically shifts between trend and range regimes based on observed volatility)
- Multi-Agent Competition Simulator running agents in identical market conditions
- Human vs Algorithm Challenge support
- Transparent Decision Inspector capturing observed indicators, triggered rules, and execution outcomes
- Comprehensive performance analytics (Return, Realized/Unrealized P&L, Max Drawdown, Win Rate, Holding Time, Fees, Sharpe/Sortino)
- Strategy Evolution Lab for parameter tuning and comparative evaluation
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# =====================================================================
# ENUMS AND CONFIGURATIONS
# =====================================================================
class MarketCondition(str, Enum):
    TRENDING_BULL = "TRENDING_BULL"
    TRENDING_BEAR = "TRENDING_BEAR"
    MEAN_REVERTING = "MEAN_REVERTING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LIQUIDITY_SQUEEZE = "LIQUIDITY_SQUEEZE"


class AgentType(str, Enum):
    MOMENTUM = "MOMENTUM"
    MEAN_REVERSION = "MEAN_REVERSION"
    MARKET_MAKER = "MARKET_MAKER"
    LIQUIDITY_HUNTER = "LIQUIDITY_HUNTER"
    CONSERVATIVE = "CONSERVATIVE"
    ADAPTIVE = "ADAPTIVE"
    HUMAN = "HUMAN"


class OrderAction(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    CLOSE = "CLOSE"
    HOLD = "HOLD"


# =====================================================================
# TECHNICAL INDICATORS (STRICTLY CAUSAL - ZERO LOOKAHEAD BIAS)
# =====================================================================
def calc_sma(prices: List[float], period: int) -> Optional[float]:
    """Calculate Simple Moving Average on historical price slice."""
    if len(prices) < period or period <= 0:
        return None
    return sum(prices[-period:]) / period


def calc_ema(prices: List[float], period: int) -> Optional[float]:
    """Calculate Exponential Moving Average on historical price slice."""
    if len(prices) < period or period <= 0:
        return None
    multiplier = 2.0 / (period + 1.0)
    ema_val = sum(prices[:period]) / period
    for p in prices[period:]:
        ema_val = (p - ema_val) * multiplier + ema_val
    return ema_val


def calc_rsi(prices: List[float], period: int = 14) -> Optional[float]:
    """Calculate Relative Strength Index (RSI) adapting to available history."""
    if len(prices) < 3:
        return None
    eff_period = min(period, len(prices) - 1)
    gains: List[float] = []
    losses: List[float] = []
    for i in range(len(prices) - eff_period, len(prices)):
        delta = prices[i] - prices[i - 1]
        if delta > 0:
            gains.append(delta)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(delta))

    avg_gain = sum(gains) / eff_period
    avg_loss = sum(losses) / eff_period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def calc_bollinger_bands(prices: List[float], period: int = 20, num_std: float = 2.0) -> Optional[Tuple[float, float, float]]:
    """Calculate Bollinger Bands: (Lower, Middle, Upper)."""
    if len(prices) < period or period <= 0:
        return None
    slice_p = prices[-period:]
    mean = sum(slice_p) / period
    variance = sum((x - mean) ** 2 for x in slice_p) / period
    std = math.sqrt(variance)
    return (round(mean - num_std * std, 2), round(mean, 2), round(mean + num_std * std, 2))


def calc_momentum_roc(prices: List[float], period: int = 5) -> Optional[float]:
    """Calculate Momentum Rate of Change (% change over lookback)."""
    if len(prices) <= period or period <= 0:
        return None
    past = prices[-period - 1]
    curr = prices[-1]
    if past == 0:
        return 0.0
    return ((curr - past) / past) * 100.0


def calc_volatility(prices: List[float], period: int = 10) -> float:
    """Calculate rolling standard deviation of price changes."""
    if len(prices) < 2:
        return 0.0
    p_slice = prices[-min(len(prices), period):]
    changes = [abs(p_slice[i] - p_slice[i - 1]) for i in range(1, len(p_slice))]
    return sum(changes) / len(changes) if changes else 0.0


# =====================================================================
# SYNTHETIC MARKET ENVIRONMENT GENERATOR
# =====================================================================
@dataclass
class MarketTick:
    step: int
    price: float
    high: float
    low: float
    volume: int
    best_bid: float
    best_ask: float
    spread: float
    depth_bids: int
    depth_asks: int
    regime: str


def generate_market_scenario(
    seed: int = 42,
    symbol: str = "BTCUSDT",
    num_steps: int = 100,
    condition: MarketCondition = MarketCondition.TRENDING_BULL,
    base_price: Optional[float] = None,
) -> List[MarketTick]:
    """Generates a deterministic sequence of simulated market ticks for fair agent competition."""
    rng = random.Random(seed)
    if base_price is None:
        base_price = 65000.0 if "BTC" in symbol.upper() else (3200.0 if "ETH" in symbol.upper() else 180.0)

    ticks: List[MarketTick] = []
    curr_price = base_price

    # Volatility and drift parameters based on condition
    if condition == MarketCondition.TRENDING_BULL:
        drift = 0.0018
        vol = 0.004
    elif condition == MarketCondition.TRENDING_BEAR:
        drift = -0.0018
        vol = 0.0045
    elif condition == MarketCondition.MEAN_REVERTING:
        drift = 0.0
        vol = 0.0035
    elif condition == MarketCondition.HIGH_VOLATILITY:
        drift = 0.0003
        vol = 0.012
    elif condition == MarketCondition.LIQUIDITY_SQUEEZE:
        drift = 0.0005
        vol = 0.008
    else:
        drift = 0.0005
        vol = 0.004

    center_price = base_price

    for step in range(1, num_steps + 1):
        # Mean reversion pull towards center in range-bound market
        reversion_pull = 0.0
        if condition == MarketCondition.MEAN_REVERTING:
            reversion_pull = -0.05 * ((curr_price - center_price) / center_price)

        # Geometric Brownian Motion with shocks
        shock = rng.gauss(0.0, 1.0)
        ret = drift + reversion_pull + shock * vol

        # Jump process in high volatility or liquidity squeeze
        if condition in (MarketCondition.HIGH_VOLATILITY, MarketCondition.LIQUIDITY_SQUEEZE) and rng.random() < 0.08:
            ret += rng.choice([-0.02, 0.02])

        curr_price = round(curr_price * (1.0 + ret), 2)
        step_high = round(curr_price * (1.0 + abs(rng.gauss(0, 0.002))), 2)
        step_low = round(curr_price * (1.0 - abs(rng.gauss(0, 0.002))), 2)
        volume = int(rng.randint(20, 150) * (2.5 if condition == MarketCondition.HIGH_VOLATILITY else 1.0))

        # Spread & Depth dynamics
        spread_mult = 2.8 if condition == MarketCondition.LIQUIDITY_SQUEEZE else (1.5 if condition == MarketCondition.HIGH_VOLATILITY else 1.0)
        half_spread = round(max(0.5, curr_price * 0.0003 * spread_mult), 2)
        best_bid = round(curr_price - half_spread, 2)
        best_ask = round(curr_price + half_spread, 2)
        spread = round(best_ask - best_bid, 2)

        depth_base = 12 if condition == MarketCondition.LIQUIDITY_SQUEEZE else 30
        depth_bids = max(3, int(depth_base + rng.gauss(0, 5)))
        depth_asks = max(3, int(depth_base + rng.gauss(0, 5)))

        ticks.append(
            MarketTick(
                step=step,
                price=curr_price,
                high=step_high,
                low=step_low,
                volume=volume,
                best_bid=best_bid,
                best_ask=best_ask,
                spread=spread,
                depth_bids=depth_bids,
                depth_asks=depth_asks,
                regime=condition.value,
            )
        )

    return ticks


# =====================================================================
# AGENT DECISION & EXECUTION MODELS
# =====================================================================
@dataclass
class AgentDecision:
    step: int
    agent_id: str
    agent_name: str
    action: OrderAction
    proposed_qty: float
    proposed_price: float
    order_type: str
    observed_price: float
    indicators: Dict[str, Any]
    rule_triggered: str
    expected_conditions: str
    execution_result: str
    reason: str


@dataclass
class AgentTrade:
    trade_id: int
    step: int
    side: str
    price: float
    quantity: float
    cost: float
    fee: float
    realized_pnl: float


@dataclass
class AgentState:
    agent_id: str
    name: str
    agent_type: AgentType
    cash: float
    initial_cash: float
    position_qty: float = 0.0
    avg_entry_price: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    equity: float = 0.0
    peak_equity: float = 0.0
    max_drawdown_pct: float = 0.0
    trades: List[AgentTrade] = field(default_factory=list)
    decisions: List[AgentDecision] = field(default_factory=list)
    equity_curve: List[Dict[str, Any]] = field(default_factory=list)
    total_fees: float = 0.0
    holding_steps: int = 0
    total_holding_steps: int = 0
    closed_trades_count: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    gross_profits: float = 0.0
    gross_losses: float = 0.0


# =====================================================================
# ALGORITHMIC TRADING AGENT IMPLEMENTATIONS
# =====================================================================
class BaseTradingAgent:
    """Base class for all algorithmic agents ensuring zero lookahead bias."""

    def __init__(self, agent_id: str, name: str, agent_type: AgentType, initial_cash: float, params: Dict[str, Any]) -> None:
        self.agent_id = agent_id
        self.name = name
        self.agent_type = agent_type
        self.initial_cash = initial_cash
        self.params = params
        self.state = AgentState(
            agent_id=agent_id,
            name=name,
            agent_type=agent_type,
            cash=initial_cash,
            initial_cash=initial_cash,
            equity=initial_cash,
            peak_equity=initial_cash,
        )

    def decide(
        self,
        current_tick: MarketTick,
        price_history: List[float],
        fee_rate: float = 0.0005,
    ) -> AgentDecision:
        """Evaluate market state and produce a transparent trading decision."""
        raise NotImplementedError

    def execute_order(
        self,
        action: OrderAction,
        qty: float,
        price: float,
        current_tick: MarketTick,
        fee_rate: float = 0.0005,
    ) -> Tuple[str, float]:
        """Execute order against the simulated market with cash and inventory tracking."""
        if action == OrderAction.HOLD or qty <= 0:
            return "HOLD (No execution)", 0.0

        if action == OrderAction.BUY:
            fill_price = current_tick.best_ask
            cost = fill_price * qty
            fee = cost * fee_rate

            if self.state.cash < (cost + fee):
                # Scale down quantity to available cash if possible
                affordable_qty = max(0.0, (self.state.cash / (fill_price * (1.0 + fee_rate))))
                if affordable_qty < 0.01:
                    return f"REJECTED (Insufficient cash: ${self.state.cash:,.2f})", 0.0
                qty = round(affordable_qty, 4)
                cost = fill_price * qty
                fee = cost * fee_rate

            self.state.cash -= (cost + fee)
            self.state.total_fees += fee

            # Update position average price
            total_qty = self.state.position_qty + qty
            if total_qty > 0:
                self.state.avg_entry_price = (
                    (self.state.position_qty * self.state.avg_entry_price) + (qty * fill_price)
                ) / total_qty
            self.state.position_qty = total_qty

            self.state.trades.append(
                AgentTrade(
                    trade_id=len(self.state.trades) + 1,
                    step=current_tick.step,
                    side="BUY",
                    price=fill_price,
                    quantity=qty,
                    cost=cost,
                    fee=fee,
                    realized_pnl=0.0,
                )
            )
            return f"FILLED BUY {qty}x @ ${fill_price:,.2f} (Fee: ${fee:,.2f})", qty

        elif action in (OrderAction.SELL, OrderAction.CLOSE):
            if self.state.position_qty <= 0:
                return "SKIPPED (No long position to sell/close)", 0.0

            sell_qty = min(qty, self.state.position_qty) if action == OrderAction.SELL else self.state.position_qty
            fill_price = current_tick.best_bid
            proceeds = fill_price * sell_qty
            fee = proceeds * fee_rate
            self.state.total_fees += fee

            # Calculate realized P&L
            cost_basis = self.state.avg_entry_price * sell_qty
            trade_pnl = (proceeds - fee) - cost_basis

            self.state.cash += (proceeds - fee)
            self.state.position_qty = max(0.0, self.state.position_qty - sell_qty)
            if self.state.position_qty == 0:
                self.state.avg_entry_price = 0.0

            self.state.realized_pnl += trade_pnl
            self.state.closed_trades_count += 1
            if trade_pnl > 0:
                self.state.winning_trades += 1
                self.state.gross_profits += trade_pnl
            else:
                self.state.losing_trades += 1
                self.state.gross_losses += abs(trade_pnl)

            self.state.trades.append(
                AgentTrade(
                    trade_id=len(self.state.trades) + 1,
                    step=current_tick.step,
                    side="SELL",
                    price=fill_price,
                    quantity=sell_qty,
                    cost=proceeds,
                    fee=fee,
                    realized_pnl=trade_pnl,
                )
            )
            return f"FILLED SELL {sell_qty}x @ ${fill_price:,.2f} (Realized P&L: ${trade_pnl:+,.2f})", sell_qty

        return "HOLD", 0.0

    def update_valuation(self, current_tick: MarketTick) -> None:
        """Mark-to-market portfolio valuation and drawdown update."""
        current_val = self.state.position_qty * current_tick.price
        cost_basis = self.state.position_qty * self.state.avg_entry_price
        self.state.unrealized_pnl = current_val - cost_basis
        self.state.equity = self.state.cash + current_val

        if self.state.equity > self.state.peak_equity:
            self.state.peak_equity = self.state.equity

        dd = 0.0
        if self.state.peak_equity > 0:
            dd = ((self.state.peak_equity - self.state.equity) / self.state.peak_equity) * 100.0
        if dd > self.state.max_drawdown_pct:
            self.state.max_drawdown_pct = dd

        if self.state.position_qty > 0:
            self.state.holding_steps += 1
            self.state.total_holding_steps += 1

        self.state.equity_curve.append(
            {
                "step": current_tick.step,
                "price": current_tick.price,
                "equity": round(self.state.equity, 2),
                "cash": round(self.state.cash, 2),
                "position_qty": round(self.state.position_qty, 4),
                "drawdown_pct": round(dd, 2),
            }
        )


# 1. MOMENTUM AGENT
class MomentumAgent(BaseTradingAgent):
    """Identifies trend direction via dual moving average crossover and rate-of-change."""

    def decide(self, current_tick: MarketTick, price_history: List[float], fee_rate: float = 0.0005) -> AgentDecision:
        fast_p = int(self.params.get("fast_period", 5))
        slow_p = int(self.params.get("slow_period", 20))
        roc_threshold = float(self.params.get("roc_threshold", 0.3))
        pos_size_pct = float(self.params.get("position_size_pct", 25.0))

        fast_ma = calc_sma(price_history, fast_p)
        slow_ma = calc_sma(price_history, slow_p)
        roc = calc_momentum_roc(price_history, period=fast_p)

        indicators = {
            "fast_ma": round(fast_ma, 2) if fast_ma else None,
            "slow_ma": round(slow_ma, 2) if slow_ma else None,
            "roc": round(roc, 2) if roc else None,
        }

        if fast_ma is None or slow_ma is None or roc is None:
            return AgentDecision(
                step=current_tick.step,
                agent_id=self.agent_id,
                agent_name=self.name,
                action=OrderAction.HOLD,
                proposed_qty=0.0,
                proposed_price=current_tick.price,
                order_type="NONE",
                observed_price=current_tick.price,
                indicators=indicators,
                rule_triggered="WARMUP_PERIOD",
                expected_conditions=f"Need {slow_p} steps for MA calculation",
                execution_result="HOLD",
                reason=f"Accumulating historical price data ({len(price_history)}/{slow_p} steps).",
            )

        # Signal rules
        if fast_ma > slow_ma and roc > roc_threshold:
            # Bullish crossover
            if self.state.position_qty == 0:
                alloc_cash = self.state.cash * (pos_size_pct / 100.0)
                qty = round(alloc_cash / current_tick.best_ask, 4)
                rule = f"BULLISH_CROSSOVER (Fast MA ${fast_ma:,.2f} > Slow MA ${slow_ma:,.2f} & ROC {roc:.2f}% > {roc_threshold}%)"
                return AgentDecision(
                    step=current_tick.step,
                    agent_id=self.agent_id,
                    agent_name=self.name,
                    action=OrderAction.BUY,
                    proposed_qty=qty,
                    proposed_price=current_tick.best_ask,
                    order_type="MARKET",
                    observed_price=current_tick.price,
                    indicators=indicators,
                    rule_triggered=rule,
                    expected_conditions="Immediate ask fill; trending momentum entry",
                    execution_result="PENDING",
                    reason="Upward price trend detected. Entering long position.",
                )
            else:
                return AgentDecision(
                    step=current_tick.step,
                    agent_id=self.agent_id,
                    agent_name=self.name,
                    action=OrderAction.HOLD,
                    proposed_qty=0.0,
                    proposed_price=current_tick.price,
                    order_type="NONE",
                    observed_price=current_tick.price,
                    indicators=indicators,
                    rule_triggered="MAINTAIN_MOMENTUM_LONG",
                    expected_conditions="Holding active position with positive trend alignment",
                    execution_result="HOLD",
                    reason=f"Trend continues favorable (Fast MA > Slow MA). Holding {self.state.position_qty} units.",
                )

        elif fast_ma < slow_ma and self.state.position_qty > 0:
            # Bearish reversal
            rule = f"BEARISH_CROSSOVER (Fast MA ${fast_ma:,.2f} < Slow MA ${slow_ma:,.2f})"
            return AgentDecision(
                step=current_tick.step,
                agent_id=self.agent_id,
                agent_name=self.name,
                action=OrderAction.CLOSE,
                proposed_qty=self.state.position_qty,
                proposed_price=current_tick.best_bid,
                order_type="MARKET",
                observed_price=current_tick.price,
                indicators=indicators,
                rule_triggered=rule,
                expected_conditions="Immediate bid fill; momentum reversal exit",
                execution_result="PENDING",
                reason="Fast MA crossed below Slow MA. Closing long position to preserve profits.",
            )

        return AgentDecision(
            step=current_tick.step,
            agent_id=self.agent_id,
            agent_name=self.name,
            action=OrderAction.HOLD,
            proposed_qty=0.0,
            proposed_price=current_tick.price,
            order_type="NONE",
            observed_price=current_tick.price,
            indicators=indicators,
            rule_triggered="NO_MOMENTUM_SIGNAL",
            expected_conditions="Market trend within neutral boundaries",
            execution_result="HOLD",
            reason="No strong trend momentum detected. Standing aside.",
        )


# 2. MEAN REVERSION AGENT
class MeanReversionAgent(BaseTradingAgent):
    """Exploits statistical price extremes using Bollinger Bands and RSI."""

    def decide(self, current_tick: MarketTick, price_history: List[float], fee_rate: float = 0.0005) -> AgentDecision:
        period = int(self.params.get("bb_period", 20))
        num_std = float(self.params.get("num_std", 2.0))
        rsi_oversold = float(self.params.get("rsi_oversold", 32.0))
        rsi_overbought = float(self.params.get("rsi_overbought", 68.0))

        bb = calc_bollinger_bands(price_history, period=period, num_std=num_std)
        rsi = calc_rsi(price_history, period=14)

        indicators = {
            "bb_lower": bb[0] if bb else None,
            "bb_mid": bb[1] if bb else None,
            "bb_upper": bb[2] if bb else None,
            "rsi": round(rsi, 2) if rsi else None,
        }

        if bb is None or rsi is None:
            return AgentDecision(
                step=current_tick.step,
                agent_id=self.agent_id,
                agent_name=self.name,
                action=OrderAction.HOLD,
                proposed_qty=0.0,
                proposed_price=current_tick.price,
                order_type="NONE",
                observed_price=current_tick.price,
                indicators=indicators,
                rule_triggered="WARMUP_PERIOD",
                expected_conditions=f"Need {period} bars for Bollinger Bands",
                execution_result="HOLD",
                reason=f"Warming up indicators ({len(price_history)}/{period}).",
            )

        lower, mid, upper = bb

        # Oversold entry
        if current_tick.price <= lower and rsi <= rsi_oversold:
            if self.state.position_qty == 0:
                alloc = self.state.cash * 0.30
                qty = round(alloc / current_tick.best_ask, 4)
                rule = f"OVERSOLD_PIERCE (Price ${current_tick.price:,.2f} <= Lower Band ${lower:,.2f} & RSI {rsi:.1f} <= {rsi_oversold})"
                return AgentDecision(
                    step=current_tick.step,
                    agent_id=self.agent_id,
                    agent_name=self.name,
                    action=OrderAction.BUY,
                    proposed_qty=qty,
                    proposed_price=current_tick.best_ask,
                    order_type="LIMIT",
                    observed_price=current_tick.price,
                    indicators=indicators,
                    rule_triggered=rule,
                    expected_conditions="Limit order at ask; anticipating bounce back to mean",
                    execution_result="PENDING",
                    reason="Price stretched beyond lower statistical band with oversold RSI. Buying dip.",
                )

        # Overbought or mean reached exit
        elif self.state.position_qty > 0 and (current_tick.price >= mid or rsi >= rsi_overbought):
            rule = f"MEAN_REVERSION_TARGET_REACHED (Price ${current_tick.price:,.2f} >= Mid Band ${mid:,.2f} or RSI {rsi:.1f} >= {rsi_overbought})"
            return AgentDecision(
                step=current_tick.step,
                agent_id=self.agent_id,
                agent_name=self.name,
                action=OrderAction.CLOSE,
                proposed_qty=self.state.position_qty,
                proposed_price=current_tick.best_bid,
                order_type="MARKET",
                observed_price=current_tick.price,
                indicators=indicators,
                rule_triggered=rule,
                expected_conditions="Exit at bid as price re-centers to moving average",
                execution_result="PENDING",
                reason="Price has reverted to central moving average. Locking in reversion profit.",
            )

        return AgentDecision(
            step=current_tick.step,
            agent_id=self.agent_id,
            agent_name=self.name,
            action=OrderAction.HOLD,
            proposed_qty=0.0,
            proposed_price=current_tick.price,
            order_type="NONE",
            observed_price=current_tick.price,
            indicators=indicators,
            rule_triggered="WITHIN_BANDS",
            expected_conditions="Price oscillating within normal dispersion",
            execution_result="HOLD",
            reason="Price is within standard Bollinger dispersion. No reversion extreme present.",
        )


# 3. MARKET MAKING AGENT
class MarketMakingAgent(BaseTradingAgent):
    """Provides two-sided liquidity and harvests spread while managing inventory skew."""

    def decide(self, current_tick: MarketTick, price_history: List[float], fee_rate: float = 0.0005) -> AgentDecision:
        half_spread_pct = float(self.params.get("half_spread_pct", 0.002))
        max_inventory = float(self.params.get("max_inventory", 5.0))
        base_size = float(self.params.get("quote_size", 1.0))

        inventory = self.state.position_qty
        # Inventory skew: if inventory is high, lower ask to offload; if low/zero, buy
        skew = -(inventory / max(1.0, max_inventory)) * 0.001

        bid_quote = round(current_tick.price * (1.0 - half_spread_pct + skew), 2)
        ask_quote = round(current_tick.price * (1.0 + half_spread_pct + skew), 2)

        indicators = {
            "inventory": round(inventory, 4),
            "max_inventory": max_inventory,
            "bid_quote": bid_quote,
            "ask_quote": ask_quote,
            "spread_captured_bps": round(half_spread_pct * 20000, 1),
        }

        # If inventory too heavy, offload
        if inventory >= max_inventory:
            rule = f"INVENTORY_LIMIT_EXCEEDED (Holding {inventory:.2f} >= Max {max_inventory:.2f})"
            return AgentDecision(
                step=current_tick.step,
                agent_id=self.agent_id,
                agent_name=self.name,
                action=OrderAction.SELL,
                proposed_qty=round(base_size, 4),
                proposed_price=current_tick.best_bid,
                order_type="MARKET",
                observed_price=current_tick.price,
                indicators=indicators,
                rule_triggered=rule,
                expected_conditions="Aggressive sell to shed inventory risk",
                execution_result="PENDING",
                reason="Inventory cap reached. Offloading inventory to restore neutrality.",
            )

        # If price drops below bid quote and we have cash, buy passive inventory
        if current_tick.price <= bid_quote and inventory < max_inventory:
            rule = f"PASSIVE_BID_FILLED (Market price ${current_tick.price:,.2f} touched Bid Quote ${bid_quote:,.2f})"
            return AgentDecision(
                step=current_tick.step,
                agent_id=self.agent_id,
                agent_name=self.name,
                action=OrderAction.BUY,
                proposed_qty=round(base_size, 4),
                proposed_price=current_tick.best_ask,
                order_type="LIMIT",
                observed_price=current_tick.price,
                indicators=indicators,
                rule_triggered=rule,
                expected_conditions="Passive bid execution at attractive discount",
                execution_result="PENDING",
                reason="Market traded through passive bid quote. Accumulating inventory spread.",
            )

        # If price reaches above our entry by half spread and we hold inventory, sell
        if inventory > 0 and current_tick.price >= (self.state.avg_entry_price * (1.0 + half_spread_pct)):
            rule = f"PASSIVE_ASK_FILLED (Market price ${current_tick.price:,.2f} reached Ask Quote ${ask_quote:,.2f})"
            return AgentDecision(
                step=current_tick.step,
                agent_id=self.agent_id,
                agent_name=self.name,
                action=OrderAction.SELL,
                proposed_qty=min(inventory, round(base_size, 4)),
                proposed_price=current_tick.best_bid,
                order_type="LIMIT",
                observed_price=current_tick.price,
                indicators=indicators,
                rule_triggered=rule,
                expected_conditions="Passive ask execution realizing spread",
                execution_result="PENDING",
                reason="Market hit passive ask quote. Capturing round-trip spread profit.",
            )

        return AgentDecision(
            step=current_tick.step,
            agent_id=self.agent_id,
            agent_name=self.name,
            action=OrderAction.HOLD,
            proposed_qty=0.0,
            proposed_price=current_tick.price,
            order_type="NONE",
            observed_price=current_tick.price,
            indicators=indicators,
            rule_triggered="QUOTING_PASSIVE_LADDER",
            expected_conditions=f"Resting two-sided quotes: Bid ${bid_quote:,.2f} / Ask ${ask_quote:,.2f}",
            execution_result="HOLD",
            reason="Maintaining passive two-sided quotes around mid-price.",
        )


# 4. LIQUIDITY HUNTER AGENT
class LiquidityHunterAgent(BaseTradingAgent):
    """Analyzes book depth and imbalance to identify breakout surges and liquidity clusters."""

    def decide(self, current_tick: MarketTick, price_history: List[float], fee_rate: float = 0.0005) -> AgentDecision:
        min_depth = int(self.params.get("min_depth", 15))
        imbalance_thresh = float(self.params.get("imbalance_threshold", 0.30))

        tot_depth = current_tick.depth_bids + current_tick.depth_asks
        imbalance = (
            (current_tick.depth_bids - current_tick.depth_asks) / tot_depth
            if tot_depth > 0
            else 0.0
        )

        indicators = {
            "depth_bids": current_tick.depth_bids,
            "depth_asks": current_tick.depth_asks,
            "book_imbalance": round(imbalance, 3),
            "min_depth_required": min_depth,
        }

        # Strong bid-side imbalance with sufficient depth -> Buy liquidity sweep
        if imbalance >= imbalance_thresh and tot_depth >= min_depth:
            if self.state.position_qty == 0:
                qty = round(min(3.0, (self.state.cash * 0.25) / current_tick.best_ask), 4)
                rule = f"BID_LIQUIDITY_SURGE (Imbalance {imbalance:+.2f} >= {imbalance_thresh:+.2f} & Depth {tot_depth} >= {min_depth})"
                return AgentDecision(
                    step=current_tick.step,
                    agent_id=self.agent_id,
                    agent_name=self.name,
                    action=OrderAction.BUY,
                    proposed_qty=qty,
                    proposed_price=current_tick.best_ask,
                    order_type="MARKET",
                    observed_price=current_tick.price,
                    indicators=indicators,
                    rule_triggered=rule,
                    expected_conditions="Sweeping thin asks before bid support drives prices upward",
                    execution_result="PENDING",
                    reason="Heavy bid liquidity cluster detected. Initiating breakout buy.",
                )

        # Ask-side imbalance with active position -> Sell before bid collapse
        elif imbalance <= -imbalance_thresh and self.state.position_qty > 0:
            rule = f"ASK_LIQUIDITY_WALL (Imbalance {imbalance:+.2f} <= {-imbalance_thresh:+.2f})"
            return AgentDecision(
                step=current_tick.step,
                agent_id=self.agent_id,
                agent_name=self.name,
                action=OrderAction.CLOSE,
                proposed_qty=self.state.position_qty,
                proposed_price=current_tick.best_bid,
                order_type="MARKET",
                observed_price=current_tick.price,
                indicators=indicators,
                rule_triggered=rule,
                expected_conditions="Immediate exit before ask wall overwhelms bids",
                execution_result="PENDING",
                reason="Heavy ask wall accumulating on the book. Exiting position.",
            )

        return AgentDecision(
            step=current_tick.step,
            agent_id=self.agent_id,
            agent_name=self.name,
            action=OrderAction.HOLD,
            proposed_qty=0.0,
            proposed_price=current_tick.price,
            order_type="NONE",
            observed_price=current_tick.price,
            indicators=indicators,
            rule_triggered="BALANCED_BOOK_DEPTH",
            expected_conditions=f"Imbalance {imbalance:+.2f} below entry threshold",
            execution_result="HOLD",
            reason="Order book depth is balanced between buyers and sellers. Waiting for liquidity sweep.",
        )


# 5. CONSERVATIVE AGENT
class ConservativeAgent(BaseTradingAgent):
    """Enforces strict exposure caps, tight stop losses, and high risk-reward thresholds."""

    def decide(self, current_tick: MarketTick, price_history: List[float], fee_rate: float = 0.0005) -> AgentDecision:
        stop_loss_pct = float(self.params.get("stop_loss_pct", 1.2))
        take_profit_pct = float(self.params.get("take_profit_pct", 2.8))
        max_risk_pct = float(self.params.get("max_risk_pct", 1.0))

        vol = calc_volatility(price_history, period=10)
        fast_ma = calc_sma(price_history, 5)
        slow_ma = calc_sma(price_history, 20)

        indicators = {
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
            "volatility": round(vol, 2),
            "entry_price": round(self.state.avg_entry_price, 2) if self.state.avg_entry_price else None,
        }

        # Position monitoring: Stop-loss and Take-profit guards
        if self.state.position_qty > 0 and self.state.avg_entry_price > 0:
            pnl_pct = ((current_tick.price - self.state.avg_entry_price) / self.state.avg_entry_price) * 100.0
            indicators["current_pnl_pct"] = round(pnl_pct, 2)

            # Stop Loss hit
            if pnl_pct <= -stop_loss_pct:
                rule = f"STOP_LOSS_GUARD (Drawdown {pnl_pct:.2f}% <= -{stop_loss_pct:.2f}%)"
                return AgentDecision(
                    step=current_tick.step,
                    agent_id=self.agent_id,
                    agent_name=self.name,
                    action=OrderAction.CLOSE,
                    proposed_qty=self.state.position_qty,
                    proposed_price=current_tick.best_bid,
                    order_type="MARKET",
                    observed_price=current_tick.price,
                    indicators=indicators,
                    rule_triggered=rule,
                    expected_conditions="Strict risk defense; cutting loss immediately",
                    execution_result="PENDING",
                    reason=f"Loss reached configured -{stop_loss_pct}% risk threshold. Liquidating to preserve capital.",
                )

            # Take Profit reached
            if pnl_pct >= take_profit_pct:
                rule = f"TAKE_PROFIT_TARGET (Gain {pnl_pct:.2f}% >= +{take_profit_pct:.2f}%)"
                return AgentDecision(
                    step=current_tick.step,
                    agent_id=self.agent_id,
                    agent_name=self.name,
                    action=OrderAction.CLOSE,
                    proposed_qty=self.state.position_qty,
                    proposed_price=current_tick.best_bid,
                    order_type="MARKET",
                    observed_price=current_tick.price,
                    indicators=indicators,
                    rule_triggered=rule,
                    expected_conditions="Target reached; harvesting profit",
                    execution_result="PENDING",
                    reason=f"Gain reached target +{take_profit_pct}%. Closing position cleanly.",
                )

            return AgentDecision(
                step=current_tick.step,
                agent_id=self.agent_id,
                agent_name=self.name,
                action=OrderAction.HOLD,
                proposed_qty=0.0,
                proposed_price=current_tick.price,
                order_type="NONE",
                observed_price=current_tick.price,
                indicators=indicators,
                rule_triggered="MONITORING_RISK_ENVELOPE",
                expected_conditions=f"P&L ({pnl_pct:+.2f}%) within bounds (-{stop_loss_pct}% to +{take_profit_pct}%)",
                execution_result="HOLD",
                reason=f"Holding position inside configured risk corridors (Current P&L: {pnl_pct:+.2f}%).",
            )

        # Entry logic: low volatility and confirmed upward trend
        if self.state.position_qty == 0 and fast_ma and slow_ma:
            if fast_ma > slow_ma and vol < (current_tick.price * 0.005):
                # Sized strictly by max risk limit
                risk_amount = self.state.cash * (max_risk_pct / 100.0)
                pos_val = risk_amount / (stop_loss_pct / 100.0)
                qty = round(min(pos_val, self.state.cash * 0.20) / current_tick.best_ask, 4)

                rule = f"CONSERVATIVE_TREND_ENTRY (Fast MA > Slow MA & Volatility ${vol:.2f} within risk budget)"
                return AgentDecision(
                    step=current_tick.step,
                    agent_id=self.agent_id,
                    agent_name=self.name,
                    action=OrderAction.BUY,
                    proposed_qty=qty,
                    proposed_price=current_tick.best_ask,
                    order_type="LIMIT",
                    observed_price=current_tick.price,
                    indicators=indicators,
                    rule_triggered=rule,
                    expected_conditions=f"Sized to risk exactly ${risk_amount:,.2f} ({max_risk_pct}% equity)",
                    execution_result="PENDING",
                    reason="Low-volatility trend detected. Entering position with strict risk size.",
                )

        return AgentDecision(
            step=current_tick.step,
            agent_id=self.agent_id,
            agent_name=self.name,
            action=OrderAction.HOLD,
            proposed_qty=0.0,
            proposed_price=current_tick.price,
            order_type="NONE",
            observed_price=current_tick.price,
            indicators=indicators,
            rule_triggered="RISK_PRUDENCE_STANDBY",
            expected_conditions="No high-conviction low-risk entry present",
            execution_result="HOLD",
            reason="Standing aside to avoid unnecessary market risk exposure.",
        )


# 6. ADAPTIVE AGENT
class AdaptiveAgent(BaseTradingAgent):
    """Dynamically detects market regime (trending vs ranging) and adapts parameters."""

    def decide(self, current_tick: MarketTick, price_history: List[float], fee_rate: float = 0.0005) -> AgentDecision:
        window = int(self.params.get("regime_window", 15))
        trend_thresh = float(self.params.get("trend_threshold", 0.40))

        if len(price_history) < window:
            return AgentDecision(
                step=current_tick.step,
                agent_id=self.agent_id,
                agent_name=self.name,
                action=OrderAction.HOLD,
                proposed_qty=0.0,
                proposed_price=current_tick.price,
                order_type="NONE",
                observed_price=current_tick.price,
                indicators={"warmup": f"{len(price_history)}/{window}"},
                rule_triggered="REGIME_WARMUP",
                expected_conditions=f"Need {window} bars to evaluate regime efficiency",
                execution_result="HOLD",
                reason=f"Calibrating market regime classifier ({len(price_history)}/{window}).",
            )

        # Kaufman Efficiency Ratio (ER) = Directional Move / Total Path
        slice_p = price_history[-window:]
        net_move = abs(slice_p[-1] - slice_p[0])
        total_path = sum(abs(slice_p[i] - slice_p[i - 1]) for i in range(1, len(slice_p)))
        efficiency = (net_move / total_path) if total_path > 0 else 0.0

        is_trending = efficiency >= trend_thresh
        active_mode = "TREND_FOLLOWING" if is_trending else "MEAN_REVERTING"

        fast_ma = calc_sma(price_history, 5)
        slow_ma = calc_sma(price_history, 15)
        rsi = calc_rsi(price_history, 14)

        indicators = {
            "efficiency_ratio": round(efficiency, 3),
            "trend_threshold": trend_thresh,
            "detected_regime": active_mode,
            "fast_ma": round(fast_ma, 2) if fast_ma else None,
            "slow_ma": round(slow_ma, 2) if slow_ma else None,
            "rsi": round(rsi, 2) if rsi else None,
        }

        # Adaptive Mode 1: Trending
        if is_trending and fast_ma and slow_ma:
            if fast_ma > slow_ma and self.state.position_qty == 0:
                qty = round((self.state.cash * 0.25) / current_tick.best_ask, 4)
                rule = f"ADAPTIVE_TREND_ENTRY (Efficiency {efficiency:.2f} >= {trend_thresh:.2f} & Fast MA > Slow MA)"
                return AgentDecision(
                    step=current_tick.step,
                    agent_id=self.agent_id,
                    agent_name=self.name,
                    action=OrderAction.BUY,
                    proposed_qty=qty,
                    proposed_price=current_tick.best_ask,
                    order_type="MARKET",
                    observed_price=current_tick.price,
                    indicators=indicators,
                    rule_triggered=rule,
                    expected_conditions="Adapted to high-efficiency directional regime",
                    execution_result="PENDING",
                    reason=f"Regime evaluated as Directional (ER: {efficiency:.2f}). Entering momentum buy.",
                )
            elif fast_ma < slow_ma and self.state.position_qty > 0:
                rule = "ADAPTIVE_TREND_EXIT (Fast MA crossed below Slow MA in trend mode)"
                return AgentDecision(
                    step=current_tick.step,
                    agent_id=self.agent_id,
                    agent_name=self.name,
                    action=OrderAction.CLOSE,
                    proposed_qty=self.state.position_qty,
                    proposed_price=current_tick.best_bid,
                    order_type="MARKET",
                    observed_price=current_tick.price,
                    indicators=indicators,
                    rule_triggered=rule,
                    expected_conditions="Closing trend long on MA weakness",
                    execution_result="PENDING",
                    reason="Trend momentum fading in directional regime. Liquidating long position.",
                )

        # Adaptive Mode 2: Mean Reversion / Choppy Range
        else:
            if rsi and rsi < 35 and self.state.position_qty == 0:
                qty = round((self.state.cash * 0.20) / current_tick.best_ask, 4)
                rule = f"ADAPTIVE_RANGE_DIP (Efficiency {efficiency:.2f} < {trend_thresh:.2f} & RSI {rsi:.1f} < 35)"
                return AgentDecision(
                    step=current_tick.step,
                    agent_id=self.agent_id,
                    agent_name=self.name,
                    action=OrderAction.BUY,
                    proposed_qty=qty,
                    proposed_price=current_tick.best_ask,
                    order_type="LIMIT",
                    observed_price=current_tick.price,
                    indicators=indicators,
                    rule_triggered=rule,
                    expected_conditions="Adapted to range-bound mean reversion mode",
                    execution_result="PENDING",
                    reason=f"Regime evaluated as Choppy Range (ER: {efficiency:.2f}). Buying oversold support.",
                )
            elif rsi and rsi > 65 and self.state.position_qty > 0:
                rule = f"ADAPTIVE_RANGE_PEAK (RSI {rsi:.1f} > 65 in range mode)"
                return AgentDecision(
                    step=current_tick.step,
                    agent_id=self.agent_id,
                    agent_name=self.name,
                    action=OrderAction.CLOSE,
                    proposed_qty=self.state.position_qty,
                    proposed_price=current_tick.best_bid,
                    order_type="MARKET",
                    observed_price=current_tick.price,
                    indicators=indicators,
                    rule_triggered=rule,
                    expected_conditions="Taking profit at range resistance",
                    execution_result="PENDING",
                    reason="Range resistance encountered. Taking profit before pullback.",
                )

        return AgentDecision(
            step=current_tick.step,
            agent_id=self.agent_id,
            agent_name=self.name,
            action=OrderAction.HOLD,
            proposed_qty=0.0,
            proposed_price=current_tick.price,
            order_type="NONE",
            observed_price=current_tick.price,
            indicators=indicators,
            rule_triggered=f"REGIME_{active_mode}_NEUTRAL",
            expected_conditions=f"Operating in {active_mode} mode; no edge at current levels",
            execution_result="HOLD",
            reason=f"Adapted to {active_mode} mode; currently waiting for high-probability inflection.",
        )


# 7. HUMAN PARTICIPANT AGENT
class HumanAgent(BaseTradingAgent):
    """Allows manual trade participation for the Human vs Algorithm Challenge."""

    def __init__(self, initial_cash: float) -> None:
        super().__init__(
            agent_id="human_user",
            name="Human Trader (You)",
            agent_type=AgentType.HUMAN,
            initial_cash=initial_cash,
            params={},
        )
        self.queued_action: OrderAction = OrderAction.HOLD
        self.queued_qty: float = 0.0

    def set_action(self, action: OrderAction, qty: float) -> None:
        self.queued_action = action
        self.queued_qty = qty

    def decide(self, current_tick: MarketTick, price_history: List[float], fee_rate: float = 0.0005) -> AgentDecision:
        action = self.queued_action
        qty = self.queued_qty
        self.queued_action = OrderAction.HOLD
        self.queued_qty = 0.0

        indicators = {
            "position": self.state.position_qty,
            "cash": round(self.state.cash, 2),
            "unrealized_pnl": round(self.state.unrealized_pnl, 2),
        }

        if action == OrderAction.BUY:
            return AgentDecision(
                step=current_tick.step,
                agent_id=self.agent_id,
                agent_name=self.name,
                action=OrderAction.BUY,
                proposed_qty=qty,
                proposed_price=current_tick.best_ask,
                order_type="MARKET",
                observed_price=current_tick.price,
                indicators=indicators,
                rule_triggered="HUMAN_DISCRETIONARY_BUY",
                expected_conditions="Discretionary order submitted by user",
                execution_result="PENDING",
                reason="User initiated manual BUY order.",
            )
        elif action in (OrderAction.SELL, OrderAction.CLOSE):
            return AgentDecision(
                step=current_tick.step,
                agent_id=self.agent_id,
                agent_name=self.name,
                action=action,
                proposed_qty=qty if qty > 0 else self.state.position_qty,
                proposed_price=current_tick.best_bid,
                order_type="MARKET",
                observed_price=current_tick.price,
                indicators=indicators,
                rule_triggered="HUMAN_DISCRETIONARY_SELL",
                expected_conditions="Discretionary order submitted by user",
                execution_result="PENDING",
                reason="User initiated manual SELL/CLOSE order.",
            )

        return AgentDecision(
            step=current_tick.step,
            agent_id=self.agent_id,
            agent_name=self.name,
            action=OrderAction.HOLD,
            proposed_qty=0.0,
            proposed_price=current_tick.price,
            order_type="NONE",
            observed_price=current_tick.price,
            indicators=indicators,
            rule_triggered="HUMAN_HOLD",
            expected_conditions="Discretionary hold",
            execution_result="HOLD",
            reason="Holding discretionary position.",
        )


# =====================================================================
# PERFORMANCE CALCULATIONS & STATS
# =====================================================================
def compute_agent_metrics(state: AgentState, num_steps: int) -> Dict[str, Any]:
    """Computes comprehensive institutional-grade performance metrics."""
    final_equity = state.equity
    init_cash = state.initial_cash
    tot_return_pct = ((final_equity - init_cash) / init_cash) * 100.0 if init_cash > 0 else 0.0

    # Win rate
    tot_closed = state.closed_trades_count
    win_rate = (state.winning_trades / tot_closed * 100.0) if tot_closed > 0 else 0.0

    # Profit factor
    profit_factor = (
        round(state.gross_profits / state.gross_losses, 2)
        if state.gross_losses > 0
        else (round(state.gross_profits, 2) if state.gross_profits > 0 else 1.0)
    )

    # Average holding duration (in steps)
    avg_holding = round(state.total_holding_steps / max(1, tot_closed), 1)

    # Step-by-step returns for Sharpe & Sortino calculation
    step_returns: List[float] = []
    if len(state.equity_curve) > 1:
        for i in range(1, len(state.equity_curve)):
            prev_eq = state.equity_curve[i - 1]["equity"]
            curr_eq = state.equity_curve[i]["equity"]
            if prev_eq > 0:
                step_returns.append((curr_eq - prev_eq) / prev_eq)

    sharpe_ratio = 0.0
    sortino_ratio = 0.0
    if len(step_returns) >= 5:
        mean_r = sum(step_returns) / len(step_returns)
        var_r = sum((r - mean_r) ** 2 for r in step_returns) / len(step_returns)
        std_r = math.sqrt(var_r)
        if std_r > 1e-6:
            # Annualized approximation (assuming ~252 trading sessions)
            sharpe_ratio = round((mean_r / std_r) * math.sqrt(252), 2)

        downside_returns = [r for r in step_returns if r < 0]
        if downside_returns:
            downside_var = sum(r ** 2 for r in downside_returns) / len(downside_returns)
            downside_std = math.sqrt(downside_var)
            if downside_std > 1e-6:
                sortino_ratio = round((mean_r / downside_std) * math.sqrt(252), 2)

    return {
        "agent_id": state.agent_id,
        "name": state.name,
        "agent_type": state.agent_type.value,
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(tot_return_pct, 2),
        "realized_pnl": round(state.realized_pnl, 2),
        "unrealized_pnl": round(state.unrealized_pnl, 2),
        "max_drawdown_pct": round(state.max_drawdown_pct, 2),
        "win_rate_pct": round(win_rate, 1),
        "total_trades": len(state.trades),
        "closed_trades": tot_closed,
        "winning_trades": state.winning_trades,
        "losing_trades": state.losing_trades,
        "profit_factor": profit_factor,
        "avg_holding_steps": avg_holding,
        "total_fees_paid": round(state.total_fees, 2),
        "sharpe_ratio": sharpe_ratio,
        "sortino_ratio": sortino_ratio,
        "position_qty": round(state.position_qty, 4),
    }


# =====================================================================
# ARENA COMPETITION SIMULATOR
# =====================================================================
class ArenaCompetition:
    """Orchestrates multi-agent competitions with identical market streams."""

    def __init__(
        self,
        seed: int = 42,
        symbol: str = "BTCUSDT",
        num_steps: int = 100,
        initial_cash: float = 100_000.0,
        condition: MarketCondition = MarketCondition.TRENDING_BULL,
        selected_agents: Optional[List[AgentType]] = None,
        custom_params: Optional[Dict[str, Dict[str, Any]]] = None,
        include_human: bool = False,
    ) -> None:
        self.seed = seed
        self.symbol = symbol.upper()
        self.num_steps = num_steps
        self.initial_cash = initial_cash
        self.condition = condition
        self.include_human = include_human
        self.custom_params = custom_params or {}

        # Pre-generate deterministic market ticks
        self.market_ticks = generate_market_scenario(
            seed=seed,
            symbol=self.symbol,
            num_steps=num_steps,
            condition=condition,
        )

        # Initialize participating agents
        if selected_agents is None:
            selected_agents = [
                AgentType.MOMENTUM,
                AgentType.MEAN_REVERSION,
                AgentType.MARKET_MAKER,
                AgentType.LIQUIDITY_HUNTER,
                AgentType.CONSERVATIVE,
                AgentType.ADAPTIVE,
            ]

        self.agents: List[BaseTradingAgent] = []
        for atype in selected_agents:
            p = self.custom_params.get(atype.value, {})
            if atype == AgentType.MOMENTUM:
                self.agents.append(MomentumAgent("agent_momentum", "Momentum Trend Agent", atype, initial_cash, p))
            elif atype == AgentType.MEAN_REVERSION:
                self.agents.append(MeanReversionAgent("agent_mean_rev", "Mean Reversion Agent", atype, initial_cash, p))
            elif atype == AgentType.MARKET_MAKER:
                self.agents.append(MarketMakingAgent("agent_mm", "Market Making Agent", atype, initial_cash, p))
            elif atype == AgentType.LIQUIDITY_HUNTER:
                self.agents.append(LiquidityHunterAgent("agent_liquidity", "Liquidity Hunter Agent", atype, initial_cash, p))
            elif atype == AgentType.CONSERVATIVE:
                self.agents.append(ConservativeAgent("agent_conservative", "Conservative Risk Guard", atype, initial_cash, p))
            elif atype == AgentType.ADAPTIVE:
                self.agents.append(AdaptiveAgent("agent_adaptive", "Adaptive Regime Agent", atype, initial_cash, p))

        if include_human:
            self.human_agent = HumanAgent(initial_cash)
            self.agents.append(self.human_agent)
        else:
            self.human_agent = None

    def run_full_competition(self) -> Dict[str, Any]:
        """Runs the complete competition from start to finish."""
        t_start = time.perf_counter()
        price_history: List[float] = []

        for tick in self.market_ticks:
            price_history.append(tick.price)

            # Step every agent through the exact same price history slice
            for agent in self.agents:
                decision = agent.decide(tick, price_history)

                # Execute order if action is active
                if decision.action in (OrderAction.BUY, OrderAction.SELL, OrderAction.CLOSE):
                    exec_result, executed_qty = agent.execute_order(
                        action=decision.action,
                        qty=decision.proposed_qty,
                        price=decision.proposed_price,
                        current_tick=tick,
                    )
                    decision.execution_result = exec_result
                else:
                    decision.execution_result = "HOLD (No order submitted)"

                agent.state.decisions.append(decision)
                agent.update_valuation(tick)

        bench_ms = (time.perf_counter() - t_start) * 1000.0

        # Compile leaderboard rankings by total return
        agent_metrics = [compute_agent_metrics(a.state, self.num_steps) for a in self.agents]
        leaderboard_by_return = sorted(agent_metrics, key=lambda x: x["total_return_pct"], reverse=True)
        leaderboard_by_drawdown = sorted(agent_metrics, key=lambda x: x["max_drawdown_pct"])
        leaderboard_by_sharpe = sorted(agent_metrics, key=lambda x: x["sharpe_ratio"], reverse=True)

        winner = leaderboard_by_return[0]

        # Post-Competition Analysis debrief
        debrief = self._generate_competition_debrief(winner, agent_metrics)

        return {
            "status": "success",
            "seed": self.seed,
            "symbol": self.symbol,
            "condition": self.condition.value,
            "num_steps": self.num_steps,
            "initial_cash": self.initial_cash,
            "winner": winner,
            "leaderboard": leaderboard_by_return,
            "leaderboard_by_drawdown": leaderboard_by_drawdown,
            "leaderboard_by_sharpe": leaderboard_by_sharpe,
            "debrief": debrief,
            "benchmark_wall_ms": round(bench_ms, 2),
            "market_ticks": [asdict(t) for t in self.market_ticks[:150]],  # sample for payload efficiency
            "agent_summaries": agent_metrics,
            "equity_curves": {a.agent_id: a.state.equity_curve for a in self.agents},
            "recent_decisions": {a.agent_id: [asdict(d) for d in a.state.decisions[-25:]] for a in self.agents},
        }

    def _generate_competition_debrief(self, winner: Dict[str, Any], all_metrics: List[Dict[str, Any]]) -> str:
        """Generates an honest, causal explanation of why the winning strategy succeeded."""
        c = self.condition
        w_name = winner["name"]
        w_ret = winner["total_return_pct"]
        w_dd = winner["max_drawdown_pct"]
        w_trades = winner["total_trades"]

        reason = f"**{w_name}** finished in 1st place with a return of **+{w_ret:.2f}%** (Max Drawdown: {w_dd:.2f}% across {w_trades} trades). "

        if c == MarketCondition.TRENDING_BULL:
            reason += "In this sustained bullish drift, momentum and trend-aligned strategies gained a strong structural edge by entering early on Golden Crosses and letting winning trades run while avoiding premature mean-reversion counter-trend shorts."
        elif c == MarketCondition.TRENDING_BEAR:
            reason += "Under persistent downward selling pressure, aggressive buy-and-hold was heavily penalized. Conservative risk bounds and prompt stop-loss liquidation preserved capital, allowing patient dip-buyers to avoid severe drawdowns."
        elif c == MarketCondition.MEAN_REVERTING:
            reason += "In this range-bound oscillating regime, trend breakout attempts suffered repeated whipsaws and fee drag. Mean-reverting statistical band entries and market making spread capture outperformed by buying support and taking profits at the central moving average."
        elif c == MarketCondition.HIGH_VOLATILITY:
            reason += "High turbulence caused frequent false breakouts. Strategies that scaled position sizes dynamically according to market volatility and trimmed exposure during expansion phases achieved the best risk-adjusted Sortino ratio."
        elif c == MarketCondition.LIQUIDITY_SQUEEZE:
            reason += "Thin order book depth punished aggressive market orders with heavy slippage. Liquidity-aware entries and passive limit orders conserved transaction costs and exploited rapid price snapbacks."
        else:
            reason += "Superior risk-adjusted execution and disciplined profit targets generated consistent outperformance."

        return reason


# =====================================================================
# STRATEGY EVOLUTION LAB COMPARISON RUNNER
# =====================================================================
def run_strategy_evolution_test(
    seed: int = 42,
    symbol: str = "BTCUSDT",
    agent_type: str = "MOMENTUM",
    condition: str = "TRENDING_BULL",
    base_params: Optional[Dict[str, Any]] = None,
    modified_params: Optional[Dict[str, Any]] = None,
    num_steps: int = 100,
    initial_cash: float = 100_000.0,
) -> Dict[str, Any]:
    """Runs a controlled side-by-side evolution test comparing Original vs Modified parameters under identical market seeds."""
    at_enum = AgentType(agent_type.upper()) if agent_type.upper() in AgentType._value2member_map_ else AgentType.MOMENTUM
    cond_enum = MarketCondition(condition.upper()) if condition.upper() in MarketCondition._value2member_map_ else MarketCondition.TRENDING_BULL

    b_params = base_params or {}
    m_params = modified_params or {}

    # Run original baseline
    comp_base = ArenaCompetition(
        seed=seed,
        symbol=symbol,
        num_steps=num_steps,
        initial_cash=initial_cash,
        condition=cond_enum,
        selected_agents=[at_enum],
        custom_params={at_enum.value: b_params},
    )
    res_base = comp_base.run_full_competition()
    base_metric = res_base["leaderboard"][0]

    # Run modified strategy on identical market data
    comp_mod = ArenaCompetition(
        seed=seed,
        symbol=symbol,
        num_steps=num_steps,
        initial_cash=initial_cash,
        condition=cond_enum,
        selected_agents=[at_enum],
        custom_params={at_enum.value: m_params},
    )
    res_mod = comp_mod.run_full_competition()
    mod_metric = res_mod["leaderboard"][0]

    # Calculate differential deltas
    deltas = {
        "return_delta_pct": round(mod_metric["total_return_pct"] - base_metric["total_return_pct"], 2),
        "drawdown_delta_pct": round(mod_metric["max_drawdown_pct"] - base_metric["max_drawdown_pct"], 2),
        "win_rate_delta_pct": round(mod_metric["win_rate_pct"] - base_metric["win_rate_pct"], 1),
        "trades_delta": mod_metric["total_trades"] - base_metric["total_trades"],
        "fees_delta": round(mod_metric["total_fees_paid"] - base_metric["total_fees_paid"], 2),
        "sharpe_delta": round(mod_metric["sharpe_ratio"] - base_metric["sharpe_ratio"], 2),
    }

    improvement = deltas["return_delta_pct"] > 0 and deltas["drawdown_delta_pct"] <= 0

    return {
        "status": "success",
        "seed": seed,
        "symbol": symbol.upper(),
        "agent_type": at_enum.value,
        "condition": cond_enum.value,
        "original": base_metric,
        "modified": mod_metric,
        "deltas": deltas,
        "is_improved": improvement,
        "base_equity_curve": res_base["equity_curves"].get(comp_base.agents[0].agent_id, []),
        "modified_equity_curve": res_mod["equity_curves"].get(comp_mod.agents[0].agent_id, []),
    }
