"""Risk Management, Position Sizing, and Strategy Backtesting Engine for ChronosMatch.

Provides pure mathematical calculations for:
- Position sizing based on capital and fixed risk percentage (e.g. 2% rule)
- Risk-to-reward (R:R) ratio and fee-adjusted break-even prices
- Sequential bar-by-bar strategy backtesting without lookahead bias
- Performance metrics: CAGR, Max Drawdown, Win Rate, Profit Factor, Exposure
- Hypothetical portfolio scenario stress testing
"""

import math
from typing import Any, Dict, List, Optional, Tuple


def calculate_position_size(
    account_balance: float,
    entry_price: float,
    stop_loss_price: float,
    risk_pct: float = 2.0,
    target_price: Optional[float] = None,
    fee_pct: float = 0.05,
) -> Dict[str, Any]:
    """Calculate recommended position size, maximum loss, profit target, and risk-reward metrics.

    Args:
        account_balance: Total equity or available virtual cash in INR.
        entry_price: Planned entry price per share/unit.
        stop_loss_price: Price level where position will be exited to limit loss.
        risk_pct: Percentage of account balance to risk on this trade (e.g. 2.0 for 2%).
        target_price: Planned take-profit price level.
        fee_pct: Estimated one-way transaction fee as percentage (e.g. 0.05%).

    Returns:
        Dictionary containing position sizing, risk, return, and break-even metrics.
    """
    if account_balance <= 0:
        raise ValueError("Account balance must be greater than zero.")
    if entry_price <= 0:
        raise ValueError("Entry price must be greater than zero.")
    if stop_loss_price <= 0:
        raise ValueError("Stop loss price must be greater than zero.")
    if risk_pct <= 0 or risk_pct > 100:
        raise ValueError("Risk percentage must be between 0.01% and 100%.")

    is_long = entry_price >= stop_loss_price
    price_risk_per_unit = abs(entry_price - stop_loss_price)

    if price_risk_per_unit <= 0.0001:
        raise ValueError("Entry price and stop-loss price cannot be identical.")

    # Maximum monetary risk allocated based on percentage of balance
    max_risk_amount = round(account_balance * (risk_pct / 100.0), 2)

    # Position size = (Risk Amount) / (Price Distance + Estimated Roundtrip Fee Distance)
    # Roundtrip fee factor: 2 * fee_pct / 100
    fee_factor = 2 * (fee_pct / 100.0)
    effective_risk_per_unit = price_risk_per_unit + (entry_price * fee_factor)

    raw_shares = max_risk_amount / effective_risk_per_unit
    shares = math.floor(raw_shares) if raw_shares >= 1.0 else round(raw_shares, 4)

    # Guard against 0 shares when balance is very small
    if shares <= 0:
        shares = 1.0 if account_balance >= entry_price else 0.0

    total_position_value = round(shares * entry_price, 2)
    estimated_entry_fee = round(total_position_value * (fee_pct / 100.0), 2)
    estimated_exit_fee = round((shares * stop_loss_price) * (fee_pct / 100.0), 2)
    total_estimated_fees = round(estimated_entry_fee + estimated_exit_fee, 2)

    # Maximum actual loss if stop loss is hit
    max_loss_inr = round((shares * price_risk_per_unit) + total_estimated_fees, 2)
    loss_pct_of_account = round((max_loss_inr / account_balance) * 100.0, 2)

    # Potential profit and Risk-to-Reward
    potential_profit_inr = 0.0
    risk_reward_ratio = 0.0
    if target_price and target_price > 0:
        profit_distance = abs(target_price - entry_price)
        target_exit_fee = round((shares * target_price) * (fee_pct / 100.0), 2)
        potential_profit_inr = round((shares * profit_distance) - (estimated_entry_fee + target_exit_fee), 2)
        if max_loss_inr > 0:
            risk_reward_ratio = round(potential_profit_inr / max_loss_inr, 2)

    # Break-even price calculation after roundtrip fees
    if is_long:
        breakeven_price = round(entry_price * (1.0 + fee_factor), 2)
    else:
        breakeven_price = round(entry_price * (1.0 - fee_factor), 2)

    portfolio_exposure_pct = round((total_position_value / account_balance) * 100.0, 2)

    return {
        "account_balance": account_balance,
        "entry_price": entry_price,
        "stop_loss_price": stop_loss_price,
        "target_price": target_price,
        "risk_pct_configured": risk_pct,
        "recommended_shares": shares,
        "total_position_value": total_position_value,
        "max_risk_budget_inr": max_risk_amount,
        "max_loss_inr": max_loss_inr,
        "loss_pct_of_account": loss_pct_of_account,
        "potential_profit_inr": potential_profit_inr,
        "risk_reward_ratio": risk_reward_ratio,
        "breakeven_price": breakeven_price,
        "total_estimated_fees": total_estimated_fees,
        "portfolio_exposure_pct": portfolio_exposure_pct,
        "is_long": is_long,
    }


def calculate_sma(series: List[float], period: int) -> List[Optional[float]]:
    """Compute Simple Moving Average (SMA) over series."""
    sma = []
    for i in range(len(series)):
        if i + 1 < period:
            sma.append(None)
        else:
            window = series[i + 1 - period : i + 1]
            sma.append(sum(window) / period)
    return sma


def calculate_ema(series: List[float], period: int) -> List[Optional[float]]:
    """Compute Exponential Moving Average (EMA) over series."""
    ema = []
    multiplier = 2.0 / (period + 1.0)
    for i, val in enumerate(series):
        if i + 1 < period:
            ema.append(None)
        elif i + 1 == period:
            # First EMA is SMA of first `period` elements
            window = series[:period]
            ema.append(sum(window) / period)
        else:
            prev = ema[-1]
            current = (val - prev) * multiplier + prev
            ema.append(current)
    return ema


def calculate_rsi(series: List[float], period: int = 14) -> List[Optional[float]]:
    """Compute Relative Strength Index (RSI) over series."""
    if len(series) <= period:
        return [None] * len(series)

    rsi = [None] * period
    gains = []
    losses = []

    for i in range(1, len(series)):
        delta = series[i] - series[i - 1]
        gains.append(max(0.0, delta))
        losses.append(max(0.0, -delta))

    if len(gains) < period:
        return [None] * len(series)

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    if avg_loss == 0:
        rsi.append(100.0)
    else:
        rs = avg_gain / avg_loss
        rsi.append(100.0 - (100.0 / (1.0 + rs)))

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            rsi.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi.append(100.0 - (100.0 / (1.0 + rs)))

    return rsi


def run_backtest(
    prices: List[float],
    timestamps: Optional[List[Any]] = None,
    strategy: str = "SMA_CROSSOVER",
    initial_capital: float = 100000.0,
    fast_period: int = 9,
    slow_period: int = 21,
    fee_pct: float = 0.05,
    stop_loss_pct: float = 0.0,
    take_profit_pct: float = 0.0,
) -> Dict[str, Any]:
    """Execute chronological bar-by-bar backtest without lookahead bias.

    Signals generated on bar `t` are executed at bar `t+1` price to strictly avoid look-ahead bias.
    Deducts transaction fees on every trade entry and exit.

    Args:
        prices: List of chronological closing prices.
        timestamps: Optional list of timestamps corresponding to prices.
        strategy: 'SMA_CROSSOVER', 'EMA_MOMENTUM', 'RSI_MEAN_REVERSION', or 'BREAKOUT'.
        initial_capital: Starting virtual cash balance.
        fast_period: Parameter for fast indicator (e.g. 9 for SMA).
        slow_period: Parameter for slow indicator (e.g. 21 for SMA).
        fee_pct: One-way transaction fee percentage.
        stop_loss_pct: Optional percentage stop-loss from entry price.
        take_profit_pct: Optional percentage take-profit from entry price.

    Returns:
        Comprehensive performance dictionary containing equity curves, trades, and metrics.
    """
    min_required = max(slow_period, fast_period, 5) + 2
    if len(prices) < min_required:
        raise ValueError(f"Insufficient historical price data points ({len(prices)}) for requested backtest parameters (min {min_required}).")

    if not timestamps or len(timestamps) != len(prices):
        timestamps = [f"Bar {i + 1}" for i in range(len(prices))]

    # Indicator calculation
    strat = strategy.upper()
    if strat == "EMA_MOMENTUM":
        fast_series = calculate_ema(prices, fast_period)
        slow_series = calculate_ema(prices, slow_period)
    elif strat == "RSI_MEAN_REVERSION":
        rsi_series = calculate_rsi(prices, period=fast_period or 14)
    elif strat == "BREAKOUT":
        # Donchian channel breakout
        pass
    else:  # Default SMA_CROSSOVER
        fast_series = calculate_sma(prices, fast_period)
        slow_series = calculate_sma(prices, slow_period)

    # State variables
    cash = initial_capital
    position = 0.0  # units held
    entry_price = 0.0
    equity_curve: List[Dict[str, Any]] = []
    trades: List[Dict[str, Any]] = []

    # Benchmark: Buy and Hold
    buy_hold_shares = initial_capital / prices[0]

    pending_order: Optional[str] = None  # 'BUY' or 'SELL' to execute on next bar

    for i in range(len(prices)):
        current_price = prices[i]
        current_time = timestamps[i]

        # 1. Execute pending signal from previous bar at current price (no lookahead bias)
        if pending_order == "BUY" and position == 0.0:
            fee = cash * (fee_pct / 100.0)
            investable = cash - fee
            if investable > 0:
                position = investable / current_price
                cash = 0.0
                entry_price = current_price
                trades.append({
                    "action": "BUY",
                    "bar_index": i,
                    "time": current_time,
                    "price": current_price,
                    "quantity": round(position, 4),
                    "fee": round(fee, 2),
                    "reason": "Signal Entry",
                })
            pending_order = None

        elif pending_order == "SELL" and position > 0.0:
            proceeds = position * current_price
            fee = proceeds * (fee_pct / 100.0)
            net_proceeds = proceeds - fee
            realized_pnl = net_proceeds - (position * entry_price)
            cash += net_proceeds

            trades.append({
                "action": "SELL",
                "bar_index": i,
                "time": current_time,
                "price": current_price,
                "quantity": round(position, 4),
                "fee": round(fee, 2),
                "pnl": round(realized_pnl, 2),
                "return_pct": round((current_price - entry_price) / entry_price * 100.0, 2),
                "reason": "Signal Exit",
            })
            position = 0.0
            entry_price = 0.0
            pending_order = None

        # 2. Check intraday stop-loss or take-profit if currently holding
        if position > 0.0 and entry_price > 0.0:
            if stop_loss_pct > 0.0 and current_price <= entry_price * (1.0 - stop_loss_pct / 100.0):
                proceeds = position * current_price
                fee = proceeds * (fee_pct / 100.0)
                net_proceeds = proceeds - fee
                pnl = net_proceeds - (position * entry_price)
                cash += net_proceeds
                trades.append({
                    "action": "SELL",
                    "bar_index": i,
                    "time": current_time,
                    "price": current_price,
                    "quantity": round(position, 4),
                    "fee": round(fee, 2),
                    "pnl": round(pnl, 2),
                    "return_pct": round((current_price - entry_price) / entry_price * 100.0, 2),
                    "reason": "Stop Loss Hit",
                })
                position = 0.0
                entry_price = 0.0

            elif take_profit_pct > 0.0 and current_price >= entry_price * (1.0 + take_profit_pct / 100.0):
                proceeds = position * current_price
                fee = proceeds * (fee_pct / 100.0)
                net_proceeds = proceeds - fee
                pnl = net_proceeds - (position * entry_price)
                cash += net_proceeds
                trades.append({
                    "action": "SELL",
                    "bar_index": i,
                    "time": current_time,
                    "price": current_price,
                    "quantity": round(position, 4),
                    "fee": round(fee, 2),
                    "pnl": round(pnl, 2),
                    "return_pct": round((current_price - entry_price) / entry_price * 100.0, 2),
                    "reason": "Take Profit Hit",
                })
                position = 0.0
                entry_price = 0.0

        # 3. Generate signals for NEXT bar
        if strat in ("SMA_CROSSOVER", "EMA_MOMENTUM"):
            if i > 0 and fast_series[i] is not None and slow_series[i] is not None and fast_series[i - 1] is not None and slow_series[i - 1] is not None:
                # Bullish Crossover: Fast crosses above Slow
                if fast_series[i - 1] <= slow_series[i - 1] and fast_series[i] > slow_series[i]:
                    if position == 0.0:
                        pending_order = "BUY"
                # Bearish Crossover: Fast crosses below Slow
                elif fast_series[i - 1] >= slow_series[i - 1] and fast_series[i] < slow_series[i]:
                    if position > 0.0:
                        pending_order = "SELL"

        elif strat == "RSI_MEAN_REVERSION":
            if i > 0 and rsi_series[i] is not None and rsi_series[i - 1] is not None:
                # Oversold bounce (< 30)
                if rsi_series[i - 1] < 30.0 and rsi_series[i] >= 30.0:
                    if position == 0.0:
                        pending_order = "BUY"
                # Overbought reversal (> 70)
                elif rsi_series[i - 1] > 70.0 and rsi_series[i] <= 70.0:
                    if position > 0.0:
                        pending_order = "SELL"

        elif strat == "BREAKOUT":
            lookback = fast_period or 20
            if i >= lookback:
                window = prices[i - lookback : i]
                highest_high = max(window)
                lowest_low = min(window)
                if current_price > highest_high and position == 0.0:
                    pending_order = "BUY"
                elif current_price < lowest_low and position > 0.0:
                    pending_order = "SELL"

        # Record portfolio mark-to-market equity
        current_equity = round(cash + (position * current_price), 2)
        buy_hold_equity = round(buy_hold_shares * current_price, 2)

        equity_curve.append({
            "time": current_time,
            "bar_index": i,
            "price": current_price,
            "strategy_equity": current_equity,
            "benchmark_equity": buy_hold_equity,
            "in_market": position > 0.0,
        })

    # Close out open position at the final bar for complete accounting
    if position > 0.0:
        last_price = prices[-1]
        proceeds = position * last_price
        fee = proceeds * (fee_pct / 100.0)
        net_proceeds = proceeds - fee
        pnl = net_proceeds - (position * entry_price)
        cash += net_proceeds
        trades.append({
            "action": "SELL",
            "bar_index": len(prices) - 1,
            "time": timestamps[-1],
            "price": last_price,
            "quantity": round(position, 4),
            "fee": round(fee, 2),
            "pnl": round(pnl, 2),
            "return_pct": round((last_price - entry_price) / entry_price * 100.0, 2),
            "reason": "End of Backtest Period",
        })
        position = 0.0
        equity_curve[-1]["strategy_equity"] = round(cash, 2)

    # 4. Compute comprehensive performance metrics
    final_equity = equity_curve[-1]["strategy_equity"]
    total_return_pct = round(((final_equity - initial_capital) / initial_capital) * 100.0, 2)
    buy_hold_return_pct = round(((equity_curve[-1]["benchmark_equity"] - initial_capital) / initial_capital) * 100.0, 2)

    # Maximum Drawdown
    peak = initial_capital
    max_drawdown_pct = 0.0
    drawdown_series: List[float] = []

    for pt in equity_curve:
        eq = pt["strategy_equity"]
        if eq > peak:
            peak = eq
        dd = ((peak - eq) / peak) * 100.0 if peak > 0 else 0.0
        drawdown_series.append(round(dd, 2))
        if dd > max_drawdown_pct:
            max_drawdown_pct = dd

    max_drawdown_pct = round(max_drawdown_pct, 2)

    # Closed round-trip trades analysis
    sell_trades = [t for t in trades if t["action"] == "SELL" and "pnl" in t]
    total_trades_count = len(sell_trades)
    winning_trades = [t for t in sell_trades if t["pnl"] > 0]
    losing_trades = [t for t in sell_trades if t["pnl"] < 0]

    win_rate_pct = round((len(winning_trades) / total_trades_count * 100.0), 2) if total_trades_count > 0 else 0.0
    gross_profits = sum(t["pnl"] for t in winning_trades)
    gross_losses = abs(sum(t["pnl"] for t in losing_trades))

    if gross_losses > 0:
        profit_factor = round(gross_profits / gross_losses, 2)
    elif gross_profits > 0:
        profit_factor = 99.99
    else:
        profit_factor = 0.0

    avg_win_inr = round(gross_profits / len(winning_trades), 2) if winning_trades else 0.0
    avg_loss_inr = round(gross_losses / len(losing_trades), 2) if losing_trades else 0.0

    # Market Exposure time (% of bars holding position)
    bars_in_market = sum(1 for pt in equity_curve if pt["in_market"])
    exposure_time_pct = round((bars_in_market / len(prices)) * 100.0, 2)

    # Annualized return (CAGR) assuming daily bars (252 trading days/year)
    days = max(1, len(prices))
    if days >= 30 and final_equity > 0:
        years = days / 252.0
        cagr_pct = round(((final_equity / initial_capital) ** (1.0 / years) - 1.0) * 100.0, 2)
    else:
        cagr_pct = total_return_pct

    return {
        "strategy": strategy,
        "parameters": {
            "fast_period": fast_period,
            "slow_period": slow_period,
            "fee_pct": fee_pct,
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
            "initial_capital": initial_capital,
        },
        "metrics": {
            "initial_capital": initial_capital,
            "final_equity": final_equity,
            "total_return_pct": total_return_pct,
            "buy_and_hold_return_pct": buy_hold_return_pct,
            "outperformance_pct": round(total_return_pct - buy_hold_return_pct, 2),
            "cagr_pct": cagr_pct,
            "max_drawdown_pct": max_drawdown_pct,
            "win_rate_pct": win_rate_pct,
            "total_trades": total_trades_count,
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "gross_profit_inr": round(gross_profits, 2),
            "gross_loss_inr": round(gross_losses, 2),
            "profit_factor": profit_factor,
            "avg_win_inr": avg_win_inr,
            "avg_loss_inr": avg_loss_inr,
            "win_loss_payoff_ratio": round(avg_win_inr / avg_loss_inr, 2) if avg_loss_inr > 0 else 0.0,
            "exposure_time_pct": exposure_time_pct,
            "total_fees_paid": round(sum(t.get("fee", 0.0) for t in trades), 2),
        },
        "equity_curve": equity_curve,
        "drawdown_curve": drawdown_series,
        "trades": trades,
    }


def run_scenario_stress_test(
    portfolio_cash: float,
    holdings: Dict[str, Dict[str, Any]],
    price_shock_pct: float = -10.0,
    volatility_shock_multiplier: float = 1.0,
    fee_hike_pct: float = 0.0,
    correlated_drop: bool = True,
) -> Dict[str, Any]:
    """Simulate hypothetical stress test shocks across active virtual portfolio.

    Args:
        portfolio_cash: Available cash in INR.
        holdings: Map of symbol -> { 'quantity': float, 'current_price': float, 'avg_buy_price': float }
        price_shock_pct: Market decline percentage (e.g. -10.0 for -10% market crash).
        volatility_shock_multiplier: Volatility expansion factor (e.g. 1.5 for 50% wider bid-ask slippage).
        fee_hike_pct: Additional transaction fees or taxes to model.
        correlated_drop: If True, all risky assets decline together.

    Returns:
        Projected portfolio valuation, losses, margin cushion, and risk alerts.
    """
    baseline_holdings_val = 0.0
    stressed_holdings_val = 0.0
    position_impacts = []

    for sym, h in holdings.items():
        qty = h.get("quantity", 0.0)
        if qty <= 0:
            continue
        p = h.get("current_price", h.get("avg_buy_price", 100.0))
        val = qty * p
        baseline_holdings_val += val

        # Price decline with volatility slippage deduction
        shock = price_shock_pct / 100.0
        slippage_deduction = (0.002 * volatility_shock_multiplier)  # widen bid/ask spread
        effective_shock = shock - slippage_deduction

        stressed_price = max(0.01, round(p * (1.0 + effective_shock), 2))
        stressed_val = round(qty * stressed_price, 2)
        stressed_holdings_val += stressed_val

        position_impacts.append({
            "symbol": sym,
            "quantity": qty,
            "baseline_price": p,
            "stressed_price": stressed_price,
            "baseline_value": val,
            "stressed_value": stressed_val,
            "loss_inr": round(val - stressed_val, 2),
            "loss_pct": round(effective_shock * 100.0, 2),
        })

    baseline_total_equity = portfolio_cash + baseline_holdings_val
    stressed_total_equity = portfolio_cash + stressed_holdings_val
    equity_loss_inr = round(baseline_total_equity - stressed_total_equity, 2)
    equity_loss_pct = round((equity_loss_inr / baseline_total_equity * 100.0), 2) if baseline_total_equity > 0 else 0.0

    stressed_exposure_pct = round((stressed_holdings_val / stressed_total_equity * 100.0), 2) if stressed_total_equity > 0 else 0.0
    cash_buffer_pct = round((portfolio_cash / stressed_total_equity * 100.0), 2) if stressed_total_equity > 0 else 100.0

    # Risk level classification
    if equity_loss_pct >= 25.0 or stressed_exposure_pct >= 90.0:
        risk_rating = "CRITICAL RISK"
        risk_color = "var(--red)"
        advice = "High capital destruction risk. Consider increasing liquid cash buffer or setting hard stop-losses."
    elif equity_loss_pct >= 10.0:
        risk_rating = "MODERATE RISK"
        risk_color = "var(--yellow)"
        advice = "Manageable portfolio drawdown. Cash reserve buffers against complete capital impairment."
    else:
        risk_rating = "LOW RISK"
        risk_color = "var(--green)"
        advice = "Portfolio demonstrates strong resilience under this hypothetical market stress scenario."

    return {
        "scenario": {
            "price_shock_pct": price_shock_pct,
            "volatility_shock_multiplier": volatility_shock_multiplier,
            "fee_hike_pct": fee_hike_pct,
            "correlated_drop": correlated_drop,
        },
        "baseline_total_equity": round(baseline_total_equity, 2),
        "stressed_total_equity": round(stressed_total_equity, 2),
        "equity_loss_inr": equity_loss_inr,
        "equity_loss_pct": equity_loss_pct,
        "portfolio_cash": portfolio_cash,
        "stressed_holdings_val": round(stressed_holdings_val, 2),
        "stressed_exposure_pct": stressed_exposure_pct,
        "cash_buffer_pct": cash_buffer_pct,
        "risk_rating": risk_rating,
        "risk_color": risk_color,
        "advice": advice,
        "position_impacts": position_impacts,
        "disclaimer": "HYPOTHETICAL STRESS-TEST SCENARIOS — SIMULATION ONLY — NOT A PREDICTIVE FINANCIAL FORECAST",
    }
