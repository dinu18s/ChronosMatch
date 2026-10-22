# ChronosMatch: Real-Time Virtual Paper Trading & Matching Terminal

> **PAPER TRADING — SIMULATION ONLY — NO REAL MONEY**  
> An educational, full-stack paper trading terminal and zero-copy electronic matching engine built in modern Python (3.12+) and vanilla HTML5/CSS3/JavaScript.

[![CI Status](https://github.com/dinu18s/ChronosMatch/actions/workflows/ci.yml/badge.svg)](https://github.com/dinu18s/ChronosMatch/actions)
[![Live Demo](https://img.shields.io/badge/Live_Demo-GitHub_Pages-blue.svg)](https://dinu18s.github.io/ChronosMatch/)
[![Currency](https://img.shields.io/badge/Currency-INR_(%E2%82%B9)-green.svg)](https://dinu18s.github.io/ChronosMatch/)

---

## 🌟 Key Features

### 1. Real-Time Market Prices
- **Live Market Data Feeds**: Live price queries powered by Yahoo Finance feed with in-memory caching (15s TTL) for fast, rate-limit-resilient updates.
- **Coverage**: Top Indian bluechips (NSE: RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK, SBIN, MARUTI, ITC, TATAPOWER, WIPRO), Global Tech (AAPL, MSFT, TSLA, NVDA), and Crypto (BTC, ETH, SOL in INR).
- **Comprehensive Quotes**: Displays stock name, symbol, current price in `₹` (INR), daily percentage change, opening price, daily high/low, and last updated time.
- **Interactive Price Charts**: Dynamic timeframes (`1D`, `1W`, `1M`, `1Y`, `ALL`) with smooth Bézier curve rendering, crosshair cursor, and floating price/time tooltips.
- **Data Transparency**: Explicit live data indicator (`● Live Exchange Feed`) vs. demo/cached fallback, ensuring simulated data is never falsely claimed as real.

### 2. Virtual Buying and Selling
- **100% Paper Money**: Starting virtual capital of **₹1,00,000.00** for every new user.
- **Server-Side Validation**:
  - Automatically validates cash sufficiency before allowing `BUY` orders.
  - Automatically verifies share ownership before allowing `SELL` orders (prevents shorting/selling more shares than owned).
- **Atomic Balance Updates**: Deducts purchase value on BUY, credits proceeds on SELL, and recalculates average purchase price and realized profit/loss.
- **Zero Real-Money Connections**: Strictly simulated paper trading; no broker connections or financial transactions.

### 3. Portfolio Dashboard
- **Real-Time Portfolio Metrics**:
  - Available Virtual Cash (₹)
  - Total Portfolio Value (Cash + Current Market Value of Holdings)
  - Total Capital Invested
  - Unrealized Profit/Loss (₹ and %) with dynamic gain/loss badges
  - Realized Profit/Loss accumulated from completed sales
- **Live Holdings Table**: Displays instrument, quantity owned, average buy price, current market price, total invested, current market value, P&L, and quick `Buy More` / `Sell` action shortcuts.
- **Transaction Audit Log**: Comprehensive history of every executed order with order ID, date & time, side, quantity, price, total value, and status.

### 4. Watchlist and Instant Search
- **Instant Search**: Search across stock symbols, tickers, and company names with live filtering as you type.
- **Category Filter Tabs**: Quickly filter by `All`, `Nifty 50`, `US Tech`, `Crypto`, or starred `⭐ Watchlist`.
- **Sort Options**: Sort by Default, Price (High-to-Low, Low-to-High), or 24h Percentage Gainers/Losers.
- **Personal Watchlist**: Pin/unpin instruments with the star button, persistently saved to the user's account.

### 5. Order Management
- **Order Types**: Virtual `Market Orders` (instant execution at current market price) and `Limit Orders` (custom price limit).
- **Order Confirmation Modal**: Displays order summary, price, quantity, total value, and before/after cash impact for user confirmation before order placement.

### 6. User Interface
- **Professional Trading Platform Design**: Dark and Light themes with one-click instant toggle (persisted in `localStorage`).
- **Mobile Responsive**: Fully responsive grid layout adapting from desktop 3-column view to tablet and mobile views.
- **Prominent Simulation Notice**: High-visibility banner stating `PAPER TRADING — SIMULATION ONLY — NO REAL MONEY`.

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
| SQLite Database  |     | Yahoo Finance API |                 | Shared-Memory IPC |
| (Users, Holdings,|     | (Live Quotes &    |                 | (SPSC Ring Buffer |
| Orders, Accounts)|     | History Candles)  |                 | & Binary WAL)     |
+------------------+     +-------------------+                 +-------------------+
```

---

## 🚀 Getting Started

### Prerequisites
- Python 3.11 or higher (Python 3.12 recommended)
- `uv` (recommended) or standard `pip` / `venv`

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

   # Optional API key for third-party market data (defaults to Yahoo Finance public feed)
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
Runs all 32 unit tests covering:
- Virtual user authentication & ₹1,00,000 balance initialization
- Live market quotes, searches, and historical chart data
- Virtual BUY and SELL order execution and balance deduction
- Insufficient cash rejection and overselling validation
- Watchlist toggling and transaction history recording
- Matching engine L3 books, order queues, ring buffers, and binary WAL

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
The frontend in `docs/index.html` is automatically served by GitHub Pages:
- **URL**: [https://dinu18s.github.io/ChronosMatch/](https://dinu18s.github.io/ChronosMatch/)
- Includes standalone client-side fallback with `localStorage` persistence and market data feeds.

### Vercel / Cloud Serverless
Configured with `vercel.json` pointing to `api/index.py`:
```bash
vercel deploy
```

---

## 📜 License
MIT License. Created for educational and demonstration purposes.
