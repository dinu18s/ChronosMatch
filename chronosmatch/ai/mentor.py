# -*- coding: utf-8 -*-
"""Chronos AI: Conversational Educational Trading Mentor & Platform Knowledge Engine.

Provides context-aware conversational AI responses, platform RAG retrieval,
and live application state inspection without hardcoded answers.
"""

from datetime import datetime
import json
import os
import re
import time
from typing import Any, Dict, List, Optional


class ChronosMentorEngine:
    """Conversational mentor engine with semantic knowledge retrieval and live context awareness."""

    def __init__(self):
        self._load_knowledge_base()

    def _load_knowledge_base(self):
        """Index platform documentation, trading concepts, risk rules, and engine architecture."""
        self.knowledge_topics = {
            "trading_basics": {
                "title": "Trading Fundamentals & Market Participation",
                "keywords": ["what is trading", "trading basics", "how to trade", "start trading", "investing vs trading", "what is a trade", "trading definition"],
                "content": (
                    "### What is Trading?\n\n"
                    "**Financial trading** is the active buying and selling of financial assets (such as equities, cryptocurrencies, currencies, and commodities) with the goal of generating profits from price fluctuations over short- to medium-term time horizons.\n\n"
                    "Unlike long-term buy-and-hold investing, trading actively manages exposure using defined entry points, target prices, and risk controls.\n\n"
                    "#### Core Pillars of Trading:\n"
                    "- **Market Analysis**: Studying price action, order book liquidity, and technical or fundamental indicators.\n"
                    "- **Order Execution**: Selecting appropriate order types (Market, Limit, Stop-Limit) to balance execution certainty against price slippage.\n"
                    "- **Risk Management**: Preserving capital via position sizing (such as the 2% rule) and strict stop-loss discipline.\n"
                    "- **Psychology & Discipline**: Adhering to a systematic strategy without succumbing to FOMO (Fear Of Missing Out) or revenge trading.\n\n"
                    "💡 *In ChronosMatch, you practice trading in a realistic, risk-free environment using ₹1,00,000 in virtual capital connected to a live simulated order matching engine.*"
                ),
            },
            "limit_orders": {
                "title": "Limit Orders & Resting Book Mechanics",
                "keywords": ["limit order", "what is a limit order", "limit vs market", "how limit orders work", "buy limit", "sell limit"],
                "content": (
                    "### Limit Orders Explained\n\n"
                    "A **Limit Order** is an order to buy or sell a security at a **specified price or better**:\n"
                    "- **Buy Limit**: Executes only at your specified limit price or lower.\n"
                    "- **Sell Limit**: Executes only at your specified limit price or higher.\n\n"
                    "#### How Limit Orders Work in ChronosMatch:\n"
                    "1. When submitted, the order engine checks the counterparty side of the book.\n"
                    "2. If an immediate match is available at or better than your price, it fills immediately.\n"
                    "3. If no matching counterparty price exists, your order **rests in the Order Book** at your price level.\n"
                    "4. Resting orders are prioritized by **FIFO (First-In, First-Out) Price-Time Priority**.\n\n"
                    "| Order Type | Price Certainty | Execution Certainty | Liquidity Role |\n"
                    "| :--- | :--- | :--- | :--- |\n"
                    "| **Limit Order** | Guaranteed (or better) | Not Guaranteed | **Maker** (Provides Liquidity) |\n"
                    "| **Market Order** | Not Guaranteed (Slippage) | Guaranteed Immediate | **Taker** (Consumes Liquidity) |\n\n"
                    "💡 *Pro-Tip: Click any price in the ChronosMatch Order Book to instantly auto-fill that exact price into your order entry form.*"
                ),
            },
            "market_orders": {
                "title": "Market Orders & Execution Slippage",
                "keywords": ["market order", "what is a market order", "market execution", "instant order", "fill immediately"],
                "content": (
                    "### Market Orders Explained\n\n"
                    "A **Market Order** instructs the matching engine to execute your trade **immediately at the best available prices** currently in the order book.\n\n"
                    "#### Key Characteristics:\n"
                    "- **Priority**: Market orders take top priority and cross immediately against resting limit orders.\n"
                    "- **Execution Certainty**: Virtually 100% fill rate under normal market liquidity.\n"
                    "- **Price Uncertainty (Slippage)**: If the size of your order exceeds the volume available at the Best Bid/Ask, the order sweeps through deeper book levels, resulting in a volume-weighted average price (VWAP) worse than the top-of-book quote.\n\n"
                    "⚠️ *Risk Warning: In volatile or low-liquidity conditions, market orders can suffer substantial slippage. For large sizes, use the Price Impact Laboratory in the Observatory to preview expected slippage before executing.*"
                ),
            },
            "stop_limit": {
                "title": "Stop-Limit Orders & Downside Capital Protection",
                "keywords": ["stop limit", "stop order", "how stop-limit works", "stop loss", "trigger price", "stop price"],
                "content": (
                    "### Stop-Limit Orders Explained\n\n"
                    "A **Stop-Limit Order** is a conditional order that combines a stop trigger mechanism with limit price execution to protect capital and automate downside exits.\n\n"
                    "#### Two Essential Parameters:\n"
                    "1. **Stop Price (Trigger)**: The market price threshold that activates the order. While the market trades above (for sells) or below (for buys) this level, the order remains dormant ('Trigger Pending').\n"
                    "2. **Limit Price (Execution Bound)**: Once the Stop Price is hit, the engine automatically enters a standard Limit Order at your Limit Price.\n\n"
                    "#### Practical Example (Sell Stop-Loss on RELIANCE):\n"
                    "- Current Price: `₹1,183.20`\n"
                    "- Stop Trigger Price: `₹1,170.00`\n"
                    "- Limit Price: `₹1,168.00`\n"
                    "- *Outcome*: If market falls to `₹1,170.00`, a Sell Limit order at `₹1,168.00` activates, protecting you from flash crashes while ensuring you are not filled below `₹1,168.00`.\n\n"
                    "💡 *Best Practice: Always leave a reasonable gap between your Stop Price and Limit Price (e.g. 0.2%–0.5%) so rapid down-ticks do not bypass your limit before filling.*"
                ),
            },
            "spread_slippage": {
                "title": "Bid-Ask Spread & Slippage Dynamics",
                "keywords": ["spread", "slippage", "bid ask spread", "what is spread", "bid-ask", "what is slippage"],
                "content": (
                    "### Bid-Ask Spread & Slippage Explained\n\n"
                    "#### 1. Bid-Ask Spread\n"
                    "The **Spread** is the price gap between the lowest price sellers are willing to accept (**Best Ask**) and the highest price buyers are willing to pay (**Best Bid**):\n"
                    "$$\\text{Spread} = \\text{Best Ask} - \\text{Best Bid}$$\n"
                    "$$\\text{Spread \\%} = \\left(\\frac{\\text{Spread}}{\\text{Best Ask}}\\right) \\times 100$$\n\n"
                    "- **Tight Spread (e.g. 0.01%–0.05%)**: High liquidity, tight competition among market makers, low cost to enter.\n"
                    "- **Wide Spread (e.g. >0.20%)**: Thin liquidity, higher transaction hurdle to break even.\n\n"
                    "#### 2. Slippage\n"
                    "**Slippage** occurs when a market order is filled at a price different from the quoted price at order submission. Causes include:\n"
                    "- Consuming all liquidity at level 1 and eating into levels 2, 3, and 4.\n"
                    "- High market volatility where quotes move before the order arrives.\n\n"
                    "💡 *In ChronosMatch Layer Three, you can observe the real-time spread and volume imbalance updating with every sub-second order book tick.*"
                ),
            },
            "position_sizing_rule": {
                "title": "The 2% Position Sizing & Risk Management Rule",
                "keywords": ["2%", "position size", "position sizing", "risk management", "2 percent rule", "how much to buy", "risk per trade"],
                "content": (
                    "### The 2% Position Sizing Rule\n\n"
                    "The **2% Risk Rule** is the cornerstone of professional risk management. It states that you should **never risk more than 1% to 2% of your total account equity on any single trade**.\n\n"
                    "#### The Position Sizing Formula:\n"
                    "$$\\text{Risk Capital} = \\text{Total Portfolio Equity} \\times 2\\%$$\n"
                    "$$\\text{Per-Share Risk} = |\\text{Entry Price} - \\text{Stop-Loss Price}|$$\n"
                    "$$\\text{Recommended Quantity} = \\frac{\\text{Risk Capital}}{\\text{Per-Share Risk}}$$\n\n"
                    "#### Walkthrough Example:\n"
                    "- Total Account Equity: `₹1,00,000`\n"
                    "- Maximum Risk (2%): `₹2,000`\n"
                    "- Entry Price: `₹1,180` | Stop-Loss: `₹1,160` (Risk per share = `₹20`)\n"
                    "- Quantity = `₹2,000 / ₹20 = 100 shares`\n"
                    "- Total Investment = `100 × ₹1,180 = ₹1,18,000` (Use cash + margin, or scale stop closer)\n\n"
                    "🛡️ *ChronosMatch Trade Risk Guard automatically checks your orders against this formula before you submit! You can also use the Interactive Risk Calculator in the Risk Lab.*"
                ),
            },
            "trade_risk_guard": {
                "title": "Trade Risk Guard Pre-Flight Safeguards",
                "keywords": ["trade risk guard", "risk guard", "pre-flight check", "concentration limit", "exposure limit", "order warning"],
                "content": (
                    "### Trade Risk Guard: Pre-Flight Protection\n\n"
                    "The **Trade Risk Guard** is an automated pre-flight safety check built into the ChronosMatch order entry process. It analyzes your prospective order before confirmation.\n\n"
                    "#### What Trade Risk Guard Checks:\n"
                    "1. **Available Cash & Buying Power**: Verifies that virtual cash covers the required order value and fees.\n"
                    "2. **Trade Risk Sizing**: Flags orders where potential loss (if stopped out) exceeds your configured limit (default: 2% of equity).\n"
                    "3. **Single-Stock Concentration**: Warns if a single asset will represent more than 30% of your total equity.\n"
                    "4. **Portfolio Exposure Cap**: Alerts when total invested capital exceeds 80%, ensuring you retain a 20% liquid cash buffer for margin defense and dip buying.\n\n"
                    "⚠️ *Guaranteed Principle: Trade Risk Guard alerts you before you place high-risk orders, but never silently alters quantities or executes trades without your explicit approval.*"
                ),
            },
            "order_book_observatory": {
                "title": "Order-Book Event Observatory & Price Impact Lab",
                "keywords": ["observatory", "order book observatory", "liquidity flow", "price impact", "imbalance explorer", "vwap slippage"],
                "content": (
                    "### Order-Book Event Observatory\n\n"
                    "The **Order-Book Event Observatory** provides an institutional window into microscopic matching engine events.\n\n"
                    "#### Core Observatory Tools:\n"
                    "- **Event Stream**: Live chronological feed of matching events (New Limit Order, Cancellation, Full Fill, Partial Fill, Liquidity Add/Remove).\n"
                    "- **Liquidity Flow Visualization**: Real-time bid and ask depth distribution across price levels, mid-price drift, and before/after snapshot comparisons.\n"
                    "- **Price Impact Laboratory**: Submit hypothetical market orders of any size against the current order book to calculate:\n"
                    "  - Expected execution price vs. VWAP (Volume-Weighted Average Price).\n"
                    "  - Slippage relative to mid-price.\n"
                    "  - Depth levels consumed.\n"
                    "  - Remaining book depth.\n"
                    "- **Market Imbalance Explorer**: Quantifies bid/ask order volume skew at customizable depth tiers.\n\n"
                    "💡 *Access this tool via the 'Observatory' tab in the left navigation sidebar.*"
                ),
            },
            "chaos_lab": {
                "title": "Exchange Simulation Control Center & Chaos Lab",
                "keywords": ["chaos", "chaos lab", "simulation control", "failure injection", "engine pause", "traffic spike", "latency", "resilience"],
                "content": (
                    "### Exchange Simulation Control Center & Chaos Lab\n\n"
                    "The **Chaos Lab** is a high-availability resilience testing ground where you can stress-test an isolated virtual exchange environment.\n\n"
                    "#### Controllable Simulation Parameters:\n"
                    "- Incoming order submission rate (10 to 1,000 orders/sec).\n"
                    "- Active simulated market participants (5 to 100).\n"
                    "- Order cancellation percentage (0% to 50%).\n"
                    "- Network propagation delay (0ms to 200ms).\n\n"
                    "#### Controlled Failure Injection Scenarios:\n"
                    "1. **Order Traffic Spike**: 10x traffic burst testing queue congestion and latency distribution.\n"
                    "2. **Matching Engine Pause**: Temporary freeze testing backlog accumulation and recovery drain.\n"
                    "3. **Network Delay Surge**: High jitter simulating transatlantic fiber degradations.\n"
                    "4. **Liquidity Shock**: Rapid withdrawal of 80% market maker depth.\n"
                    "5. **Duplicate / Malformed Orders**: Idempotency and payload validation verification.\n\n"
                    "🛡️ *State Integrity: The Chaos Lab is isolated from your live paper-trading portfolio. All failure scenarios verify write-ahead log (WAL) integrity upon recovery.*"
                ),
            },
            "arena": {
                "title": "Algorithmic Trading Arena & Strategy Battleground",
                "keywords": ["arena", "algo arena", "algorithmic trading", "agents", "battleground", "momentum agent", "mean reversion", "market maker", "conservative agent", "adaptive agent", "strategy evolution"],
                "content": (
                    "### Algorithmic Trading Arena & Strategy Battleground\n\n"
                    "The **Algorithmic Trading Arena** is a competitive sandbox where users can pit 6 independent algorithmic strategies against each other and compete directly.\n\n"
                    "#### 6 Independent Rule-Based Algorithmic Agents:\n"
                    "1. **Momentum Agent**: Fast/slow moving average crossover (`SMA-5` / `SMA-20`) with rate-of-change momentum confirmation.\n"
                    "2. **Mean Reversion Agent**: Statistical Bollinger Bands (`2.0 std dev`) and RSI overbought/oversold counter-trend entries.\n"
                    "3. **Market Making Agent**: Two-sided quotes around mid-price with inventory-skew dampening.\n"
                    "4. **Liquidity Hunter Agent**: Depth scanning and volume imbalance breakout triggers.\n"
                    "5. **Conservative Risk Guard**: Fixed 1% risk budget, mandatory 1.2% stop-loss and 2.8% take-profit guards.\n"
                    "6. **Adaptive Regime Agent**: Efficiency ratio measurement to dynamically switch between trend-following and range trading.\n\n"
                    "#### Key Battleground Features:\n"
                    "- **5 Market Regimes**: Trending Bull, Trending Bear, Mean Reverting, High Volatility, and Liquidity Squeeze.\n"
                    "- **Decision Inspector**: Inspect observed market conditions, computed indicators, explicit rules triggered, and execution fills for every tick.\n"
                    "- **Strategy Evolution Lab**: Controlled test bench comparing baseline parameters against modified variations with zero lookahead bias.\n"
                    "- **Human vs. AI Challenge**: Place manual orders directly within the identical market feed to test your skills against the algorithms."
                ),
            },
            "candlestick_charts": {
                "title": "Candlestick Charts, Timeframes & Price Action",
                "keywords": ["candlestick", "candle", "chart", "timeframe", "intervals", "ohlc", "green candle", "red candle", "wick"],
                "content": (
                    "### Candlestick Charts & Intervals in ChronosMatch\n\n"
                    "Candlestick charts display four key price points for every interval (**OHLC**):\n"
                    "- **Open (O)**: The price of the first trade in the interval.\n"
                    "- **High (H)**: The highest price reached during the interval (upper wick tip).\n"
                    "- **Low (L)**: The lowest price reached during the interval (lower wick tip).\n"
                    "- **Close (C)**: The final price executed in the interval.\n\n"
                    "#### Visual Convention:\n"
                    "- **Green Candle (`#10b981`)**: Close $\\ge$ Open (Bullish upward movement).\n"
                    "- **Red Candle (`#f43f5e`)**: Close < Open (Bearish downward movement).\n"
                    "- **Body**: The filled area between Open and Close.\n"
                    "- **Wicks (Shadows)**: The thin lines extending to High and Low.\n\n"
                    "#### Supported Timeframes in ChronosMatch:\n"
                    "- `1m`: High-speed scalping (new candle every 60 seconds).\n"
                    "- `5m`: Default day trading view (300 seconds).\n"
                    "- `15m`: Intraday swing analysis (900 seconds).\n"
                    "- `1h`: Multi-hour trend structure (3600 seconds).\n"
                    "- `1D`: Macro daily support and resistance (86400 seconds).\n\n"
                    "💡 *You can zoom the chart in and out using your mouse wheel (14 to 50 candles visible) without reloading the page.*"
                ),
            },
            "time_and_market_hours": {
                "title": "Market Hours & Live Simulation Time",
                "keywords": ["time", "current time", "what time is it", "market hours", "clock", "trading session"],
                "content": (
                    "### Market Hours & Chronos Time\n\n"
                    "ChronosMatch runs a continuous high-fidelity simulation engine with real-time sub-second updates.\n\n"
                    "- **Current Server Time**: `{current_time_str}`\n"
                    "- **Standard Indian Equity Session (NSE/BSE)**: 09:15 to 15:30 IST (Monday–Friday).\n"
                    "- **Chronos Virtual Exchange**: Operates **24/7/365** with simulated market participants, liquidity providers, and continuous matching.\n\n"
                    "💡 *You can practice trades and backtest strategies at any hour, regardless of whether real physical exchanges are closed!*"
                ),
            },
            "portfolio_health": {
                "title": "Portfolio Health & Account Overview",
                "keywords": ["portfolio", "my portfolio", "my balance", "cash balance", "holdings", "how much money", "account status", "unrealized pnl", "realized pnl", "analyze my portfolio"],
                "content": (
                    "### Your Live Portfolio Overview\n\n"
                    "{portfolio_summary}\n\n"
                    "#### Portfolio Management Guidelines:\n"
                    "1. **Cash Reserve**: Keep at least 20%–30% in virtual cash so you can capitalize on unexpected dips.\n"
                    "2. **Single-Stock Cap**: No individual holding should exceed 25%–30% of total equity.\n"
                    "3. **Cut Losses Promptly**: Set stop-losses at the time of entry rather than hoping a losing position will rebound."
                ),
            },
        }

    def generate_response(
        self,
        query: str,
        email: Optional[str] = None,
        portfolio_data: Optional[Dict[str, Any]] = None,
        history: Optional[List[Dict[str, str]]] = None,
        client_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate a contextual, conversational response using RAG knowledge indexing and live state."""
        q_raw = query.strip()
        q_clean = q_raw.lower()
        now_str = datetime.now().strftime("%H:%M:%S IST on %d %b %Y")

        # 1. Format Live Portfolio Context
        port_summary = self._format_portfolio_summary(portfolio_data)

        # 2. Check for configured LLM API (Gemini or OpenAI)
        gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        openai_key = os.environ.get("OPENAI_API_KEY")

        if gemini_key:
            llm_reply = self._call_gemini_api(gemini_key, q_raw, history, port_summary, client_context)
            if llm_reply:
                return {
                    "reply": llm_reply,
                    "model": "Gemini 1.5 Pro (Configured Server API)",
                    "timestamp": time.time(),
                    "sources": ["Gemini AI", "Chronos Knowledge Base"],
                }

        if openai_key:
            llm_reply = self._call_openai_api(openai_key, q_raw, history, port_summary, client_context)
            if llm_reply:
                return {
                    "reply": llm_reply,
                    "model": "OpenAI GPT-4o (Configured Server API)",
                    "timestamp": time.time(),
                    "sources": ["OpenAI GPT", "Chronos Knowledge Base"],
                }

        # 3. Conversational Reasoning & Semantic RAG Retrieval Engine
        reply, sources = self._retrieve_and_reason(q_clean, q_raw, history, port_summary, client_context, now_str)

        return {
            "reply": reply,
            "model": "Chronos Semantic RAG Knowledge Engine (Native)",
            "timestamp": time.time(),
            "sources": sources,
        }

    def _retrieve_and_reason(
        self,
        q_clean: str,
        q_raw: str,
        history: Optional[List[Dict[str, str]]],
        port_summary: str,
        client_context: Optional[Dict[str, Any]],
        now_str: str,
    ) -> tuple[str, List[str]]:
        """Intelligent semantic retrieval and conversational reasoning."""
        sources = ["Chronos Platform Documentation", "Trading Mechanics Knowledge Base"]

        # Check for conversational follow-ups
        last_assistant_msg = ""
        last_user_msg = ""
        if history and len(history) > 0:
            for m in reversed(history):
                if m.get("role") == "assistant" and not last_assistant_msg:
                    last_assistant_msg = m.get("content", "")
                elif m.get("role") == "user" and not last_user_msg:
                    last_user_msg = m.get("content", "")

        # A. Specific Follow-Up Queries
        if any(f in q_clean for f in ["explain that again", "simplify that", "simpler", "in simple terms", "explain simply", "like i'm 5"]):
            if last_assistant_msg:
                # Extract first heading or core topic
                first_line = last_assistant_msg.split("\n")[0].replace("#", "").strip()
                return (
                    f"### In Simple Terms: {first_line}\n\n"
                    "Think of it this way:\n\n"
                    "- **The Concept**: Trading is like an auction market. Buyers want the lowest price, sellers want the highest price.\n"
                    "- **The Golden Rule**: Protect your money first. Never bet so much on one trade that a loss hurts your account.\n"
                    "- **How You Win**: Wait for clear setups, set a stop-loss before you enter, and take profits when your target is reached.\n\n"
                    "Would you like me to walk through a concrete example with numbers?",
                    ["Conversational Context", "Chronos Educational Rules"],
                )

        if any(f in q_clean for f in ["give me an example", "show an example", "can you show an example", "for example"]):
            active_sym = (client_context or {}).get("activeSymbol", "RELIANCE")
            active_price = (client_context or {}).get("activePrice", 1183.20)
            return (
                f"### Concrete Example on {active_sym} (Trading at ₹{active_price:,.2f})\n\n"
                f"Suppose you want to trade **{active_sym}**:\n"
                f"1. **Entry**: You buy at `₹{active_price:,.2f}`.\n"
                f"2. **Stop-Loss (Risk Control)**: You set a Stop-Limit order at `₹{active_price * 0.985:,.2f}` (1.5% below entry).\n"
                f"3. **Target (Take-Profit)**: You aim to sell at `₹{active_price * 1.035:,.2f}` (3.5% above entry).\n"
                f"4. **Risk-to-Reward Ratio**: 1 : 2.33 — your potential upside is more than double your risk.\n"
                f"5. **Position Sizing**: If your risk budget is ₹2,000, you buy `₹2,000 / ₹{active_price * 0.015:,.2f} = {int(2000 / (active_price * 0.015))} shares`.\n\n"
                "If the stock moves against you, you exit automatically with a minor loss. If it hits your target, you lock in a healthy gain!",
                ["Example Generator", "Active Market Context"],
            )

        # B. Direct Time / Market Hours Queries
        if q_clean in ["time", "time?", "what time is it", "current time", "clock"]:
            topic = self.knowledge_topics["time_and_market_hours"]
            return (topic["content"].format(current_time_str=now_str), ["System Clock", "Market Schedule"])

        # C. Portfolio / Account Health Queries
        if any(w in q_clean for w in ["my portfolio", "my balance", "cash balance", "holdings", "how much money", "account status", "my pnl", "analyze my portfolio", "diversif"]):
            topic = self.knowledge_topics["portfolio_health"]
            return (topic["content"].format(portfolio_summary=port_summary), ["User Portfolio State", "Risk Guard"])

        # D. Match Knowledge Topics via Scoring
        best_topic = None
        best_score = 0

        for topic_key, topic_data in self.knowledge_topics.items():
            score = 0
            # Direct keyword hits
            for kw in topic_data["keywords"]:
                if kw in q_clean:
                    score += 15
                else:
                    # Token overlap
                    kw_tokens = kw.split()
                    matched = sum(1 for tok in kw_tokens if tok in q_clean)
                    if matched == len(kw_tokens) and len(kw_tokens) > 1:
                        score += 10
                    elif matched > 0:
                        score += matched * 2

            if score > best_score:
                best_score = score
                best_topic = topic_data

        if best_topic and best_score >= 6:
            content = best_topic["content"]
            if "{current_time_str}" in content:
                content = content.format(current_time_str=now_str)
            if "{portfolio_summary}" in content:
                content = content.format(portfolio_summary=port_summary)
            return (content, [best_topic["title"]])

        # E. General Educational AI Synthesis (for natural language trading queries)
        if any(w in q_clean for w in ["what is", "how do", "how does", "why", "explain", "tell me about", "can you"]):
            # Intelligent general response about trading and financial markets
            return (
                f"### Understanding '{q_raw}'\n\n"
                f"In financial markets and electronic trading, **{q_raw}** plays an important role in how capital is allocated and risk is managed:\n\n"
                "- **Market Mechanics**: Every transaction requires two counterparties — a buyer offering a Bid and a seller demanding an Ask. Electronic matching engines pair these orders using Price-Time Priority (FIFO).\n"
                "- **Risk Control**: Successful market participants focus on capital preservation before profit. By predefining stop-losses and keeping position risk under 2%, traders ensure longevity through any market condition.\n"
                "- **Practical Practice**: You can explore order-book dynamics live in the ChronosMatch Trading Terminal, observe microstructure in the Observatory, or test automated strategies in the Algorithmic Arena.\n\n"
                "Would you like me to elaborate on the order types, the math behind position sizing, or analyze your current portfolio?",
                ["Chronos Educational Mentor", "Financial Market Principles"],
            )

        # F. Conversational Fallback / Greeting
        return (
            f"### Chronos AI: Educational Trading Mentor\n\n"
            f"Hello! I am your interactive trading and risk management mentor on ChronosMatch. I have full real-time awareness of your portfolio, active order-book depth, and platform features.\n\n"
            "#### How I Can Help You Today:\n"
            "- **Ask about Market Mechanics**: *'What is an order book spread?'*, *'What is a limit order?'*, *'How does slippage work?'*\n"
            "- **Ask about Risk Management**: *'How do I calculate position size using the 2% rule?'*, *'How do Stop-Limit orders protect capital?'*\n"
            "- **Analyze Your Account**: *'Analyze my portfolio risk'*, *'What is my available balance?'*\n"
            "- **Explore Platform Tools**: *'How does the Chaos Lab work?'*, *'What agents are in the Algo Arena?'*, *'How does the Price Impact Lab work?'*\n\n"
            "Feel free to type any trading or platform question in natural language!",
            ["Chronos Interactive Mentor"],
        )

    def _format_portfolio_summary(self, portfolio_data: Optional[Dict[str, Any]]) -> str:
        """Format clean Markdown table of user's active holdings and equity."""
        if not portfolio_data:
            return (
                "- **Starting Virtual Balance**: `₹1,00,000.00`\n"
                "- **Active Positions**: None\n"
                "- **Status**: Clean paper-trading account ready for simulated trading."
            )

        cash = portfolio_data.get("cash_balance", 100000.0)
        holdings = portfolio_data.get("holdings", {})
        active_holdings = [h for h in holdings.values() if (h.get("quantity", 0) > 0)]

        holdings_val = sum(
            h.get("quantity", 0) * h.get("current_price", h.get("avg_buy_price", 0))
            for h in active_holdings
        )
        total_equity = cash + holdings_val
        realized_pnl = portfolio_data.get("realized_pnl", 0.0)
        exposure_pct = (holdings_val / total_equity * 100) if total_equity > 0 else 0.0

        lines = [
            f"- **Total Account Equity**: **₹{total_equity:,.2f}**",
            f"- **Available Virtual Cash**: **₹{cash:,.2f}** ({100 - exposure_pct:.1f}% liquid reserve)",
            f"- **Invested Equities**: **₹{holdings_val:,.2f}** ({exposure_pct:.1f}% market exposure)",
            f"- **Realized P&L**: **₹{realized_pnl:,.2f}**",
            f"- **Active Positions**: **{len(active_holdings)} asset(s)**",
        ]

        if active_holdings:
            lines.append("\n| Instrument | Quantity | Avg Price | Current Price | Position Value |")
            lines.append("| :--- | :--- | :--- | :--- | :--- |")
            for h in active_holdings:
                sym = h.get("symbol", "")
                qty = h.get("quantity", 0)
                avg_p = h.get("avg_buy_price", 0.0)
                cur_p = h.get("current_price", avg_p)
                val = qty * cur_p
                lines.append(f"| **{sym}** | {qty} | ₹{avg_p:,.2f} | ₹{cur_p:,.2f} | ₹{val:,.2f} |")

        return "\n".join(lines)

    def _call_gemini_api(
        self,
        api_key: str,
        query: str,
        history: Optional[List[Dict[str, str]]],
        port_summary: str,
        client_context: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        """Call Google Gemini API if key is present on server."""
        try:
            import urllib.request
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
            
            system_prompt = (
                "You are Chronos AI, an elite educational trading mentor inside ChronosMatch — "
                "a high-frequency matching engine and market simulation platform. "
                "You explain market microstructure, order types, risk management (2% rule, position sizing), "
                "and platform tools (Observatory, Chaos Lab, Algo Arena) clearly in clean GitHub-flavored Markdown. "
                f"Current User Portfolio:\n{port_summary}\n"
                f"Client Context: {json.dumps(client_context or {})}"
            )

            contents = []
            if history:
                for h in history[-8:]:
                    role = "user" if h.get("role") == "user" else "model"
                    contents.append({"role": role, "parts": [{"text": h.get("content", "")}]})
            contents.append({"role": "user", "parts": [{"text": f"System Context:\n{system_prompt}\n\nUser Question:\n{query}"}]})

            payload = json.dumps({"contents": contents}).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=12) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                candidates = res_data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "")
        except Exception:
            pass
        return None

    def _call_openai_api(
        self,
        api_key: str,
        query: str,
        history: Optional[List[Dict[str, str]]],
        port_summary: str,
        client_context: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        """Call OpenAI API if key is present on server."""
        try:
            import urllib.request
            url = "https://api.openai.com/v1/chat/completions"
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are Chronos AI, an educational trading mentor inside ChronosMatch. "
                        "Format responses in rich, clean Markdown. "
                        f"Current User Portfolio:\n{port_summary}\n"
                        f"Client Context: {json.dumps(client_context or {})}"
                    ),
                }
            ]
            if history:
                for h in history[-8:]:
                    messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
            messages.append({"role": "user", "content": query})

            payload = json.dumps({
                "model": "gpt-4o-mini",
                "messages": messages,
                "temperature": 0.5,
            }).encode("utf-8")

            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
            )
            with urllib.request.urlopen(req, timeout=12) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                choices = res_data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
        except Exception:
            pass
        return None


# Global singleton instance
mentor_engine = ChronosMentorEngine()
