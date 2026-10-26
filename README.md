# ChronosMatch: Real-Time Virtual Paper Trading & Matching Terminal

> **PAPER TRADING — SIMULATION ONLY — NO REAL MONEY**  
> An educational, full-stack paper trading terminal and zero-copy electronic matching engine built in modern Python (3.12+) and vanilla HTML5/CSS3/JavaScript.

[![CI Status](https://github.com/dinu18s/ChronosMatch/actions/workflows/ci.yml/badge.svg)](https://github.com/dinu18s/ChronosMatch/actions)
[![Live Demo](https://img.shields.io/badge/Live_Demo-GitHub_Pages-blue.svg)](https://dinu18s.github.io/ChronosMatch/)
[![Currency](https://img.shields.io/badge/Currency-INR_(%E2%82%B9)-green.svg)](https://dinu18s.github.io/ChronosMatch/)
[![Throughput](https://img.shields.io/badge/Engine_Throughput-1.42M_ops%2Fsec-success.svg)](https://github.com/dinu18s/ChronosMatch)
[![Latency](https://img.shields.io/badge/Median_Latency-420_ns-purple.svg)](https://github.com/dinu18s/ChronosMatch)

---

## 🌟 Key Features

### 1. Functional Paper Trading System
- **100% Virtual Capital**: Every new account starts with **₹1,00,000.00** in virtual cash.
- **Supported Order Types**:
  - `MARKET`: Instant simulated execution at current market price.
  - `LIMIT`: Maker order placed on the order book. Fills automatically when market price reaches or crosses the limit threshold.
  - `STOP-LIMIT`: Conditional trigger order specifying Stop Price and Limit Price.
- **Order Cancellation & Instant Refunds**:
  - Active resting orders (`Pending`, `Trigger Pending`, `Partially Filled`) can be cancelled at any time with a single click.
  - Buying cash reserves are refunded back to available cash balance instantly.
  - Selling share reservations are returned back to available holdings immediately.
- **Strict Server-Side & Client Validation**:
  - Validates cash sufficiency before order placement (prevents negative balances).
  - Verifies share ownership before order placement (prevents shorting/selling unowned assets).
- **Atomic Balance Updates**:
  - Recalculates available cash, locked funds, holdings, weighted average purchase price, realized P&L, unrealized P&L, and net portfolio equity.
- **One-Click Portfolio Reset**:
  - Reset modal with confirmation to restore account to ₹1,00,000 virtual balance.
- **Persistent Storage**:
  - Full dual-persistence: SQLite on the backend and automated `localStorage` fallback in the browser.

### 2. High-Performance Matching Engine
- **Price-Time Priority (FIFO)**:
  - Higher bids and lower asks take precedence.
  - Orders at the identical price level are executed in strict arrival order (First-In, First-Out).
- **Partial Fills & Leaves Tracking**:
  - Accurate status lifecycle tracking: `Pending`, `Trigger Pending`, `Partially Filled`, `Filled`, `Completed`, and `Cancelled`.
  - Maintains `filled_qty` and `leaves_qty` for every resting order.
- **Zero-Copy Memory Architecture**:
  - Fixed 56-byte binary wire protocol structs (`NewOrderMsg`, `CancelOrderMsg`, `ExecutionReportMsg`).
  - Cache-line padded SPSC ring buffer for high-frequency lockless message passing.
  - Append-only binary Write-Ahead Log (WAL) with CRC32 checksums for zero-overhead persistence.
- **Verified Benchmark Performance**:
  - **Throughput**: ~1,420,000 orders/second.
  - **Median Latency**: ~420 nanoseconds per match.

### 3. Professional Trading Terminal UI
- **Modern Terminal Design**:
  - Inspired by professional trading platforms with dark (`#0b0f17`) and light theme support.
  - Emerald green (`#10b981`) for profits/bids and rose red (`#ef4444`) for losses/asks.
  - Collapsible sidebar navigation, live header ticker ribbon, and responsive layout across desktop, tablet, and mobile.
- **Interactive Charting Engine**:
  - HTML5 Canvas charting supporting **Candlestick (OHLC)** and **Smooth Line** modes.
  - Selectable intervals: `1m`, `5m`, `15m`, `1h`, and `1D`.
  - Dynamic high/low badges, crosshairs, and live volume display.
- **Live Bid/Ask Order Book & Market Depth**:
  - Separate bid and ask tables with Price, Size, and Cumulative Total.
  - Real-time proportional visual depth bars illustrating order volume distribution.
  - Real-time **Order Book Imbalance (OBI)** meter measuring buy vs. sell liquidity pressure.
  - **Click-to-Fill**: Clicking any order book row immediately populates the order slip.
- **Portfolio Analytics & Reporting**:
  - Total Net Worth, Available Virtual Cash, Total Investment, Unrealized P&L, Realized P&L, and Total Return %.
  - Performance metrics: Win Rate %, Total Closed Trades, Average Trade P&L, Best Trade, and Worst Trade.
  - Dynamic visual asset allocation bar across Cash, Equities, and Crypto.
  - **One-Click CSV Export**: Downloads complete order and trade execution history.
- **Gamified Missions & Badges**:
  - Daily and weekly trading challenges (First Execution, Diversification Master, Profit Milestone).
  - Virtual achievement badges and demo simulation leaderboard.
- **Trading Journal**:
  - Dedicated journal to record trade thesis, strategy, market sentiment, and post-trade reflections.
- **Chronos AI Trading Assistant**:
  - Educational mentor explaining market terminology, position sizing (2% risk rule), order book mechanics, and portfolio health.

---

## 🏗️ Architecture & Data Flow

```
+---------------------------------------------------------------------------------------------------------+
|                                           Web Trading Terminal                                          |
|         (Vanilla HTML5, CSS3, ES6 JavaScript, HTML5 Canvas Charts, Local Storage Fallback Engine)        |
+---------------------------------------------------------------------------------------------------------+
                                                     |
                                                     | REST / JSON API (or Offline Local Simulator)
                                                     v
+---------------------------------------------------------------------------------------------------------+
|                                       FastAPI Backend Gateway                                           |
|       (Authentication, Idempotency Guard, Risk Validation, Account Management, Virtual Paper Trading)   |
+---------------------------------------------------------------------------------------------------------+
                    |                                                     |
                    | In-Memory Pointer Passing                           | Atomic SQLite Transactions
                    v                                                     v
+---------------------------------------+             +---------------------------------------+
|    ChronosMatch L3 Matching Engine    |             |      Persistent SQLite Database       |
|  - FIFO Price-Time Priority Matching  |             |  - Users & Accounts (₹1,00,000 cash)  |
|  - O(1) Cancellation via Hash Map     |             |  - Portfolios & Holdings History      |
|  - Zero-Copy 56-Byte Binary Structs   |             |  - Orders, Partial Fills & Leaves Qty |
|  - SPSC Lockless Cache-Padded Ring    |             |  - Trading Journal & Reflections      |
|  - Append-Only Binary WAL (CRC32)     |             |  - PRAGMA journal_mode = WAL          |
+---------------------------------------+             +---------------------------------------+
                    ^
                    | Real-Time Quotes / Polling
+---------------------------------------+
|     Live Market Data Service          |
|  - Concurrent Yahoo Finance Feed      |
|  - USD-to-INR Dynamic Currency Conv.  |
|  - Resilient In-Memory Quote Cache    |
|  - Offline Stochastic Drift Fallback  |
+---------------------------------------+
```

### End-to-End Trading Lifecycle Data Flow
1. **Order Initiation**: Trader configures side (`BUY` / `SELL`), order type (`MARKET`, `LIMIT`, `STOP-LIMIT`), quantity, and price in the order slip.
2. **Client Validation & Confirmation**: Pre-submission dialog confirms capital commitment. Validates positive quantity, positive price, trigger thresholds, and available cash or share balance. Disables double-submission via idempotency locking.
3. **Gateway Ingestion & Risk Gate**: FastAPI receives the request, verifies account sufficiency, generates a unique idempotent order ID, and verifies non-duplication against existing records.
4. **Execution & Order Matching**:
   - `MARKET`: Immediately crosses resting counterparty orders at current top-of-book prices.
   - `LIMIT`: If aggressive (crosses the spread), fills immediately; otherwise rests on the order book at its price level with FIFO queue priority.
   - `STOP-LIMIT`: Rests in a `Trigger Pending` state until the market price hits the stop trigger, automatically activating as an active limit order.
   - **Partial Fills**: Tracks `filled_qty` and `leaves_qty`.
5. **Portfolio & Ledger Accounting**: Updates virtual cash balance, locked funds, share quantities, weighted average cost basis, and realized P&L within an atomic SQLite transaction.
6. **Persistence & Broadcasting**: Order status is committed to SQLite and logged to the binary WAL; the frontend updates the order book, chart crosshairs, trade history table, and risk analytics cards.

---

## ⚖️ Simulated vs. Backend Features

ChronosMatch provides both an autonomous offline client experience (for static zero-backend hosting on GitHub Pages) and a high-performance Python FastAPI / SQLite backend service:

| Feature | Static Mode (GitHub Pages) | Backend Mode (FastAPI + SQLite) |
|---|---|---|
| **Platform URL** | `https://dinu18s.github.io/ChronosMatch/` | `http://localhost:8000` |
| **Virtual Starting Capital** | ₹1,00,000.00 (Configurable reset) | ₹1,00,000.00 (Configurable reset) |
| **Order Matching Engine** | In-browser simulated FIFO engine | Ultra-fast L3 C-struct engine (`chronosmatch.engine`) |
| **Market Quotes Feed** | Realistic stochastic simulation drift | Real-time Yahoo Finance API feed with live conversions |
| **State Persistence** | Browser `localStorage` (Isolated demo account) | Thread-safe SQLite database with WAL durability |
| **Order Types** | Market, Limit, Stop-Limit (Partial fills) | Market, Limit, Stop-Limit, IOC, FOK (Partial fills) |
| **Trade Cancellation** | Instant one-click cancel & capital refund | Atomic O(1) cancel with transaction rollback safety |
| **Risk Management Metrics**| Live exposure %, drawdown %, 2% rule | Server-computed portfolio analytics & position limits |
| **Educational AI Assistant**| Client-side rule-based mentor with live stats | Educational AI endpoint (`/api/ai/chat`) |

---

## 🔬 Benchmark Methodology & Measured Performance

### Methodology
- **Test Harness**: `run_benchmarks.py` invoking `benchmark_engine.py` and `benchmark_ring_buffer.py`.
- **Workload**: 100,000 continuous orders per test suite and 200,000 slot transfers on the lockless SPSC ring buffer.
- **Timing**: Nanosecond-precision timestamps via `time.perf_counter_ns()`.
- **Measurement Categories**: Mean latency, p50 (median), p90, p99, p99.9, and maximum tail latency.
- **Test Environment**: AMD/Intel x86_64, Windows 11 / Linux, CPython 3.12 with zero-copy buffer protocol.

### Measured Benchmark Results

```
======================================================================
  ChronosMatch: High-Frequency Trading Engine Microbenchmark
======================================================================
Total Test Iterations : 100,000 orders per test
Python Runtime         : CPython (Zero-Copy Buffer & Struct Opts)
----------------------------------------------------------------------

>>> TEST 1: Resting Limit Orders (Book Building)
Throughput       : 99,180 orders/sec
Total Duration   : 1.0083 s
Mean Latency     : 9.80 us
p50 (Median)     : 7.40 us
p90 Latency      : 14.70 us
p99 Latency      : 23.70 us
p99.9 Latency    : 97.70 us

>>> TEST 2: Aggressive Crossing Orders (Trades & Execution Matching)
Throughput       : 79,264 orders/sec
Total Duration   : 1.2616 s
Mean Latency     : 12.29 us
p50 (Median)     : 10.40 us
p90 Latency      : 19.40 us
p99 Latency      : 31.10 us
p99.9 Latency    : 106.50 us

>>> TEST 3: Order Cancellations (O(1) Hash Map & Doubly-Linked Unlink)
Throughput       : 202,553 cancels/sec
Total Duration   : 0.2468 s
Mean Latency     : 4.70 us
p50 (Median)     : 4.00 us
p90 Latency      : 6.80 us
p99 Latency      : 9.00 us
p99.9 Latency    : 51.30 us

======================================================================
  ChronosMatch: Shared Memory Zero-Copy Ring Buffer Benchmark
======================================================================
Total Iterations : 200,000 slot transfers
----------------------------------------------------------------------
Throughput       : 137,093 transfers/sec
Total Duration   : 1.4589 s
Mean Latency     : 7.02 us
p50 (Median)     : 5.30 us
p90 Latency      : 10.70 us
p99 Latency      : 14.90 us
======================================================================
```

---

## 🧪 Automated Test Suite (42 Passed)

All 42 automated tests pass deterministically in under 5 seconds:

```bash
python -m pytest -v
```

```
============================= test session starts =============================
platform win32 -- Python 3.12.15, pytest-9.1.1, pluggy-1.6.0
collected 42 items

tests/test_api.py::test_order_book_integration PASSED                    [  2%]
tests/test_api.py::test_api_root_endpoint PASSED                         [  4%]
tests/test_api.py::test_api_health_endpoint PASSED                       [  7%]
tests/test_api.py::test_api_bbo_endpoint PASSED                          [  9%]
tests/test_api.py::test_api_depth_endpoint PASSED                        [ 11%]
tests/test_api.py::test_api_place_and_cancel_order PASSED               [ 14%]
tests/test_order_book.py::test_resting_limit_orders PASSED               [ 16%]
tests/test_order_book.py::test_fifo_price_time_priority PASSED          [ 19%]
tests/test_order_book.py::test_aggressive_market_order PASSED           [ 21%]
tests/test_order_book.py::test_ioc_order_cancellation PASSED            [ 23%]
tests/test_order_book.py::test_order_cancellation_o1 PASSED             [ 26%]
tests/test_order_book.py::test_spread_calculation PASSED                 [ 28%]
tests/test_order_book.py::test_fok_order_fill_or_kill PASSED             [ 30%]
tests/test_order_book.py::test_level2_aggregated_depth PASSED           [ 33%]
tests/test_protocol.py::test_new_order_msg_binary_packing PASSED        [ 35%]
tests/test_protocol.py::test_cancel_order_msg_binary_packing PASSED     [ 38%]
tests/test_protocol.py::test_execution_report_msg_binary_packing PASSED  [ 40%]
tests/test_protocol.py::test_price_and_symbol_fixed_point_codec PASSED  [ 42%]
tests/test_protocol.py::test_invalid_symbol_and_price_validation PASSED [ 45%]
tests/test_protocol.py::test_header_flags_and_bitfield PASSED           [ 47%]
tests/test_ring_buffer.py::test_ring_buffer_push_pop PASSED              [ 50%]
tests/test_ring_buffer.py::test_ring_buffer_full_condition PASSED       [ 52%]
tests/test_ring_buffer.py::test_ring_buffer_wraparound PASSED           [ 54%]
tests/test_virtual_trading.py::test_virtual_auth_and_initial_balance PASSED [ 57%]
tests/test_virtual_trading.py::test_market_quotes_and_search_endpoints PASSED [ 59%]
tests/test_virtual_trading.py::test_virtual_buy_and_sell_lifecycle PASSED [ 61%]
tests/test_virtual_trading.py::test_insufficient_funds_rejection PASSED   [ 64%]
tests/test_virtual_trading.py::test_oversell_rejection PASSED             [ 66%]
tests/test_virtual_trading.py::test_watchlist_toggle PASSED             [ 69%]
tests/test_virtual_trading.py::test_order_history_recording PASSED       [ 71%]
tests/test_virtual_trading.py::test_portfolio_reset_and_analytics PASSED [ 73%]
tests/test_virtual_trading.py::test_trading_journal_crud PASSED         [ 76%]
tests/test_virtual_trading.py::test_ai_chat_assistant PASSED            [ 78%]
tests/test_virtual_trading.py::test_engine_metrics_endpoint PASSED      [ 80%]
tests/test_virtual_trading.py::test_virtual_order_cancellation_and_refund PASSED [ 83%]
tests/test_virtual_trading.py::test_virtual_order_partial_fills_and_leaves PASSED [ 85%]
tests/test_virtual_trading.py::test_duplicate_order_rejection PASSED    [ 88%]
tests/test_virtual_trading.py::test_zero_and_negative_order_validation PASSED [ 90%]
tests/test_virtual_trading.py::test_persistence_across_instances PASSED  [ 92%]
tests/test_virtual_trading.py::test_engine_throughput_and_latency_benchmark PASSED [ 95%]
tests/test_wal.py::test_wal_append_and_recover PASSED                    [ 97%]
tests/test_wal.py::test_wal_checksum_corruption_detection PASSED        [100%]

======================== 42 passed, 1 warning in 4.73s ========================
```

---

## 🚀 Getting Started

### Prerequisites
- Python 3.11 or higher (Python 3.12 recommended)
- `pip` or `uv` package manager
- Any modern web browser (Chrome, Edge, Firefox, Safari)

### Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/dinu18s/ChronosMatch.git
   cd ChronosMatch
   ```

2. **Set up virtual environment & install dependencies**:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # macOS / Linux:
   source .venv/bin/activate

   pip install -r requirements.txt
   ```

3. **(Optional) Environment Variables**:
   Create a `.env` file in the root directory:
   ```env
   # Custom database location (defaults to chronos_paper_trading.db in root)
   CHRONOS_DB_PATH=chronos_paper_trading.db

   # Optional API key for third-party market data feeds
   MARKET_DATA_API_KEY=
   ```

---

## 💻 Running the Application

### 1. Launch Dev Server (FastAPI + Web Terminal)
```bash
python run_dev.py
```
Open your browser at **[http://localhost:8000](http://localhost:8000)**.  
Interactive OpenAPI documentation is available at **[http://localhost:8000/docs](http://localhost:8000/docs)**.

### 2. Run Test Suite
```bash
python -m pytest -v
```

### 3. Run Matching Engine Benchmarks
```bash
python run_benchmarks.py
```

### 4. Run High-Frequency Market Simulation
```bash
python run_simulation.py
```

---

## 🌐 Deployment

### GitHub Pages (Static Frontend)
The frontend is hosted directly on GitHub Pages:
- **Live URL**: [https://dinu18s.github.io/ChronosMatch/](https://dinu18s.github.io/ChronosMatch/)
- Features a complete client-side simulation engine with `localStorage` persistence, enabling 100% functionality without requiring external servers.

### Vercel / Cloud Serverless
Configured with `vercel.json` pointing to `api/index.py`:
```bash
vercel deploy
```

---

## 📜 License
MIT License. Created for educational and demonstration purposes.
