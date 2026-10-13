"""FastAPI application for ChronosMatch Zero-Copy HFT Engine."""

import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure src is in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from api.dashboard import get_dashboard_html
from chronosmatch.engine import MatchingEngine
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
    title="ChronosMatch: Zero-Copy HFT Engine API",
    description="Ultra-low-latency electronic trading matching engine backend",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Global engine instance
engine = MatchingEngine()
_start_time = time.time()

# Pre-populate sample books
for default_sym in ["BTCUSDT", "ETHUSDT", "AAPL"]:
    book = engine.get_or_create_book(default_sym)
    # Seed initial resting orders
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


@app.get("/", response_model=None)
def read_root(request: Request):
    """Serve interactive web trading terminal to browsers, or JSON to API callers."""
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return HTMLResponse(content=get_dashboard_html())
    return {
        "service": "ChronosMatch: Zero-Copy HFT Matching Engine",
        "status": "online",
        "uptime_seconds": round(time.time() - _start_time, 2),
        "docs_url": "/docs",
        "dashboard_url": "/dashboard",
        "supported_features": [
            "Price-Time Priority (FIFO)",
            "Zero-Copy Memory Semantics",
            "SPSC Shared-Memory Ring Buffer",
            "Binary Write-Ahead Log (WAL)",
            "Limit, Market, IOC, FOK Orders",
        ],
    }


@app.get("/dashboard", response_class=HTMLResponse)
def get_dashboard():
    """Direct URL for web trading terminal UI."""
    return HTMLResponse(content=get_dashboard_html())


@app.get("/health")
def health_check():
    return {"status": "ok", "timestamp": time.time_ns()}


@app.get("/api/bbo/{symbol}")
def get_bbo(symbol: str):
    """Retrieve Best Bid & Offer (BBO) for an instrument."""
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