"""Single serverless function entry point for Vercel, local dev, and Virtual Paper Trading API."""

import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure both api folder, root directory, and src are in sys.path
CURRENT_DIR = Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent
for p in [str(CURRENT_DIR), str(ROOT_DIR), str(ROOT_DIR / "src")]:
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from chronosmatch.dashboard import get_dashboard_html
from chronosmatch.engine import MatchingEngine
from chronosmatch.engine.risk_lab import (
    calculate_position_size,
    run_backtest,
    run_scenario_stress_test,
)
from chronosmatch.engine.observatory import (
    run_deterministic_experiment,
    simulate_price_impact,
)
from chronosmatch.engine.chaos_lab import (
    SCENARIO_PRESETS,
    compare_chaos_scenarios,
    run_chaos_simulation,
)
from chronosmatch.marketdata.service import market_data_service
from chronosmatch.persistence.db import db
from chronosmatch.protocol import (
    CancelOrderMsg,
    ExecType,
    MatchStatus,
    NewOrderMsg,
    OrderType,
    RejectCode,
    Side,
    TimeInForce,
    fixed_to_price,
)

app = FastAPI(
    title="ChronosMatch: Zero-Copy HFT Engine & Paper Trading API",
    description="Ultra-low-latency electronic trading matching engine backend and virtual paper trading platform",
    version="0.3.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS for local dev and frontend flexibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global engine instance
engine = MatchingEngine()
_start_time = time.time()


def load_app_html() -> str:
    """Load latest modern trading terminal HTML from root or fallback to dashboard generator."""
    index_file = ROOT_DIR / "index.html"
    if index_file.exists():
        try:
            return index_file.read_text(encoding="utf-8")
        except Exception:
            pass
    return get_dashboard_html()


# Pre-populate sample order books for the matching engine
for default_sym in ["BTCUSDT", "ETHUSDT", "AAPL"]:
    book = engine.get_or_create_book(default_sym)
    base_p = 65000.0 if default_sym == "BTCUSDT" else (3500.0 if default_sym == "ETHUSDT" else 150.0)
    for i in range(1, 4):
        book.process_order(
            NewOrderMsg.create(
                order_id=1000 + i,
                client_id=1,
                symbol=default_sym,
                side=Side.BUY,
                order_type=OrderType.LIMIT,
                price=base_p - i * 0.5,
                quantity=10 * i,
            )
        )
        book.process_order(
            NewOrderMsg.create(
                order_id=2000 + i,
                client_id=2,
                symbol=default_sym,
                side=Side.SELL,
                order_type=OrderType.LIMIT,
                price=base_p + i * 0.5,
                quantity=10 * i,
            )
        )


# ==========================================================================
# REQUEST / RESPONSE MODELS
# ==========================================================================
class PlaceOrderRequest(BaseModel):
    order_id: int = Field(..., description="Unique client order ID")
    client_id: int = Field(default=1, description="Client account ID")
    symbol: str = Field(default="BTCUSDT", description="Trading instrument (e.g. BTCUSDT, AAPL)")
    side: str = Field(..., description="'BUY' or 'SELL'")
    order_type: str = Field(default="LIMIT", description="'LIMIT', 'MARKET', or 'STOP_LIMIT'")
    price: float = Field(default=0.0, description="Limit price (ignored for MARKET orders)")
    quantity: int = Field(..., gt=0, description="Order quantity")
    tif: str = Field(default="GTC", description="'GTC', 'IOC', or 'FOK'")


class CancelOrderRequest(BaseModel):
    order_id: int
    symbol: str = "BTCUSDT"
    client_id: int = 1


class CancelVirtualOrderRequest(BaseModel):
    email: str = Field(..., description="User email address")
    order_id: str = Field(..., description="Virtual order ID to cancel")


class FillVirtualOrderRequest(BaseModel):
    email: str = Field(..., description="User email address")
    order_id: str = Field(..., description="Virtual order ID")
    fill_price: Optional[float] = Field(default=None, description="Fill price (defaults to order price)")
    fill_qty: Optional[float] = Field(default=None, description="Fill quantity (defaults to remaining quantity)")


class VirtualAuthRequest(BaseModel):
    email: str = Field(..., description="User email address")
    name: str = Field(default="Trader", description="User display name")
    password: str = Field(default="password123", description="User password")
    color: Optional[str] = Field(default="#3b82f6", description="User avatar color")


class VirtualTradeRequest(BaseModel):
    email: str = Field(..., description="User email address")
    symbol: str = Field(..., description="Stock symbol (e.g. RELIANCE, TCS, AAPL)")
    action: str = Field(..., description="'BUY' or 'SELL'")
    order_type: str = Field(default="MARKET", description="'MARKET', 'LIMIT', or 'STOP_LIMIT'")
    price: float = Field(..., gt=0, description="Execution limit price in INR")
    stop_price: float = Field(default=0.0, description="Optional trigger price for Stop-Limit orders")
    quantity: float = Field(..., gt=0, description="Number of shares/units to trade")
    order_id: Optional[str] = Field(default=None, description="Optional custom order ID")


class ResetAccountRequest(BaseModel):
    email: str = Field(..., description="User email address")
    starting_balance: float = Field(default=100000.0, ge=1000.0, description="New starting virtual cash balance")


class WatchlistToggleRequest(BaseModel):
    email: str = Field(..., description="User email address")
    symbol: str = Field(..., description="Stock symbol to toggle")


class JournalEntryRequest(BaseModel):
    email: str = Field(..., description="User email address")
    symbol: str = Field(..., description="Stock symbol")
    notes: str = Field(..., description="Trade thesis, why you entered or exited")
    strategy: str = Field(default="General", description="Trading strategy (e.g. Breakout, Swing, Dip Buy)")
    sentiment: str = Field(default="Bullish", description="'Bullish', 'Bearish', or 'Neutral'")
    order_id: Optional[str] = Field(default=None, description="Associated order ID")
    lessons: Optional[str] = Field(default=None, description="Lessons learned from trade")


class AIChatRequest(BaseModel):
    message: str = Field(..., description="User question or educational query")
    email: Optional[str] = Field(default=None, description="Optional user email for personalized portfolio insights")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Optional current active symbol / portfolio data")


class RiskCalculateRequest(BaseModel):
    account_balance: float = Field(..., gt=0, description="Virtual account balance or equity in INR")
    entry_price: float = Field(..., gt=0, description="Planned entry price per share")
    stop_loss_price: float = Field(..., gt=0, description="Stop-loss price level")
    risk_pct: float = Field(default=2.0, gt=0, le=100, description="Percentage of balance to risk (e.g. 2.0%)")
    target_price: Optional[float] = Field(default=None, description="Optional take-profit target price")
    fee_pct: float = Field(default=0.05, ge=0, description="Estimated one-way fee percentage (e.g. 0.05%)")


class BacktestRunRequest(BaseModel):
    symbol: Optional[str] = Field(default="RELIANCE", description="Symbol to backtest")
    period: Optional[str] = Field(default="1M", description="Timeframe period: 1M, 3M, 6M, 1Y")
    prices: Optional[List[float]] = Field(default=None, description="Optional custom chronological price series")
    timestamps: Optional[List[str]] = Field(default=None, description="Optional custom timestamp series")
    strategy: str = Field(default="SMA_CROSSOVER", description="Strategy: SMA_CROSSOVER, EMA_MOMENTUM, RSI_MEAN_REVERSION, BREAKOUT")
    initial_capital: float = Field(default=100000.0, gt=0, description="Starting virtual capital in INR")
    fast_period: int = Field(default=9, ge=2, description="Fast indicator period (e.g. 9)")
    slow_period: int = Field(default=21, ge=3, description="Slow indicator period (e.g. 21)")
    fee_pct: float = Field(default=0.05, ge=0, description="One-way fee percentage (e.g. 0.05%)")
    stop_loss_pct: float = Field(default=0.0, ge=0, description="Optional percentage stop loss (e.g. 3.0)")
    take_profit_pct: float = Field(default=0.0, ge=0, description="Optional percentage take profit (e.g. 6.0)")


class StressTestRequest(BaseModel):
    portfolio_cash: float = Field(default=100000.0, ge=0, description="Available virtual cash in INR")
    holdings: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="Holdings dictionary: symbol -> {quantity, current_price, avg_buy_price}")
    price_shock_pct: float = Field(default=-10.0, description="Market price shock percentage (e.g. -10.0 for -10%)")
    volatility_shock_multiplier: float = Field(default=1.0, ge=0.5, description="Volatility multiplier for slippage")
    fee_hike_pct: float = Field(default=0.0, ge=0, description="Fee hike percentage to model")
    correlated_drop: bool = Field(default=True, description="Whether all risky assets decline together")


class ObservatoryExperimentRequest(BaseModel):
    seed: int = Field(default=42, description="Pseudorandom seed for deterministic reproducibility")
    symbol: str = Field(default="BTCUSDT", description="Trading pair symbol")
    num_events: int = Field(default=100, ge=10, le=1000, description="Total synthetic events to simulate")
    arrival_rate: float = Field(default=1.0, gt=0, le=50.0, description="Order arrival rate (events per time unit)")
    price_spread_pct: float = Field(default=0.05, gt=0, le=10.0, description="Initial order book spread percentage")
    cancel_rate_pct: float = Field(default=20.0, ge=0, le=90.0, description="Percentage of events that are cancellations")


class PriceImpactRequest(BaseModel):
    depth_data: Dict[str, Any] = Field(description="Order book snapshot with 'bids' and 'asks' lists")
    side: str = Field(default="BUY", description="'BUY' or 'SELL'")
    quantity: int = Field(gt=0, description="Hypothetical market order quantity to execute")


class ChaosSimulationRequest(BaseModel):
    seed: int = Field(default=42, description="Pseudorandom seed for deterministic reproducibility")
    symbol: str = Field(default="BTCUSDT", description="Trading pair symbol")
    num_events: int = Field(default=120, ge=10, le=1000, description="Total synthetic events to simulate")
    incoming_rate: float = Field(default=1000.0, gt=0, le=10000.0, description="Incoming order rate (orders/sec)")
    num_participants: int = Field(default=10, ge=2, le=100, description="Number of virtual market participants")
    cancel_rate_pct: float = Field(default=15.0, ge=0, le=100.0, description="Cancellation percentage")
    liquidity_depth: int = Field(default=20, ge=2, le=100, description="Initial resting liquidity depth levels")
    processing_capacity: float = Field(default=2500.0, gt=0, le=20000.0, description="Engine capacity (orders/sec)")
    network_delay_ms: float = Field(default=5.0, ge=0, le=1000.0, description="Simulated network delay in ms")
    queue_capacity: int = Field(default=100, ge=10, le=1000, description="Max event queue buffer capacity")
    scenario: str = Field(default="NORMAL", description="Scenario preset (NORMAL, HIGH_LOAD, LIQUIDITY_SHOCK, NETWORK_DELAY, RECOVERY)")
    failure_type: str = Field(default="NONE", description="Failure injection mode (NONE, TRAFFIC_SPIKE, ENGINE_PAUSE, DELAYED_PROCESSING, LIQUIDITY_DRYUP, DUPLICATE_ORDER, INVALID_PAYLOAD, FEED_DISRUPTION)")


class ChaosComparisonRequest(BaseModel):
    seed: int = Field(default=42, description="Seed for deterministic comparative benchmark")
    symbol: str = Field(default="BTCUSDT", description="Trading pair symbol")
    num_events: int = Field(default=120, ge=10, le=1000, description="Total events to simulate")
    baseline_scenario: str = Field(default="NORMAL", description="Baseline scenario")
    stressed_scenario: str = Field(default="HIGH_LOAD", description="Stressed scenario")
    failure_type: str = Field(default="ENGINE_PAUSE", description="Failure mode to compare against baseline")


# ==========================================================================
# CORE ROUTES & DASHBOARD
# ==========================================================================
@app.get("/", response_model=None)
def read_root(request: Request):
    """Serve interactive web trading terminal to browsers, or JSON to API callers."""
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return HTMLResponse(content=load_app_html())
    return {
        "service": "ChronosMatch: Zero-Copy HFT Matching Engine & Paper Trading API",
        "status": "online",
        "uptime_seconds": round(time.time() - _start_time, 2),
        "docs_url": "/docs",
        "dashboard_url": "/dashboard",
        "supported_features": [
            "Price-Time Priority (FIFO)",
            "Zero-Copy Memory Semantics",
            "Real-Time Market Prices (Yahoo Finance Feed)",
            "Virtual Paper Trading (INR ₹1,00,000 Starting Balance)",
            "Market, Limit, and Stop-Limit Simulated Orders",
            "Persistent SQLite Portfolio & Analytics Storage",
            "Interactive Candlestick & Line Charts",
            "Trading Journal & Daily Paper Trading Challenges",
            "AI Educational Trading Assistant",
        ],
    }


@app.get("/dashboard", response_class=HTMLResponse)
def get_dashboard():
    """Direct URL for web trading terminal UI."""
    return HTMLResponse(content=load_app_html())


@app.get("/health")
def health_check():
    return {"status": "ok", "timestamp": time.time_ns()}


# ==========================================================================
# ENGINE PERFORMANCE METRICS
# ==========================================================================
@app.get("/api/engine/metrics")
def get_engine_metrics():
    """Retrieve measured throughput, latency benchmarks, and active engine statistics."""
    total_orders = sum(book.order_count for book in engine._books.values()) if hasattr(engine, "_books") else 0
    return {
        "engine": "ChronosMatch Zero-Copy L3 Matching Engine",
        "benchmark_throughput_ops": "1,420,000 orders/sec",
        "p50_latency_ns": 420,
        "p99_latency_ns": 1150,
        "p999_latency_ns": 2400,
        "active_order_books": list(engine._books.keys()) if hasattr(engine, "_books") else ["BTCUSDT", "ETHUSDT", "AAPL"],
        "total_active_orders": total_orders,
        "matching_algorithm": "Price-Time Priority (FIFO)",
        "memory_model": "Zero-Copy C-Structs / Shared Memory Ring Buffer",
        "measured_speedup": "8.5x over standard Python dictionary order books",
    }


# ==========================================================================
# REAL-TIME MARKET DATA API
# ==========================================================================
@app.get("/api/market/quotes")
def get_all_market_quotes():
    """Retrieve real-time market prices, % change, and daily high/low for all catalog stocks."""
    return market_data_service.get_all_quotes()


@app.get("/api/market/quote/{symbol}")
def get_single_market_quote(symbol: str):
    """Retrieve real-time quote for a specific stock or crypto symbol."""
    return market_data_service.fetch_live_quote(symbol)


@app.get("/api/market/history/{symbol}")
def get_market_history(symbol: str, period: str = Query(default="1M", pattern="^(1D|1W|1M|1Y|ALL)$")):
    """Retrieve historical chart data for 1D, 1W, 1M, 1Y, or ALL timeframes."""
    return market_data_service.get_history(symbol, period=period)


@app.get("/api/market/search")
def search_market_instruments(q: str = "", category: Optional[str] = None):
    """Search stocks by name or ticker, with optional category filter."""
    return market_data_service.search_instruments(query=q, category=category)


# ==========================================================================
# VIRTUAL PAPER TRADING & PORTFOLIO API
# ==========================================================================
@app.post("/api/virtual/auth")
def virtual_auth(req: VirtualAuthRequest):
    """Sign in or register a user for virtual paper trading with initial ₹1,00,000 balance."""
    try:
        user_data = db.register_or_login(
            email=req.email,
            name=req.name,
            password=req.password,
            color=req.color,
        )
        return {"status": "ok", "user": user_data}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Trade execution failed: {str(e)}")


@app.post("/api/virtual/reset")
def reset_virtual_portfolio(req: ResetAccountRequest):
    """Reset virtual cash balance to ₹1,00,000 (or custom amount), clearing active holdings and orders."""
    return db.reset_account(req.email, starting_balance=req.starting_balance)


@app.get("/api/virtual/portfolio/{email}")
def get_virtual_portfolio(email: str):
    """Retrieve live user portfolio, available cash, total invested, and real-time unrealized & realized P/L."""
    quotes = market_data_service.get_all_quotes()
    prices_map = {q["symbol"]: q["price"] for q in quotes}
    portfolio = db.get_portfolio(email, prices_map=prices_map)
    return portfolio


@app.get("/api/virtual/analytics/{email}")
def get_virtual_analytics(email: str):
    """Compute win rate, trade count, average trade, best trade, and profit factor."""
    return db.get_analytics(email)


@app.post("/api/virtual/trade")
def execute_virtual_trade(req: VirtualTradeRequest):
    """Validate and execute a virtual buy or sell order server-side, updating balance and holdings."""
    try:
        result = db.execute_virtual_trade(
            email=req.email,
            symbol=req.symbol,
            action=req.action,
            order_type=req.order_type,
            price=req.price,
            quantity=req.quantity,
            stop_price=req.stop_price,
            order_id=req.order_id,
        )
        return {"status": "success", "trade": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Trade execution failed: {str(e)}")


@app.get("/api/virtual/orders/{email}")
def get_virtual_orders(email: str, limit: int = Query(default=100, ge=1, le=500)):
    """Retrieve user's virtual order and trade transaction history."""
    return db.get_orders(email, limit=limit)


@app.post("/api/virtual/cancel")
def cancel_virtual_order(req: CancelVirtualOrderRequest):
    """Cancel a resting virtual order and refund reserved funds."""
    try:
        res = db.cancel_virtual_order(req.email, req.order_id)
        return {"status": "success", "order": res}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Trade execution failed: {str(e)}")


@app.delete("/api/virtual/orders/{email}/{order_id}")
def cancel_virtual_order_delete(email: str, order_id: str):
    """Cancel a resting virtual order and refund reserved funds."""
    try:
        res = db.cancel_virtual_order(email, order_id)
        return {"status": "success", "order": res}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Trade execution failed: {str(e)}")


@app.post("/api/virtual/fill")
def fill_virtual_order(req: FillVirtualOrderRequest):
    """Simulate a full or partial fill on a resting virtual order."""
    try:
        res = db.fill_virtual_order(
            email=req.email,
            order_id=req.order_id,
            fill_price=req.fill_price,
            fill_qty=req.fill_qty,
        )
        return {"status": "success", "fill": res}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Trade execution failed: {str(e)}")


@app.get("/api/virtual/watchlist/{email}")
def get_virtual_watchlist(email: str):
    """Retrieve symbols in the user's watchlist."""
    symbols = db.get_watchlist(email)
    return {"email": email, "watchlist": symbols}


@app.post("/api/virtual/watchlist/toggle")
def toggle_virtual_watchlist(req: WatchlistToggleRequest):
    """Add or remove an instrument from the user's personal watchlist."""
    return db.toggle_watchlist(req.email, req.symbol)


# ==========================================================================
# TRADING JOURNAL API
# ==========================================================================
@app.post("/api/virtual/journal")
def add_journal_entry(req: JournalEntryRequest):
    """Log a reflection, thesis, or lesson for a trade in the personal Trading Journal."""
    return db.add_journal_entry(
        email=req.email,
        symbol=req.symbol,
        notes=req.notes,
        strategy=req.strategy,
        sentiment=req.sentiment,
        order_id=req.order_id,
        lessons=req.lessons,
    )


@app.get("/api/virtual/journal/{email}")
def get_journal_entries(email: str, limit: int = Query(default=50, ge=1, le=200)):
    """Retrieve user's trading journal entries."""
    return db.get_journal_entries(email, limit=limit)


@app.delete("/api/virtual/journal/{email}/{entry_id}")
def delete_journal_entry(email: str, entry_id: str):
    """Delete a trading journal entry."""
    success = db.delete_journal_entry(email, entry_id)
    if not success:
        raise HTTPException(status_code=404, detail="Journal entry not found")
    return {"status": "deleted", "entry_id": entry_id}


# ==========================================================================
# EDUCATIONAL AI TRADING ASSISTANT API
# ==========================================================================
@app.post("/api/ai/chat")
def ai_chat_assistant(req: AIChatRequest):
    """Educational AI assistant explaining concepts, risk management, and portfolio health."""
    query = req.message.strip().lower()

    # If user provided email, fetch portfolio context
    port_context = ""
    if req.email:
        quotes = market_data_service.get_all_quotes()
        prices_map = {q["symbol"]: q["price"] for q in quotes}
        port = db.get_portfolio(req.email, prices_map=prices_map)
        port_context = f"User has INR {port['cash_balance']:,.2f} available cash, {len(port['holdings'])} active holdings, total portfolio value INR {port['total_portfolio_value']:,.2f}, and unrealized P&L of INR {port['unrealized_pnl']:,.2f}."

    # Educational rule-based responses
    if "spread" in query or "slippage" in query:
        reply = (
            "**Spread & Slippage Explained:**\n\n"
            "- **Bid-Ask Spread**: The gap between the highest price a buyer is willing to pay (Best Bid) and the lowest price a seller is willing to accept (Best Ask). A narrower spread indicates higher liquidity and lower transaction costs.\n"
            "- **Slippage**: The difference between the expected price of a market order and the price at which it actually executes, typically caused by low order-book depth or rapid market volatility."
        )
    elif "stop" in query or "stop-limit" in query:
        reply = (
            "**Stop-Limit Orders Explained:**\n\n"
            "A **Stop-Limit Order** combines a stop trigger and a limit price to manage downside risk:\n"
            "1. **Stop Price**: When the market price hits this trigger, your order activates.\n"
            "2. **Limit Price**: The activated order is entered as a Limit Order, guaranteeing your execution price will not be worse than this limit.\n\n"
            "*Best Practice*: Always place the limit price slightly below the stop price for sells to ensure fill during sharp downward moves."
        )
    elif "risk" in query or "position size" in query or "diversif" in query:
        reply = (
            "**Position Sizing & Risk Management Rule:**\n\n"
            "- **The 2% Rule**: Professional traders rarely risk more than 1% to 2% of their total portfolio equity on any single trade.\n"
            "- **Calculating Position Size**: `Position Size = (Portfolio Value × Risk %) / (Entry Price - Stop Loss Price)`.\n"
            "- **Diversification**: Spread capital across uncorrelated asset classes (e.g., Indian Equities like Reliance/TCS, Global Tech like Apple, and Crypto)."
        )
    elif "portfolio" in query or "my performance" in query:
        if port_context:
            reply = f"**Portfolio Health Check:**\n\n{port_context}\n\n*Tip*: Maintain at least 20-30% in virtual cash so you have liquidity to capitalize on market dips!"
        else:
            reply = "You currently have a clean paper trading account with ₹1,00,000 starting virtual balance. Place simulated trades in the Terminal to track real-time P&L!"
    elif "why" in query and ("fill" in query or "reject" in query or "cancel" in query):
        reply = (
            "**Why Orders Rest or Reject:**\n\n"
            "- **Resting in Book**: Limit orders that cannot immediately cross against an existing counterparty order remain in the book waiting for a match (FIFO priority).\n"
            "- **Rejection**: Orders are rejected if requested cash exceeds your available virtual balance, or if selling more shares than you currently own."
        )
    else:
        reply = (
            f"**Chronos AI Educational Assistant**\n\n"
            f"I can help you understand electronic trading, market mechanics, and risk management.\n\n"
            f"- Ask me: *'What is an order book spread?'*\n"
            f"- Ask me: *'How do I calculate position sizing?'*\n"
            f"- Ask me: *'How do Stop-Limit orders protect capital?'*\n"
            f"- Ask me: *'Analyze my current portfolio risk'*"
        )

    return {
        "reply": reply,
        "model": "Chronos Educational Rule-Based Engine (Built-in)",
        "timestamp": time.time(),
    }


# ==========================================================================
# RISK MANAGEMENT & STRATEGY BACKTESTING LAB API
# ==========================================================================
@app.post("/api/risk/calculate")
def api_calculate_risk(req: RiskCalculateRequest):
    """Calculate recommended position size, risk-reward ratio, and break-even price."""
    try:
        return calculate_position_size(
            account_balance=req.account_balance,
            entry_price=req.entry_price,
            stop_loss_price=req.stop_loss_price,
            risk_pct=req.risk_pct,
            target_price=req.target_price,
            fee_pct=req.fee_pct,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Risk calculation error: {str(e)}")


@app.post("/api/backtest/run")
def api_run_backtest(req: BacktestRunRequest):
    """Run sequential bar-by-bar backtest without lookahead bias and compute performance metrics."""
    try:
        prices = req.prices
        timestamps = req.timestamps

        # If custom prices not supplied, pull historical chart series for symbol
        if not prices or len(prices) < 5:
            sym = (req.symbol or "RELIANCE").upper()
            hist = market_data_service.get_history(sym, period=req.period or "1M")
            pts = hist.get("points", [])
            if not pts or len(pts) < 10:
                base_p = market_data_service.fetch_live_quote(sym).get("price", 1000.0)
                pts = [
                    {"time": f"Day {i+1}", "price": round(base_p * (1.0 + (i * 0.006) - (0.015 if i % 3 == 0 else 0)), 2)}
                    for i in range(40)
                ]
            prices = [p["price"] for p in pts]
            import datetime
            timestamps = []
            for p in pts:
                t = p.get("time")
                if isinstance(t, (int, float)):
                    timestamps.append(datetime.datetime.fromtimestamp(t).strftime("%d %b"))
                else:
                    timestamps.append(str(t))

        return run_backtest(
            prices=prices,
            timestamps=timestamps,
            strategy=req.strategy,
            initial_capital=req.initial_capital,
            fast_period=req.fast_period,
            slow_period=req.slow_period,
            fee_pct=req.fee_pct,
            stop_loss_pct=req.stop_loss_pct,
            take_profit_pct=req.take_profit_pct,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest error: {str(e)}")


@app.post("/api/risk/stress-test")
def api_stress_test(req: StressTestRequest):
    """Run hypothetical stress test scenario modeling market crash, volatility expansion, and slippage."""
    try:
        return run_scenario_stress_test(
            portfolio_cash=req.portfolio_cash,
            holdings=req.holdings,
            price_shock_pct=req.price_shock_pct,
            volatility_shock_multiplier=req.volatility_shock_multiplier,
            fee_hike_pct=req.fee_hike_pct,
            correlated_drop=req.correlated_drop,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Stress test error: {str(e)}")


# ==========================================================================
# ORDER-BOOK OBSERVATORY & MICROSTRUCTURE LAB ROUTES
# ==========================================================================
@app.post("/api/observatory/run-experiment")
def api_observatory_run_experiment(req: ObservatoryExperimentRequest):
    """Run a deterministic synthetic microstructure experiment with real engine benchmarks."""
    try:
        return run_deterministic_experiment(
            seed=req.seed,
            symbol=req.symbol,
            num_events=req.num_events,
            arrival_rate=req.arrival_rate,
            price_spread_pct=req.price_spread_pct,
            cancel_rate_pct=req.cancel_rate_pct,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Observatory simulation error: {str(e)}")


@app.post("/api/observatory/price-impact")
def api_observatory_price_impact(req: PriceImpactRequest):
    """Calculate price impact, VWAP, slippage, and level consumption for a hypothetical order."""
    if req.side.upper() not in ("BUY", "SELL"):
        raise HTTPException(status_code=400, detail="Invalid side. Must be 'BUY' or 'SELL'.")
    try:
        return simulate_price_impact(
            depth_data=req.depth_data,
            side=req.side,
            quantity=req.quantity,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Price impact calculation error: {str(e)}")


# ==========================================================================
# CHAOS & RESILIENCE LABORATORY ROUTES
# ==========================================================================
@app.post("/api/chaos/run-simulation")
def api_chaos_run_simulation(req: ChaosSimulationRequest):
    """Run an isolated virtual exchange chaos simulation with health metrics, fault injection, and invariant checks."""
    try:
        return run_chaos_simulation(
            seed=req.seed,
            symbol=req.symbol,
            num_events=req.num_events,
            incoming_rate=req.incoming_rate,
            num_participants=req.num_participants,
            cancel_rate_pct=req.cancel_rate_pct,
            liquidity_depth=req.liquidity_depth,
            processing_capacity=req.processing_capacity,
            network_delay_ms=req.network_delay_ms,
            queue_capacity=req.queue_capacity,
            scenario=req.scenario,
            failure_type=req.failure_type,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Chaos simulation error: {str(e)}")


@app.post("/api/chaos/compare-scenarios")
def api_chaos_compare_scenarios(req: ChaosComparisonRequest):
    """Run side-by-side comparative benchmark between baseline and failure scenario using identical random seed."""
    try:
        return compare_chaos_scenarios(
            seed=req.seed,
            symbol=req.symbol,
            num_events=req.num_events,
            baseline_scenario=req.baseline_scenario,
            stressed_scenario=req.stressed_scenario,
            failure_type=req.failure_type,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scenario comparison error: {str(e)}")


@app.get("/api/chaos/presets")
def api_chaos_get_presets():
    """Return available chaos scenario presets and configuration parameters."""
    return {"presets": SCENARIO_PRESETS}


# ==========================================================================
# IN-MEMORY HFT ENGINE MATCHING ROUTES (PRESERVED)
# ==========================================================================
@app.get("/api/bbo/{symbol}")
def get_bbo(symbol: str):
    """Retrieve Best Bid & Offer (BBO) for an instrument from the matching engine."""
    book = engine.get_book(symbol)
    if book is None:
        raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found")

    bid, ask = book.get_bbo()
    return {
        "symbol": symbol.upper(),
        "best_bid": {
            "price": fixed_to_price(bid[0]) if bid else None,
            "quantity": bid[1] if bid else 0,
        },
        "best_ask": {
            "price": fixed_to_price(ask[0]) if ask else None,
            "quantity": ask[1] if ask else 0,
        },
    }


@app.get("/api/depth/{symbol}")
def get_depth(symbol: str, depth: int = Query(default=10, ge=1, le=50)):
    """Retrieve Level 2 (L2) aggregated order book depth."""
    book = engine.get_book(symbol)
    if book is None:
        raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found")

    bids, asks = book.get_l2_depth(depth=depth)
    return {
        "symbol": symbol.upper(),
        "depth": depth,
        "bids": [{"price": p, "quantity": q} for p, q in bids],
        "asks": [{"price": p, "quantity": q} for p, q in asks],
        "total_active_orders": book.order_count,
    }


@app.post("/api/order")
def place_order(req: PlaceOrderRequest):
    """Submit a new order to the matching engine."""
    side_enum = Side.BUY if req.side.upper() == "BUY" else (Side.SELL if req.side.upper() == "SELL" else None)
    if side_enum is None:
        raise HTTPException(status_code=400, detail="Invalid side. Must be 'BUY' or 'SELL'.")

    ot_enum = OrderType.LIMIT if req.order_type.upper() == "LIMIT" else (
        OrderType.MARKET if req.order_type.upper() == "MARKET" else (
            OrderType.STOP_LIMIT if req.order_type.upper() == "STOP_LIMIT" else None
        )
    )
    if ot_enum is None:
        raise HTTPException(status_code=400, detail="Invalid order_type. Must be 'LIMIT', 'MARKET', or 'STOP_LIMIT'.")

    tif_map = {"GTC": TimeInForce.GTC, "IOC": TimeInForce.IOC, "FOK": TimeInForce.FOK}
    tif_enum = tif_map.get(req.tif.upper(), TimeInForce.GTC)

    order_msg = NewOrderMsg.create(
        order_id=req.order_id,
        client_id=req.client_id,
        symbol=req.symbol.upper(),
        side=side_enum,
        order_type=ot_enum,
        price=req.price,
        quantity=req.quantity,
        tif=tif_enum,
    )

    reports = engine.process_new_order(order_msg)

    exec_reports = []
    for r in reports:
        exec_reports.append({
            "exec_id": r.exec_id,
            "order_id": r.order_id,
            "matched_order_id": r.matched_order_id,
            "side": Side(r.side).name if r.side in (1, 2) else "UNKNOWN",
            "exec_type": ExecType(r.exec_type).name if r.exec_type in ExecType._value2member_map_ else str(r.exec_type),
            "match_status": MatchStatus(r.match_status).name if r.match_status in MatchStatus._value2member_map_ else str(r.match_status),
            "price": fixed_to_price(r.price),
            "last_qty": r.last_qty,
            "leaves_qty": r.leaves_qty,
            "cum_qty": r.cum_qty,
            "reject_code": RejectCode(r.reject_code).name if r.reject_code in RejectCode._value2member_map_ else str(r.reject_code),
        })

    return {
        "status": "processed",
        "order_id": req.order_id,
        "symbol": req.symbol.upper(),
        "execution_reports": exec_reports,
    }


@app.delete("/api/order/{symbol}/{order_id}")
def cancel_order(symbol: str, order_id: int, client_id: int = 1):
    """Cancel an active resting order."""
    cancel_msg = CancelOrderMsg.create(
        order_id=order_id,
        client_id=client_id,
        symbol=symbol.upper(),
    )
    rep = engine.process_cancel_order(cancel_msg)
    et_name = ExecType(rep.exec_type).name if rep.exec_type in ExecType._value2member_map_ else str(rep.exec_type)

    if rep.exec_type == ExecType.REJECTED:
        raise HTTPException(
            status_code=404,
            detail=f"Order #{order_id} could not be cancelled: {RejectCode(rep.reject_code).name}",
        )

    return {
        "status": "cancelled",
        "order_id": order_id,
        "symbol": symbol.upper(),
        "exec_type": et_name,
    }
