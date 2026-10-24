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

## 🏗️ Architecture

```
+---------------------------------------------------------------------------------+
|                                Frontend Client                                  |
|   (Interactive Chart, Watchlist, Order Gateway, Portfolio, Holdings, Dark Mode) |
+---------------------------------------------------------------------------------+
           |                                                        |
           v                                                        v
+-----------------------------+                           +-----------------------+
|  FastAPI Virtual Trading    |                           |  HFT Matching Engine  |
|  & Market Data Service      |                           |  (Zero-Copy C-Structs)|
+-----------------------------+                           +-----------------------+
  |                        |                                     |
  v                        v                                     v
+------------------+     +-------------------+                 +-------------------+
| SQLite Database  |     | Market Data Feed  |                 | Shared-Memory IPC |
| (Users, Holdings,|     | (Yahoo Finance &  |                 | (SPSC Ring Buffer |
| Orders, Accounts)|     | Fallback Engine)  |                 | & Binary WAL)     |
+------------------+     +-------------------+                 +-------------------+
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

   # Optional API key for third-party market data
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
.venv\Scripts\python.exe -m pytest -ra
```
Runs the comprehensive test suite covering:
- Virtual user authentication & ₹1,00,000 balance initialization
- Live market quotes, searches, and historical chart data
- Virtual BUY and SELL order execution and balance deduction
- Insufficient cash rejection and overselling validation
- Resting LIMIT and STOP-LIMIT order execution
- Order cancellation and instant cash/shares refund
- Partial fills and remaining leaves quantity tracking
- Watchlist toggling and transaction history recording
- Portfolio analytics, win rate calculations, and trading journal CRUD
- AI chat assistant educational rules
- Matching engine L3 books, FIFO price-time priority, ring buffers, and binary WAL

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
