"""Real-Time Market Data Service for ChronosMatch Virtual Paper Trading.

Integrates with market data APIs (Yahoo Finance / Free-tier feeds) with in-memory
caching, fallback resilience, and support for Indian equities, Global tech, and Crypto.
"""

import datetime
import os
import time
from typing import Any, Dict, List, Optional

import httpx

# Catalog of supported trading instruments
INSTRUMENT_CATALOG = [
    {
        "symbol": "RELIANCE",
        "name": "Reliance Industries",
        "ticker": "RELIANCE",
        "category": "Indian Equities",
        "yahoo_symbol": "RELIANCE.NS",
        "currency": "INR",
        "base_price": 1184.50,
        "tick_size": 0.05,
    },
    {
        "symbol": "TCS",
        "name": "Tata Consultancy Services",
        "ticker": "TCS",
        "category": "Indian Equities",
        "yahoo_symbol": "TCS.NS",
        "currency": "INR",
        "base_price": 2506.90,
        "tick_size": 0.05,
    },
    {
        "symbol": "INFY",
        "name": "Infosys Ltd",
        "ticker": "INFY",
        "category": "Indian Equities",
        "yahoo_symbol": "INFY.NS",
        "currency": "INR",
        "base_price": 1153.35,
        "tick_size": 0.05,
    },
    {
        "symbol": "HDFCBANK",
        "name": "HDFC Bank Ltd",
        "ticker": "HDFCBANK",
        "category": "Indian Equities",
        "yahoo_symbol": "HDFCBANK.NS",
        "currency": "INR",
        "base_price": 694.05,
        "tick_size": 0.05,
    },
    {
        "symbol": "ICICIBANK",
        "name": "ICICI Bank Ltd",
        "ticker": "ICICIBANK",
        "category": "Indian Equities",
        "yahoo_symbol": "ICICIBANK.NS",
        "currency": "INR",
        "base_price": 1398.50,
        "tick_size": 0.05,
    },
    {
        "symbol": "SBIN",
        "name": "State Bank of India",
        "ticker": "SBIN",
        "category": "Indian Equities",
        "yahoo_symbol": "SBIN.NS",
        "currency": "INR",
        "base_price": 970.00,
        "tick_size": 0.05,
    },
    {
        "symbol": "MARUTI",
        "name": "Maruti Suzuki India",
        "ticker": "MARUTI",
        "category": "Indian Equities",
        "yahoo_symbol": "MARUTI.NS",
        "currency": "INR",
        "base_price": 11170.00,
        "tick_size": 0.50,
    },
    {
        "symbol": "ITC",
        "name": "ITC Limited",
        "ticker": "ITC",
        "category": "Indian Equities",
        "yahoo_symbol": "ITC.NS",
        "currency": "INR",
        "base_price": 258.90,
        "tick_size": 0.05,
    },
    {
        "symbol": "TATAPOWER",
        "name": "Tata Power Company",
        "ticker": "TATAPOWER",
        "category": "Indian Equities",
        "yahoo_symbol": "TATAPOWER.NS",
        "currency": "INR",
        "base_price": 382.40,
        "tick_size": 0.05,
    },
    {
        "symbol": "WIPRO",
        "name": "Wipro Limited",
        "ticker": "WIPRO",
        "category": "Indian Equities",
        "yahoo_symbol": "WIPRO.NS",
        "currency": "INR",
        "base_price": 190.41,
        "tick_size": 0.05,
    },
    {
        "symbol": "AAPL",
        "name": "Apple Inc.",
        "ticker": "AAPL",
        "category": "Global Tech",
        "yahoo_symbol": "AAPL",
        "currency": "USD",
        "base_price": 343.99,
        "tick_size": 0.01,
    },
    {
        "symbol": "MSFT",
        "name": "Microsoft Corporation",
        "ticker": "MSFT",
        "category": "Global Tech",
        "yahoo_symbol": "MSFT",
        "currency": "USD",
        "base_price": 435.50,
        "tick_size": 0.01,
    },
    {
        "symbol": "TSLA",
        "name": "Tesla Inc.",
        "ticker": "TSLA",
        "category": "Global Tech",
        "yahoo_symbol": "TSLA",
        "currency": "USD",
        "base_price": 240.20,
        "tick_size": 0.01,
    },
    {
        "symbol": "NVDA",
        "name": "NVIDIA Corporation",
        "ticker": "NVDA",
        "category": "Global Tech",
        "yahoo_symbol": "NVDA",
        "currency": "USD",
        "base_price": 138.80,
        "tick_size": 0.01,
    },
    {
        "symbol": "BTCUSDT",
        "name": "Bitcoin (BTC / INR)",
        "ticker": "BTC",
        "category": "Crypto",
        "yahoo_symbol": "BTC-INR",
        "currency": "INR",
        "base_price": 7737300.00,
        "tick_size": 1.00,
    },
    {
        "symbol": "ETHUSDT",
        "name": "Ethereum (ETH / INR)",
        "ticker": "ETH",
        "category": "Crypto",
        "yahoo_symbol": "ETH-INR",
        "currency": "INR",
        "base_price": 285400.00,
        "tick_size": 0.50,
    },
    {
        "symbol": "SOLUSDT",
        "name": "Solana (SOL / INR)",
        "ticker": "SOL",
        "category": "Crypto",
        "yahoo_symbol": "SOL-INR",
        "currency": "INR",
        "base_price": 14200.00,
        "tick_size": 0.10,
    },
]

INSTRUMENT_MAP = {inst["symbol"]: inst for inst in INSTRUMENT_CATALOG}


class MarketDataService:
    """Provides cached real-time quotes, historical candles, and instrument search."""

    def __init__(self, cache_ttl_seconds: float = 15.0):
        self.cache_ttl = cache_ttl_seconds
        self._quote_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_timestamps: Dict[str, float] = {}
        self._usd_to_inr: float = 87.20
        self._usd_cache_ts: float = 0.0
        self.api_key = os.environ.get("MARKET_DATA_API_KEY", "")

    def _get_usd_inr_rate(self) -> float:
        """Fetch or return cached USD/INR exchange rate."""
        now = time.time()
        if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("CHRONOS_OFFLINE") or (now - self._usd_cache_ts < 300):  # 5 min cache
            return self._usd_to_inr
        try:
            with httpx.Client(timeout=4.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
                resp = client.get("https://query1.finance.yahoo.com/v8/finance/chart/USDINR=X?interval=1d&range=1d")
                if resp.status_code == 200:
                    meta = resp.json()["chart"]["result"][0]["meta"]
                    price = meta.get("regularMarketPrice")
                    if price and price > 0:
                        self._usd_to_inr = float(price)
                        self._usd_cache_ts = now
        except Exception:
            pass
        return self._usd_to_inr

    def fetch_live_quote(self, symbol: str) -> Dict[str, Any]:
        """Fetch quote from Yahoo Finance API or return cached/fallback data."""
        sym = symbol.strip().upper()
        inst = INSTRUMENT_MAP.get(sym)
        if not inst:
            # Fallback mock for arbitrary symbol
            return {
                "symbol": sym,
                "name": sym,
                "ticker": sym,
                "price": 100.0,
                "currency": "INR",
                "change_val": 0.0,
                "change_pct": 0.0,
                "open_price": 100.0,
                "day_high": 105.0,
                "day_low": 95.0,
                "volume": 10000,
                "is_live": False,
                "data_source": "Demo / Unsupported Instrument",
                "last_updated": datetime.datetime.now().strftime("%H:%M:%S IST"),
            }

        now = time.time()
        cached = self._quote_cache.get(sym)
        if cached and (now - self._cache_timestamps.get(sym, 0)) < self.cache_ttl:
            return cached

        yahoo_sym = inst["yahoo_symbol"]
        usd_rate = self._get_usd_inr_rate()

        if not (os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("CHRONOS_OFFLINE")):
            try:
                with httpx.Client(timeout=4.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
                    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_sym}?interval=1d&range=1d"
                    resp = client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        res = data["chart"]["result"][0]
                        meta = res["meta"]

                        raw_price = meta.get("regularMarketPrice") or inst["base_price"]
                        prev_close = meta.get("chartPreviousClose") or raw_price
                        raw_open = meta.get("regularMarketOpen") or raw_price
                        raw_high = meta.get("regularMarketDayHigh") or raw_price
                        raw_low = meta.get("regularMarketDayLow") or raw_price
                        volume = meta.get("regularMarketVolume") or 0

                        # Convert US equities from USD to INR so terminal is unified in INR
                        multiplier = usd_rate if inst["currency"] == "USD" else 1.0

                        price_inr = round(raw_price * multiplier, 2)
                        prev_close_inr = round(prev_close * multiplier, 2)
                        open_inr = round(raw_open * multiplier, 2)
                        high_inr = round(raw_high * multiplier, 2)
                        low_inr = round(raw_low * multiplier, 2)

                        change_val = round(price_inr - prev_close_inr, 2)
                        change_pct = round((change_val / prev_close_inr * 100) if prev_close_inr > 0 else 0.0, 2)

                        quote_data = {
                            "symbol": inst["symbol"],
                            "name": inst["name"],
                            "ticker": inst["ticker"],
                            "category": inst["category"],
                            "price": price_inr,
                            "native_price": round(raw_price, 2),
                            "native_currency": inst["currency"],
                            "currency": "INR",
                            "change_val": change_val,
                            "change_pct": change_pct,
                            "open_price": open_inr,
                            "day_high": high_inr,
                            "day_low": low_inr,
                            "volume": volume,
                            "is_live": True,
                            "data_source": "Live Exchange (Yahoo Finance Feed)",
                            "last_updated": datetime.datetime.now().strftime("%H:%M:%S IST"),
                        }

                        self._quote_cache[sym] = quote_data
                        self._cache_timestamps[sym] = now
                        return quote_data
            except Exception:
                pass

        # Fallback if network request times out or is offline
        usd_rate = self._get_usd_inr_rate()
        multiplier = usd_rate if inst["currency"] == "USD" else 1.0
        fallback_price = round(inst["base_price"] * multiplier, 2)

        fallback_data = {
            "symbol": inst["symbol"],
            "name": inst["name"],
            "ticker": inst["ticker"],
            "category": inst["category"],
            "price": fallback_price,
            "native_price": inst["base_price"],
            "native_currency": inst["currency"],
            "currency": "INR",
            "change_val": 0.0,
            "change_pct": 0.0,
            "open_price": fallback_price,
            "day_high": round(fallback_price * 1.015, 2),
            "day_low": round(fallback_price * 0.985, 2),
            "volume": 250000,
            "is_live": False,
            "data_source": "Demo / Cached Baseline (Free Tier Limit / Offline)",
            "last_updated": datetime.datetime.now().strftime("%H:%M:%S IST"),
        }
        self._quote_cache[sym] = fallback_data
        self._cache_timestamps[sym] = now
        return fallback_data

    def get_all_quotes(self) -> List[Dict[str, Any]]:
        """Fetch quotes for all catalog instruments concurrently."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        symbols = [inst["symbol"] for inst in INSTRUMENT_CATALOG]
        results_map = {}

        # First populate from existing valid cache
        now = time.time()
        to_fetch = []
        for sym in symbols:
            cached = self._quote_cache.get(sym)
            if cached and (now - self._cache_timestamps.get(sym, 0)) < self.cache_ttl:
                results_map[sym] = cached
            else:
                to_fetch.append(sym)

        if to_fetch:
            with ThreadPoolExecutor(max_workers=min(8, len(to_fetch))) as executor:
                future_to_sym = {executor.submit(self.fetch_live_quote, sym): sym for sym in to_fetch}
                for future in as_completed(future_to_sym):
                    sym = future_to_sym[future]
                    try:
                        results_map[sym] = future.result()
                    except Exception:
                        results_map[sym] = self.fetch_live_quote(sym)

        # Return in original catalog order
        return [results_map.get(sym) or self.fetch_live_quote(sym) for sym in symbols]

    def get_history(self, symbol: str, period: str = "1M") -> Dict[str, Any]:
        """Fetch historical candle / line chart series from Yahoo Finance or fallback."""
        sym = symbol.strip().upper()
        inst = INSTRUMENT_MAP.get(sym) or INSTRUMENT_CATALOG[0]
        yahoo_sym = inst.get("yahoo_symbol", "RELIANCE.NS")

        # Map period to interval and range
        period_map = {
            "1D": ("5m", "1d"),
            "1W": ("15m", "5d"),
            "1M": ("1d", "1mo"),
            "1Y": ("1wk", "1y"),
            "ALL": ("1mo", "5y"),
        }
        interval, rng = period_map.get(period.upper(), ("1d", "1mo"))
        usd_rate = self._get_usd_inr_rate()
        multiplier = usd_rate if inst["currency"] == "USD" else 1.0

        try:
            with httpx.Client(timeout=5.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
                url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_sym}?interval={interval}&range={rng}"
                resp = client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    res = data["chart"]["result"][0]
                    timestamps = res.get("timestamp", [])
                    raw_closes = res["indicators"]["quote"][0].get("close", [])

                    points = []
                    for ts, c in zip(timestamps, raw_closes):
                        if c is not None:
                            points.append({
                                "time": ts,
                                "price": round(c * multiplier, 2),
                            })

                    if points:
                        return {
                            "symbol": sym,
                            "period": period.upper(),
                            "interval": interval,
                            "points": points,
                            "data_source": "Live Exchange (Yahoo Finance)",
                            "is_live": True,
                        }
        except Exception:
            pass

        # Fallback realistic chart generator for offline mode
        base_p = self.fetch_live_quote(sym)["price"]
        points = []
        count = 30 if period == "1M" else (24 if period == "1D" else 52)
        cur = base_p * 0.94
        now_ts = int(time.time())
        step = 86400 if period == "1M" else (1800 if period == "1D" else 604800)

        for i in range(count):
            t = now_ts - (count - i) * step
            # Smooth drift towards base price
            drift = (base_p - cur) / (count - i + 1)
            noise = (hash(f"{sym}_{i}_{period}") % 100 - 50) / 100.0 * (base_p * 0.01)
            cur = round(cur + drift + noise, 2)
            points.append({"time": t, "price": cur})

        points[-1]["price"] = base_p
        return {
            "symbol": sym,
            "period": period.upper(),
            "interval": interval,
            "points": points,
            "data_source": "Cached / Historical Baseline",
            "is_live": False,
        }

    def search_instruments(self, query: str = "", category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search and filter catalog instruments by symbol or company name."""
        q = query.strip().lower()
        results = []
        quotes = self.get_all_quotes()

        for quote in quotes:
            inst = INSTRUMENT_MAP.get(quote["symbol"], {})
            cat = inst.get("category", "")

            if category and category.lower() != "all" and cat.lower() != category.lower():
                continue

            if not q or q in quote["symbol"].lower() or q in quote["name"].lower() or q in inst.get("ticker", "").lower():
                results.append(quote)

        return results


# Global market data service instance
market_data_service = MarketDataService()
