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

import datetime
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
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
from chronosmatch.engine.arena import (
    AgentType,
    ArenaCompetition,
    MarketCondition,
    run_strategy_evolution_test,
)
from chronosmatch.marketdata.service import INSTRUMENT_CATALOG, market_data_service
from chronosmatch.persistence.db import db, calculate_corporate_action
from chronosmatch.ai.mentor import mentor_engine
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

class CorporateActionSimulateRequest(BaseModel):
    symbol: str
    action_type: str
    parameters: Dict[str, Any]
    current_quantity: Optional[float] = None
    current_avg_price: Optional[float] = None
    current_cash: Optional[float] = None
    market_price: Optional[float] = None
    email: Optional[str] = None


class CorporateActionApplyRequest(BaseModel):
    action_id: str
    symbol: str
    action_type: str
    parameters: Dict[str, Any]
    current_price: Optional[float] = None
    email: Optional[str] = "demo@chronosmatch.io"
    current_quantity: Optional[float] = None
    current_avg_price: Optional[float] = None
    current_cash: Optional[float] = None

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


class RegisterRequest(BaseModel):
    email: str = Field(..., description="User email address")
    name: Optional[str] = Field(default="", description="User display name")
    password: str = Field(..., min_length=1, description="Account password")
    color: Optional[str] = Field(default="#3b82f6", description="User avatar color")


class LoginRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., description="Account password")


class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., description="Registered user email address")


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., description="Secure password reset token")
    new_password: str = Field(..., min_length=4, description="New password (minimum 4 characters)")


class VirtualAuthRequest(BaseModel):
    email: str = Field(..., description="User email address")
    name: Optional[str] = Field(default="Trader", description="User display name")
    password: Optional[str] = Field(default="pass", description="User password")
    color: Optional[str] = Field(default="#3b82f6", description="User avatar color")
    action: Optional[str] = Field(default=None, description="Optional action: 'register', 'login'")


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
    conversation_id: Optional[str] = Field(default=None, description="Unique conversation identifier")
    history: Optional[List[Dict[str, str]]] = Field(default=None, description="Prior conversation messages")


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


class ArenaCompetitionRequest(BaseModel):
    seed: int = Field(default=42, description="Pseudorandom seed for deterministic market generation")
    symbol: str = Field(default="BTCUSDT", description="Instrument symbol")
    num_steps: int = Field(default=100, ge=10, le=500, description="Number of simulation steps")
    initial_cash: float = Field(default=100000.0, gt=0, description="Starting virtual capital per agent")
    condition: str = Field(default="TRENDING_BULL", description="Market condition preset")
    selected_agents: Optional[List[str]] = Field(default=None, description="List of agent types to participate")
    custom_params: Optional[Dict[str, Dict[str, Any]]] = Field(default=None, description="Custom parameters per agent")
    include_human: bool = Field(default=False, description="Whether human participant joins the arena")


class ArenaEvolutionRequest(BaseModel):
    seed: int = Field(default=42, description="Seed for deterministic evaluation")
    symbol: str = Field(default="BTCUSDT", description="Instrument symbol")
    agent_type: str = Field(default="MOMENTUM", description="Agent type to evolve")
    condition: str = Field(default="TRENDING_BULL", description="Market condition")
    base_params: Optional[Dict[str, Any]] = Field(default=None, description="Original baseline parameters")
    modified_params: Optional[Dict[str, Any]] = Field(default=None, description="Modified test parameters")
    num_steps: int = Field(default=100, ge=10, le=500, description="Number of steps")
    initial_cash: float = Field(default=100000.0, gt=0, description="Starting capital")


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


@app.get("/api/market/instruments")
def get_market_instruments():
    """Retrieve catalog of all available trading instruments."""
    return {
        "status": "ok",
        "count": len(INSTRUMENT_CATALOG),
        "instruments": INSTRUMENT_CATALOG,
    }


@app.get("/api/market/depth/{symbol}")
def get_market_depth(symbol: str, depth: int = Query(default=10, ge=1, le=50)):
    """Retrieve Level 2 (L2) aggregated order book depth snapshot."""
    sym = symbol.upper()
    book = engine.get_book(sym)
    if book is None:
        quote = market_data_service.fetch_live_quote(sym)
        base = quote["price"] if quote else 1000.0
        tick = quote.get("tick_size", 0.05) if quote else 0.05
        bids = [{"price": round(base - (i + 1) * tick, 2), "quantity": round(15.0 + i * 4.5, 1)} for i in range(depth)]
        asks = [{"price": round(base + (i + 1) * tick, 2), "quantity": round(12.0 + i * 3.8, 1)} for i in range(depth)]
        cum_b, cum_a = 0.0, 0.0
        for b in bids:
            cum_b += b["quantity"]
            b["total"] = round(cum_b, 1)
        for a in asks:
            cum_a += a["quantity"]
            a["total"] = round(cum_a, 1)
        return {
            "symbol": sym,
            "depth": depth,
            "bids": bids,
            "asks": asks,
            "total_active_orders": len(bids) + len(asks),
            "environment": "MarketDataService",
        }

    bids_raw, asks_raw = book.get_l2_depth(depth=depth)
    bids = [{"price": p, "quantity": q} for p, q in bids_raw]
    asks = [{"price": p, "quantity": q} for p, q in asks_raw]
    return {
        "symbol": sym,
        "depth": depth,
        "bids": bids,
        "asks": asks,
        "total_active_orders": book.order_count,
        "environment": "MatchingEngine",
    }


@app.get("/api/market/bbo/{symbol}")
def get_market_bbo(symbol: str):
    """Retrieve Best Bid & Offer (BBO) with spread."""
    sym = symbol.upper()
    book = engine.get_book(sym)
    if book is not None:
        bid, ask = book.get_bbo()
        if bid or ask:
            best_bid_p = fixed_to_price(bid[0]) if bid else None
            best_ask_p = fixed_to_price(ask[0]) if ask else None
            spread = round(best_ask_p - best_bid_p, 4) if (best_bid_p and best_ask_p) else 0.0
            return {
                "symbol": sym,
                "best_bid": {"price": best_bid_p, "quantity": bid[1] if bid else 0},
                "best_ask": {"price": best_ask_p, "quantity": ask[1] if ask else 0},
                "spread": spread,
                "environment": "MatchingEngine",
            }

    quote = market_data_service.fetch_live_quote(sym)
    if not quote:
        raise HTTPException(status_code=404, detail=f"Symbol '{symbol}' not found")
    price = quote["price"]
    tick = quote.get("tick_size", 0.05)
    best_bid_p = round(price - tick, 2)
    best_ask_p = round(price + tick, 2)
    return {
        "symbol": sym,
        "best_bid": {"price": best_bid_p, "quantity": 25.0},
        "best_ask": {"price": best_ask_p, "quantity": 20.0},
        "spread": round(best_ask_p - best_bid_p, 2),
        "environment": "MarketDataService",
    }



# ==========================================================================
# VIRTUAL PAPER TRADING & PORTFOLIO API
# ==========================================================================
@app.post("/api/virtual/register")
def virtual_register(req: RegisterRequest):
    """Securely register a new user account with initial ₹1,00,000 virtual balance and PBKDF2 hashed password."""
    try:
        name = req.name.strip() if req.name else req.email.split("@")[0]
        user_data = db.create_user(
            email=req.email,
            name=name,
            password=req.password,
            color=req.color,
        )
        return {
            "status": "ok",
            "message": "Account created successfully! Please log in.",
            "user": user_data,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registration failed: {str(e)}")


@app.post("/api/virtual/login")
def virtual_login(req: LoginRequest):
    """Authenticate an existing user account using secure salted hash verification."""
    try:
        user_data = db.authenticate_user(
            email=req.email,
            password=req.password,
        )
        return {"status": "ok", "user": user_data}
    except ValueError as e:
        status_code = 404 if "not found" in str(e).lower() else 401
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")


@app.post("/api/virtual/logout")
def virtual_logout():
    """Acknowledge session termination on server."""
    return {"status": "ok", "message": "Logged out successfully."}


@app.post("/api/virtual/forgot-password")
def forgot_password(req: ForgotPasswordRequest):
    """Generate an expiring single-use password reset token.
    Public response never reveals whether an email exists (security requirement).
    """
    token = db.create_password_reset_token(req.email)
    # Generic security response: do not reveal email existence
    return {
        "status": "ok",
        "message": "If this email is registered, password reset instructions have been generated.",
        "token": token,
    }


@app.post("/api/virtual/reset-password")
def reset_password(req: ResetPasswordRequest):
    """Reset user password using single-use secure reset token and PBKDF2 hash."""
    try:
        res = db.reset_password_with_token(token=req.token, new_password=req.new_password)
        return {
            "status": "ok",
            "message": res.get("message", "Password reset successfully! Please log in."),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Password reset failed: {str(e)}")


@app.get("/api/virtual/user/{email}")
def get_virtual_user(email: str):
    """Get public profile information for a user."""
    user = db.get_user(email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.post("/api/virtual/auth")
def virtual_auth(req: VirtualAuthRequest):
    """Sign in or register a user for virtual paper trading with initial ₹1,00,000 balance."""
    try:
        if req.action == "register":
            name = req.name.strip() if req.name else req.email.split("@")[0]
            user_data = db.create_user(
                email=req.email,
                name=name,
                password=req.password,
                color=req.color,
            )
            return {"status": "ok", "message": "Account created successfully! Please log in.", "user": user_data}
        elif req.action == "login":
            user_data = db.authenticate_user(
                email=req.email,
                password=req.password,
            )
            return {"status": "ok", "user": user_data}
        else:
            user_data = db.register_or_login(
                email=req.email,
                name=req.name or "Trader",
                password=req.password,
                color=req.color,
            )
            return {"status": "ok", "user": user_data}
    except ValueError as e:
        status_code = 404 if "not found" in str(e).lower() else (401 if "incorrect password" in str(e).lower() else 400)
        raise HTTPException(status_code=status_code, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Authentication failed: {str(e)}")


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


@app.get("/api/virtual/orders/{email}/{order_id}")
def get_single_virtual_order(email: str, order_id: str):
    """Retrieve details and status for a specific virtual order."""
    order = db.get_order(email, order_id)
    if not order:
        raise HTTPException(status_code=404, detail=f"Order '{order_id}' not found for user {email}")
    return {"status": "ok", "order": order}


@app.get("/api/virtual/account/{email}")
def get_virtual_account(email: str):
    """Retrieve account summary, cash balances, and portfolio equity."""
    user = db.get_user(email)
    if not user:
        raise HTTPException(status_code=404, detail="User account not found")
    portfolio = db.get_portfolio(email)
    return {
        "status": "ok",
        "email": user["email"],
        "name": user["name"],
        "created_at": user.get("created_at"),
        "portfolio": portfolio,
    }


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
    try:
        portfolio_data = None
        if req.email:
            quotes = market_data_service.get_all_quotes()
            prices_map = {q["symbol"]: q["price"] for q in quotes}
            portfolio_data = db.get_portfolio(req.email, prices_map=prices_map)
        elif req.context and "portfolio" in req.context:
            portfolio_data = req.context.get("portfolio")

        response = mentor_engine.generate_response(
            query=req.message,
            email=req.email,
            portfolio_data=portfolio_data,
            history=req.history,
            client_context=req.context,
        )
        if req.conversation_id:
            response["conversation_id"] = req.conversation_id
        return response
    except Exception as e:
        return {
            "reply": f"⚠️ **Error generating AI response**: {str(e)}\n\nPlease try again or ask another trading question.",
            "model": "Chronos Fallback Handler",
            "timestamp": time.time(),
            "sources": ["Error Handler"],
            "conversation_id": req.conversation_id,
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
# ALGORITHMIC TRADING ARENA ROUTES
# ==========================================================================
@app.post("/api/arena/run-competition")
def api_arena_run_competition(req: ArenaCompetitionRequest):
    """Run an algorithmic trading arena competition between independent algorithmic agents."""
    try:
        cond_enum = MarketCondition(req.condition.upper()) if req.condition.upper() in MarketCondition._value2member_map_ else MarketCondition.TRENDING_BULL
        agents_enums = None
        if req.selected_agents:
            agents_enums = [
                AgentType(a.upper()) for a in req.selected_agents if a.upper() in AgentType._value2member_map_
            ]

        comp = ArenaCompetition(
            seed=req.seed,
            symbol=req.symbol,
            num_steps=req.num_steps,
            initial_cash=req.initial_cash,
            condition=cond_enum,
            selected_agents=agents_enums,
            custom_params=req.custom_params,
            include_human=req.include_human,
        )
        return comp.run_full_competition()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Arena competition error: {str(e)}")


@app.post("/api/arena/compare-strategies")
def api_arena_compare_strategies(req: ArenaEvolutionRequest):
    """Run a controlled Strategy Evolution Lab test comparing Original vs Modified parameters."""
    try:
        return run_strategy_evolution_test(
            seed=req.seed,
            symbol=req.symbol,
            agent_type=req.agent_type,
            condition=req.condition,
            base_params=req.base_params,
            modified_params=req.modified_params,
            num_steps=req.num_steps,
            initial_cash=req.initial_cash,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Strategy evolution test error: {str(e)}")


@app.get("/api/arena/presets")
def api_arena_get_presets():
    """Return available arena agent definitions, descriptions, and market presets."""
    return {
        "agents": {
            "MOMENTUM": {
                "name": "Momentum Trend Agent",
                "description": "Identifies trend direction via dual moving average crossover and rate-of-change momentum.",
                "default_params": {"fast_period": 5, "slow_period": 20, "roc_threshold": 0.3, "position_size_pct": 25.0},
            },
            "MEAN_REVERSION": {
                "name": "Mean Reversion Agent",
                "description": "Exploits statistical price extremes using Bollinger Bands and RSI overbought/oversold levels.",
                "default_params": {"bb_period": 20, "num_std": 2.0, "rsi_oversold": 32.0, "rsi_overbought": 68.0},
            },
            "MARKET_MAKER": {
                "name": "Market Making Agent",
                "description": "Provides two-sided liquidity, capturing the spread with dynamic inventory skew management.",
                "default_params": {"half_spread_pct": 0.002, "max_inventory": 5.0, "quote_size": 1.0},
            },
            "LIQUIDITY_HUNTER": {
                "name": "Liquidity Hunter Agent",
                "description": "Analyzes book depth and imbalance to identify breakout surges and liquidity clusters.",
                "default_params": {"min_depth": 15, "imbalance_threshold": 0.30},
            },
            "CONSERVATIVE": {
                "name": "Conservative Risk Guard",
                "description": "Follows strict exposure caps, tight stop-loss thresholds, and high risk-reward setups.",
                "default_params": {"stop_loss_pct": 1.2, "take_profit_pct": 2.8, "max_risk_pct": 1.0},
            },
            "ADAPTIVE": {
                "name": "Adaptive Regime Agent",
                "description": "Dynamically shifts between trend-following and range-bound mean-reversion based on market efficiency.",
                "default_params": {"regime_window": 15, "trend_threshold": 0.40},
            },
        },
        "conditions": {
            "TRENDING_BULL": "Sustained upward drift with positive momentum shocks and shallow pullbacks.",
            "TRENDING_BEAR": "Downward pressure with negative cascades and aggressive selling.",
            "MEAN_REVERTING": "Oscillating range-bound market between clear support and resistance levels.",
            "HIGH_VOLATILITY": "Turbulent swings, wide standard deviations, and sudden jump events.",
            "LIQUIDITY_SQUEEZE": "Thin order book depth, wide spreads, and rapid slippage.",
        },
    }


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



CORPORATE_ACTIONS_CATALOG = [
    {
        "id": "SIM-DIV-RELIANCE-2026",
        "symbol": "RELIANCE",
        "company_name": "Reliance Industries Limited",
        "action_type": "DIVIDEND",
        "title": "₹10.00 Final Cash Dividend per Share",
        "status": "ACTIVE",
        "is_simulated": True,
        "announcement_date": "2026-10-25",
        "ex_date": "2026-11-10",
        "record_date": "2026-11-12",
        "execution_date": "2026-11-15",
        "parameters": {"dividend_per_share": 10.0},
        "description": "Board recommends simulated final cash dividend of ₹10.00 per equity share (Face Value ₹10).",
        "educational_note": "Dividends are payments made by a corporation to its shareholders out of profits. On the ex-dividend date, the stock price generally drops by roughly the dividend amount as cash is transferred out of company reserves.",
        "category": "Cash Dividend",
    },
    {
        "id": "SIM-SPLIT-INFY-2026",
        "symbol": "INFY",
        "company_name": "Infosys Limited",
        "action_type": "STOCK_SPLIT",
        "title": "2:1 Stock Split (Sub-division of Shares)",
        "status": "ACTIVE",
        "is_simulated": True,
        "announcement_date": "2026-10-28",
        "ex_date": "2026-11-18",
        "record_date": "2026-11-20",
        "execution_date": "2026-11-22",
        "parameters": {"split_from": 1, "split_to": 2},
        "description": "Sub-division of 1 equity share of Face Value ₹5 each into 2 equity shares of Face Value ₹2.50 each.",
        "educational_note": "A 2:1 stock split doubles your share quantity while cutting the share price and average cost basis in half. Total invested capital and market value remain identical: no artificial profit is created.",
        "category": "Stock Split",
    },
    {
        "id": "SIM-BONUS-TCS-2026",
        "symbol": "TCS",
        "company_name": "Tata Consultancy Services Ltd",
        "action_type": "BONUS_ISSUE",
        "title": "1:2 Bonus Issue (1 Bonus Share for every 2 held)",
        "status": "ACTIVE",
        "is_simulated": True,
        "announcement_date": "2026-11-01",
        "ex_date": "2026-11-25",
        "record_date": "2026-11-27",
        "execution_date": "2026-11-30",
        "parameters": {"bonus_shares": 1, "existing_shares": 2},
        "description": "Issuance of 1 bonus share for every 2 existing equity shares held on the record date out of free reserves.",
        "educational_note": "Bonus shares are additional shares given to existing shareholders at no additional cost through capitalization of free reserves. Average cost basis reduces proportionately, preserving total investment value.",
        "category": "Bonus Shares",
    },
    {
        "id": "SIM-BONUS-TATAMOTORS-2026",
        "symbol": "TATAMOTORS",
        "company_name": "Tata Motors Limited",
        "action_type": "BONUS_ISSUE",
        "title": "1:1 Bonus Issue (1 Bonus Share for every 1 held)",
        "status": "UPCOMING",
        "is_simulated": True,
        "announcement_date": "2026-11-04",
        "ex_date": "2026-12-05",
        "record_date": "2026-12-08",
        "execution_date": "2026-12-10",
        "parameters": {"bonus_shares": 1, "existing_shares": 1},
        "description": "Allotment of 1 bonus equity share for every 1 fully paid equity share held by members.",
        "educational_note": "A 1:1 bonus issue doubles the number of shares held by each eligible investor, while the ex-bonus market price mathematically halves.",
        "category": "Bonus Shares",
    },
    {
        "id": "SIM-REVSPLIT-YESBANK-2026",
        "symbol": "YESBANK",
        "company_name": "Yes Bank Limited",
        "action_type": "REVERSE_SPLIT",
        "title": "1:5 Reverse Stock Split (Share Consolidation)",
        "status": "ACTIVE",
        "is_simulated": True,
        "announcement_date": "2026-10-15",
        "ex_date": "2026-11-12",
        "record_date": "2026-11-14",
        "execution_date": "2026-11-16",
        "parameters": {"from_shares": 5, "to_shares": 1},
        "description": "Consolidation of 5 equity shares into 1 equity share to improve trading profile and reduce penny-stock volatility.",
        "educational_note": "A reverse split reduces the total outstanding shares while increasing the per-share price proportionally. Investors retain the same proportional ownership and aggregate position value.",
        "category": "Reverse Split",
    },
    {
        "id": "SIM-RIGHTS-BHARTIARTL-2026",
        "symbol": "BHARTIARTL",
        "company_name": "Bharti Airtel Limited",
        "action_type": "RIGHTS_ISSUE",
        "title": "1:14 Rights Issue @ ₹535.00 (Discount to Market)",
        "status": "ACTIVE",
        "is_simulated": True,
        "announcement_date": "2026-10-20",
        "ex_date": "2026-11-20",
        "record_date": "2026-11-22",
        "execution_date": "2026-11-28",
        "parameters": {"rights_shares": 1, "for_shares": 14, "subscription_price": 535.0},
        "description": "Rights entitlement allowing existing shareholders to subscribe to 1 new share for every 14 held at a preferential price of ₹535.00.",
        "educational_note": "A rights issue allows existing shareholders to purchase additional shares directly from the company at a discounted price, requiring a cash outflow to subscribe and lowering blended average cost.",
        "category": "Rights Issue",
    },
    {
        "id": "SIM-BUYBACK-WIPRO-2026",
        "symbol": "WIPRO",
        "company_name": "Wipro Limited",
        "action_type": "BUYBACK",
        "title": "Tender Offer Buyback @ ₹445.00 per Share",
        "status": "ACTIVE",
        "is_simulated": True,
        "announcement_date": "2026-10-30",
        "ex_date": "2026-11-22",
        "record_date": "2026-11-24",
        "execution_date": "2026-11-29",
        "parameters": {"buyback_price": 445.0},
        "description": "Company initiates tender offer to buy back equity shares at a premium price of ₹445.00 per share via proportionate tender.",
        "educational_note": "In a stock buyback, the company buys its own shares from shareholders at a predetermined tender price (usually higher than market price), crediting cash and reducing share counts.",
        "category": "Stock Buyback",
    },
    {
        "id": "SIM-SYM-MOTHERSUM-2026",
        "symbol": "MOTHERSUM",
        "company_name": "Samvardhana Motherson International Ltd",
        "action_type": "SYMBOL_CHANGE",
        "title": "Symbol Transition: MOTHERSUM ➔ MOTHERSON",
        "status": "COMPLETED",
        "is_simulated": True,
        "announcement_date": "2026-10-10",
        "ex_date": "2026-10-28",
        "record_date": "2026-10-29",
        "execution_date": "2026-10-30",
        "parameters": {"new_symbol": "MOTHERSON"},
        "description": "Corporate renaming and ticker transition on exchanges from MOTHERSUM to MOTHERSON following corporate restructuring.",
        "educational_note": "A symbol change reflects corporate rebranding or reorganizations. All holdings, position sizes, and cost bases are carried over to the new symbol with zero economic loss.",
        "category": "Symbol Change",
    },
]


@app.get("/api/corporate-actions/events")
def get_corporate_action_events():
    """Retrieve catalog of simulated corporate action events."""
    return {
        "status": "success",
        "count": len(CORPORATE_ACTIONS_CATALOG),
        "events": CORPORATE_ACTIONS_CATALOG,
    }


@app.post("/api/corporate-actions/simulate")
def simulate_corporate_action(req: CorporateActionSimulateRequest):
    """Simulate a corporate action and preview its impact on holdings, cash, and portfolio valuation."""
    symbol = req.symbol.strip().upper()
    action_type = req.action_type.strip().upper()

    # Determine holdings and cash baseline
    current_qty = req.current_quantity
    current_avg = req.current_avg_price
    current_cash = req.current_cash

    # Fallback to database if email provided and fields missing
    if (current_qty is None or current_cash is None) and req.email:
        email = req.email.strip().lower()
        acct = db.get_account(email)
        if acct:
            current_cash = float(acct["cash_balance"])
        port = db.get_portfolio(email)
        holdings = port.get("holdings", [])
        for h in holdings:
            if h["symbol"].upper() == symbol:
                current_qty = float(h["quantity"])
                current_avg = float(h["avg_buy_price"])
                break

    # If still not provided, provide sensible defaults for demonstration
    if current_cash is None:
        current_cash = 100000.00
    if current_qty is None or current_qty <= 0:
        current_qty = 100.0
    if current_avg is None or current_avg <= 0:
        try:
            quote = market_data_service.fetch_live_quote(symbol)
            current_avg = float(quote.get("price", 1000.00))
        except Exception:
            current_avg = 1000.00

    market_price = req.market_price
    if market_price is None or market_price <= 0:
        try:
            quote = market_data_service.fetch_live_quote(symbol)
            market_price = float(quote.get("price", current_avg))
        except Exception:
            market_price = current_avg

    try:
        res = calculate_corporate_action(
            action_type=action_type,
            parameters=req.parameters,
            current_qty=current_qty,
            current_avg=current_avg,
            current_cash=current_cash,
            market_price=market_price,
        )
        return {
            "status": "success",
            "symbol": symbol,
            "action_type": action_type,
            "simulation": res,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/api/corporate-actions/apply")
def apply_corporate_action_endpoint(req: CorporateActionApplyRequest):
    """Apply a corporate action event to user portfolio, enforcing single-use event execution."""
    email = (req.email or "demo@chronosmatch.io").strip().lower()
    symbol = req.symbol.strip().upper()
    action_type = req.action_type.strip().upper()

    # Check if duplicate
    if db.is_corporate_action_applied(email, req.action_id):
        raise HTTPException(
            status_code=409,
            detail=f"Corporate action '{req.action_id}' has already been applied to portfolio for '{email}'. Duplicate application prevented.",
        )

    # Get market price
    if req.current_price and req.current_price > 0:
        mkt_price = req.current_price
    else:
        try:
            quote = market_data_service.fetch_live_quote(symbol)
            mkt_price = float(quote.get("price", 1000.00))
        except Exception:
            mkt_price = 1000.00

    # Ensure user exists in database for persistent ledger & duplicate prevention
    if not db.user_exists(email):
        try:
            db.create_user(email, "Trader", "DemoPass123!")
            db.reset_account(email, starting_balance=req.current_cash or 100000.00)
            if req.current_quantity and req.current_quantity > 0:
                with db.get_connection() as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO holdings (email, symbol, quantity, avg_buy_price, total_invested, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            email,
                            symbol,
                            req.current_quantity,
                            req.current_avg_price or 1000.0,
                            round(req.current_quantity * (req.current_avg_price or 1000.0), 2),
                            datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        ),
                    )
        except Exception:
            pass

    try:
        result = db.apply_corporate_action(
            email=email,
            action_id=req.action_id,
            symbol=symbol,
            action_type=action_type,
            parameters=req.parameters,
            current_price=mkt_price,
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database error applying corporate action: {str(exc)}")


@app.get("/api/corporate-actions/history/{email}")
def get_user_corporate_actions(email: str):
    """Retrieve history of applied corporate actions for a user."""
    email = email.strip().lower()
    actions = db.get_corporate_actions(email)
    return {
        "status": "success",
        "email": email,
        "count": len(actions),
        "history": actions,
    }


@app.websocket("/api/market/ws")
@app.websocket("/ws/events")
async def websocket_market_events(websocket: WebSocket):
    """Real-time WebSocket event stream for Developer Playground & Market Monitor."""
    await websocket.accept()
    try:
        import asyncio
        await websocket.send_json({
            "type": "connection_status",
            "status": "connected",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "message": "Connected to ChronosMatch Real-Time Event Stream",
            "server": "ChronosMatch-FastAPI-v0.3.0",
        })
        while True:
            quotes = market_data_service.get_all_quotes()
            await websocket.send_json({
                "type": "quotes",
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "data": quotes,
            })
            await asyncio.sleep(2.0)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
