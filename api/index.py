"""Single serverless function entry point for Vercel, local dev, and Virtual Paper Trading API."""

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure both api folder and root directory are in sys.path
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
    price_to_fixed,
    symbol_to_int,
)

app = FastAPI(
    title="ChronosMatch: Zero-Copy HFT Engine & Paper Trading API",
    description="Ultra-low-latency electronic trading matching engine backend and virtual paper trading platform",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS for frontend flexibility
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
    order_type: str = Field(default="LIMIT", description="'LIMIT' or 'MARKET'")
    price: float = Field(default=0.0, description="Limit price (ignored for MARKET orders)")
    quantity: int = Field(..., gt=0, description="Order quantity")
    tif: str = Field(default="GTC", description="'GTC', 'IOC', or 'FOK'")


class CancelOrderRequest(BaseModel):
    order_id: int
    symbol: str = "BTCUSDT"
    client_id: int = 1


class VirtualAuthRequest(BaseModel):
    email: str = Field(..., description="User email address")
    name: str = Field(default="Trader", description="User display name")
    password: str = Field(default="password123", description="User password")
    color: Optional[str] = Field(default="#3b82f6", description="User avatar color")


class VirtualTradeRequest(BaseModel):
    email: str = Field(..., description="User email address")
    symbol: str = Field(..., description="Stock symbol (e.g. RELIANCE, TCS, AAPL)")
    action: str = Field(..., description="'BUY' or 'SELL'")
    order_type: str = Field(default="MARKET", description="'MARKET' or 'LIMIT'")
    price: float = Field(..., gt=0, description="Execution price in INR")
    quantity: float = Field(..., gt=0, description="Number of shares/units to trade")
    order_id: Optional[str] = Field(default=None, description="Optional custom order ID")


class WatchlistToggleRequest(BaseModel):
    email: str = Field(..., description="User email address")
    symbol: str = Field(..., description="Stock symbol to toggle")


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
            "Persistent SQLite Portfolio & Transaction Storage",
            "Holdings & P/L (Realized & Unrealized) Tracking",
            "Watchlist and Live Search",
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


@app.get("/api/virtual/portfolio/{email}")
def get_virtual_portfolio(email: str):
    """Retrieve live user portfolio, available cash, total invested, and real-time unrealized & realized P/L."""
    quotes = market_data_service.get_all_quotes()
    prices_map = {q["symbol"]: q["price"] for q in quotes}
    portfolio = db.get_portfolio(email, prices_map=prices_map)
    return portfolio


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
            order_id=req.order_id,
        )
        return {"status": "success", "trade": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/virtual/orders/{email}")
def get_virtual_orders(email: str, limit: int = Query(default=50, ge=1, le=200)):
    """Retrieve user's virtual order and trade transaction history."""
    return db.get_orders(email, limit=limit)


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
        OrderType.MARKET if req.order_type.upper() == "MARKET" else None
    )
    if ot_enum is None:
        raise HTTPException(status_code=400, detail="Invalid order_type. Must be 'LIMIT' or 'MARKET'.")

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
