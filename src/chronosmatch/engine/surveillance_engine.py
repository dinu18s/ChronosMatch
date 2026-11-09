"""Market Surveillance & Fraud Detection Lab engine for ChronosMatch.

Provides deterministic, explainable surveillance detection algorithms,
scenario simulation generators, investigation workspaces, challenge modes,
and regulatory dossier generation.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
import datetime
import math
import uuid


# =============================================================================
# DEFAULT SURVEILLANCE THRESHOLDS
# =============================================================================

DEFAULT_THRESHOLDS = {
    "SPOOFING": {
        "order_size_ratio": 3.0,        # Order size >= 3.0x median book size
        "cancel_latency_ms": 1500,       # Cancelled within <= 1500 ms
        "fill_rate_max_pct": 5.0,        # Less than 5% executed
    },
    "LAYERING": {
        "min_depth_tiers": 3,            # Orders stacked across >= 3 distinct price tiers
        "cancel_rate_min_pct": 80.0,     # >= 80% of layered orders cancelled
        "require_opposite_exec": True,   # Execution on contra-side during stacking
    },
    "WASH_TRADING": {
        "max_net_delta_pct": 5.0,        # Net position change <= 5% of traded volume
        "max_price_variance_pct": 0.20,  # Price variance between matched trades <= 0.20%
        "min_round_trips": 2,            # At least 2 matched round-trips between coordinated IDs
    },
    "PUMP_AND_DUMP": {
        "min_runup_pct": 8.0,            # Price run-up >= 8.0%
        "min_reversal_pct": 70.0,        # Reversal erases >= 70% of peak run-up
        "max_cycle_duration_sec": 300,   # Entire cycle within 5 minutes
    },
    "UNUSUAL_VOLUME": {
        "volume_multiplier": 4.0,        # Volume >= 4.0x rolling 20-period median
        "participant_concentration_pct": 60.0, # Top participant >= 60% of volume
    },
    "ABNORMAL_PRICE": {
        "sigma_deviation": 3.0,          # Price move >= 3.0 standard deviations
        "max_time_window_sec": 30,       # Occurs within <= 30 seconds
    },
}


# =============================================================================
# DETECTION RULES CATALOG
# =============================================================================

DETECTION_RULES = [
    {
        "id": "SPOOF-01",
        "name": "Spoofing Detection",
        "pattern": "Spoofing",
        "category": "Order Book Manipulation",
        "severity": "CRITICAL",
        "description": "Identifies large non-bona fide orders submitted to create a false impression of buying or selling pressure, rapidly cancelled prior to execution.",
        "regulatory_basis": "SEBI PFUTP Regulations / US Dodd-Frank Act Sec 747 / CFTC Rule 180.1",
        "default_thresholds": DEFAULT_THRESHOLDS["SPOOFING"],
    },
    {
        "id": "LAYER-02",
        "name": "Order Book Layering",
        "pattern": "Layering",
        "category": "Order Book Manipulation",
        "severity": "CRITICAL",
        "description": "Detects laddered multi-tier orders entered on one side of the book to simulate artificial depth while executing bona-fide trades on the contra side.",
        "regulatory_basis": "MiFID II MAR Regulatory Technical Standards 25 / SEBI Circular on Layering",
        "default_thresholds": DEFAULT_THRESHOLDS["LAYERING"],
    },
    {
        "id": "WASH-03",
        "name": "Wash Trading & Self-Matching",
        "pattern": "Wash Trading",
        "category": "Volume Manipulation",
        "severity": "HIGH",
        "description": "Flags transactions executed between identical or coordinated accounts with zero net economic risk or change in beneficial ownership.",
        "regulatory_basis": "Commodity Exchange Act 4c(a)(A) / SEBI Prohibition of Fraudulent Trade Practices",
        "default_thresholds": DEFAULT_THRESHOLDS["WASH_TRADING"],
    },
    {
        "id": "PUMP-04",
        "name": "Pump and Dump Scheme",
        "pattern": "Pump and Dump",
        "category": "Price Manipulation",
        "severity": "CRITICAL",
        "description": "Detects aggressive artificial markup in price driven by concentrated market orders followed by sharp distribution and liquidity withdrawal.",
        "regulatory_basis": "SEC Rule 10b-5 / SEBI Prohibition of Market Abuse Guidelines",
        "default_thresholds": DEFAULT_THRESHOLDS["PUMP_AND_DUMP"],
    },
    {
        "id": "VOL-05",
        "name": "Unusual Volume Surge",
        "pattern": "Unusual Volume",
        "category": "Statistical Anomalies",
        "severity": "WARNING",
        "description": "Surveillance trigger for trading volume spikes significantly exceeding the moving baseline without commensurate market depth absorption.",
        "regulatory_basis": "Exchange Surveillance SOP - Abnormal Turnover Alerts",
        "default_thresholds": DEFAULT_THRESHOLDS["UNUSUAL_VOLUME"],
    },
    {
        "id": "PRICE-06",
        "name": "Abnormal Price Movement",
        "pattern": "Abnormal Price Movement",
        "category": "Statistical Anomalies",
        "severity": "WARNING",
        "description": "Monitors sudden volatility bursts exceeding 3 standard deviations in ultra-short intervals, flagging possible sweeps or flash crashes.",
        "regulatory_basis": "SEBI Circuit Filter & Dynamic Price Band Guidelines",
        "default_thresholds": DEFAULT_THRESHOLDS["ABNORMAL_PRICE"],
    },
]


# =============================================================================
# SURVEILLANCE FEED SEED EVENTS
# =============================================================================

INITIAL_SURVEILLANCE_FEED = [
    {
        "event_id": "EVT-8901",
        "timestamp": "10:14:02.120",
        "symbol": "RELIANCE",
        "type": "ORDER_ENTRY",
        "side": "BUY",
        "price": 1183.05,
        "quantity": 25,
        "account": "ACC-HFT-801",
        "flag": "BENIGN",
        "details": "Routine limit order posted to bid ladder.",
    },
    {
        "event_id": "EVT-8902",
        "timestamp": "10:14:02.340",
        "symbol": "RELIANCE",
        "type": "ORDER_EXECUTION",
        "side": "SELL",
        "price": 1183.15,
        "quantity": 10,
        "account": "ACC-RET-412",
        "flag": "BENIGN",
        "details": "Retail market order executed against best ask.",
    },
    {
        "event_id": "EVT-8903",
        "timestamp": "10:14:03.010",
        "symbol": "TCS",
        "type": "ORDER_ENTRY",
        "side": "BUY",
        "price": 3480.00,
        "quantity": 1200,
        "account": "ACC-UNK-994",
        "flag": "SUSPICIOUS",
        "details": "Large order (8.4x median) posted at bid.",
    },
    {
        "event_id": "EVT-8904",
        "timestamp": "10:14:03.245",
        "symbol": "TCS",
        "type": "ORDER_CANCEL",
        "side": "BUY",
        "price": 3480.00,
        "quantity": 1200,
        "account": "ACC-UNK-994",
        "flag": "SUSPICIOUS",
        "details": "Cancelled after 235ms with 0 fills (Spoofing candidate).",
    },
    {
        "event_id": "EVT-8905",
        "timestamp": "10:14:04.100",
        "symbol": "INFY",
        "type": "TRADE_MATCH",
        "side": "CROSS",
        "price": 1820.50,
        "quantity": 500,
        "account": "ACC-BOT-01 -> ACC-BOT-02",
        "flag": "SUSPICIOUS",
        "details": "Matched trade between paired coordinated sub-accounts.",
    },
    {
        "event_id": "EVT-8906",
        "timestamp": "10:14:05.500",
        "symbol": "HDFCBANK",
        "type": "VOL_SPIKE",
        "side": "BUY",
        "price": 1650.00,
        "quantity": 15000,
        "account": "MULTIPLE",
        "flag": "BENIGN",
        "details": "Block trade rebalancing crossing at official benchmark.",
    },
]


# =============================================================================
# CURATED PRESET FRAUD SCENARIOS
# =============================================================================

PRESET_SCENARIOS = {
    "SCN_SPOOFING": {
        "id": "SCN_SPOOFING",
        "title": "Large Fake Bid Wall (Spoofing Attack)",
        "pattern": "Spoofing",
        "symbol": "RELIANCE",
        "description": "A manipulative participant places an outsized buy order of 1,800 shares (5.5x median depth) to create false buying pressure, waits 280ms for ask prices to react, and instantly cancels the bid while executing a sell on the contra side.",
        "params": {
            "order_size": 1800,
            "order_size_ratio": 5.5,
            "cancel_latency_ms": 280,
            "fill_percentage": 0.0,
            "participants": 1,
            "price_impact_pct": 0.45,
            "volume": 1800,
        },
        "expected_detection": "SPOOF-01",
        "expected_verdict": "CONFIRMED_SIMULATION",
    },
    "SCN_LAYERING": {
        "id": "SCN_LAYERING",
        "title": "Sell-Side Ladder Depth Illusion (Layering)",
        "pattern": "Layering",
        "symbol": "TCS",
        "description": "A trader enters 4 layered sell orders of 400 shares each across 4 consecutive price ticks above the offer. 92% of the orders are cancelled within 800ms once counterparties dump shares into the trader's resting buy order.",
        "params": {
            "order_size": 1600,
            "cancel_latency_ms": 750,
            "tier_count": 4,
            "cancel_rate_pct": 92.5,
            "participants": 1,
            "price_impact_pct": -0.65,
            "volume": 1600,
        },
        "expected_detection": "LAYER-02",
        "expected_verdict": "CONFIRMED_SIMULATION",
    },
    "SCN_WASH_TRADING": {
        "id": "SCN_WASH_TRADING",
        "title": "Coordinated Bot Churn (Wash Trading)",
        "pattern": "Wash Trading",
        "symbol": "INFY",
        "description": "Two coordinated algorithmic sub-accounts ('USR-ALPHA' and 'USR-BETA') execute 6 consecutive matched trades of 450 shares at identical prices with zero change in net inventory, fabricating 2,700 shares of artificial volume.",
        "params": {
            "order_size": 450,
            "round_trips": 6,
            "net_delta_pct": 0.0,
            "price_variance_pct": 0.05,
            "participants": 2,
            "volume": 2700,
        },
        "expected_detection": "WASH-03",
        "expected_verdict": "CONFIRMED_SIMULATION",
    },
    "SCN_PUMP_DUMP": {
        "id": "SCN_PUMP_DUMP",
        "title": "Micro-Cap Aggressive Ramp & Dump (Pump & Dump)",
        "pattern": "Pump and Dump",
        "symbol": "BTCUSDT",
        "description": "A syndicate executes high-frequency aggressive market buys driving price up +12.4% over 90 seconds, followed immediately by heavy sell distribution that erases 95% of the gains within 60 seconds.",
        "params": {
            "order_size": 2500,
            "runup_pct": 12.4,
            "reversal_pct": 95.0,
            "cycle_duration_sec": 150,
            "participants": 3,
            "volume": 7500,
        },
        "expected_detection": "PUMP-04",
        "expected_verdict": "CONFIRMED_SIMULATION",
    },
    "SCN_UNUSUAL_VOLUME": {
        "id": "SCN_UNUSUAL_VOLUME",
        "title": "Isolated Volume Explosion (Abnormal Surge)",
        "pattern": "Unusual Volume",
        "symbol": "HDFCBANK",
        "description": "Trading volume surges to 6.2x the 20-period rolling median within a single 5-minute interval, with 78% of the volume accounted for by a single unverified clearing participant.",
        "params": {
            "volume_multiplier": 6.2,
            "concentration_pct": 78.0,
            "participants": 1,
            "volume": 35000,
        },
        "expected_detection": "VOL-05",
        "expected_verdict": "CONFIRMED_SIMULATION",
    },
    "SCN_ABNORMAL_PRICE": {
        "id": "SCN_ABNORMAL_PRICE",
        "title": "Flash Sweep Volatility Shock (Price Anomaly)",
        "pattern": "Abnormal Price Movement",
        "symbol": "RELIANCE",
        "description": "A rapid series of aggressive market orders consumes 8 levels of book depth in 12 seconds, resulting in a 4.1 sigma price divergence that triggers surveillance circuit checks.",
        "params": {
            "sigma_deviation": 4.1,
            "time_window_sec": 12,
            "depth_consumed_pct": 85.0,
            "participants": 1,
            "price_impact_pct": 2.8,
            "volume": 5000,
        },
        "expected_detection": "PRICE-06",
        "expected_verdict": "CONFIRMED_SIMULATION",
    },
    "SCN_BENIGN_MARKET_MAKER": {
        "id": "SCN_BENIGN_MARKET_MAKER",
        "title": "Algorithmic Market Maker Re-quoting (False Positive Benchmark)",
        "pattern": "Benign Market Making",
        "symbol": "TCS",
        "description": "A bona-fide market maker continuously updates bids and asks as fair-value drifts. While cancellation latency is low (450ms) and cancel rate is 72%, order sizes are normal (0.8x median) and bilateral volume is balanced with active fills.",
        "params": {
            "order_size": 40,
            "order_size_ratio": 0.85,
            "cancel_latency_ms": 450,
            "fill_percentage": 24.0,
            "participants": 1,
            "price_impact_pct": 0.05,
            "volume": 800,
        },
        "expected_detection": None,
        "expected_verdict": "FALSE_POSITIVE",
    },
}


# =============================================================================
# SURVEILLANCE ACADEMY & CHALLENGES
# =============================================================================

SURVEILLANCE_LESSONS = [
    {
        "id": "LESSON-01",
        "title": "Market Surveillance 101: Guarding Financial Integrity",
        "category": "Fundamentals",
        "read_time": "3 min",
        "summary": "How modern exchanges monitor trillions in turnover through automated real-time surveillance, trade reconstitution, and behavioral pattern recognition.",
        "content": (
            "Exchange surveillance systems act as the digital radar of financial markets. "
            "Unlike traditional accounting audits that occur months after the fact, market surveillance engines "
            "process every order submission, modification, cancellation, and execution in nanoseconds.\n\n"
            "Key Surveillance Objectives:\n"
            "1. Preserving Fair Price Discovery: Ensuring market prices reflect genuine supply and demand.\n"
            "2. Protecting Order Book Integrity: Preventing phantom liquidity designed to deceive execution algorithms.\n"
            "3. Maintaining Orderly Markets: Detecting sudden liquidity drains, abusive volatility sweeps, and runaway algorithms.\n"
            "4. Regulatory Compliance: Fulfilling statutory oversight obligations under SEBI, US SEC/CFTC, and EU MiFID II."
        ),
    },
    {
        "id": "LESSON-02",
        "title": "Order Book Deception: Spoofing vs. Layering",
        "category": "Order Book Manipulation",
        "read_time": "4 min",
        "summary": "Understanding non-bona fide orders, Order-to-Trade Ratios (OTR), phantom depth walls, and the mathematical signature of deceptive intent.",
        "content": (
            "Spoofing and Layering are predatory strategies where a participant enters orders with the predetermined "
            "intent to cancel them before execution.\n\n"
            "• Spoofing: Typically uses a single massive order positioned just outside the BBO to create immediate "
            "panic or momentum. The spoofer trades on the opposite side, then pulls the wall in milliseconds.\n\n"
            "• Layering: Stacks multiple orders across multiple price levels. By distributing volume across 3 or 4 tiers, "
            "the manipulator tricks VWAP algorithms and retail traders into believing deep institutional support exists.\n\n"
            "Exchange Defense: Surveillance algorithms track Order-to-Trade Ratios (OTR) and cancellation speed distributions "
            "to differentiate manipulative patterns from genuine quoting."
        ),
    },
    {
        "id": "LESSON-03",
        "title": "Fabricating Liquidity: Wash Trading & Circular Volume",
        "category": "Volume Manipulation",
        "read_time": "4 min",
        "summary": "How artificial volume distorts market rankings, deceives liquidity screeners, and how counterparty cluster analysis exposes self-matching.",
        "content": (
            "Wash Trading involves transactions where no genuine change of beneficial ownership occurs. "
            "The buyer and seller are either the exact same legal entity, or coordinated sub-accounts operating under common control.\n\n"
            "Why Bad Actors Wash Trade:\n"
            "• Artificial Liquidity: Pumping exchange rankings to attract retail liquidity.\n"
            "• Fee & Token Farming: Exploiting maker rebates or trading reward mechanisms.\n"
            "• Tax Manipulation: Establishing synthetic capital losses through synchronized off-market crosses.\n\n"
            "Surveillance Methods: Graph network analysis connects beneficial account IDs, shared IP ranges, funding wallets, "
            "and calculates net economic delta relative to gross turnover."
        ),
    },
    {
        "id": "LESSON-04",
        "title": "The False Positive Dilemma: Protecting Legitimate Market Makers",
        "category": "Surveillance Ethics & Precision",
        "read_time": "5 min",
        "summary": "Why aggressive trading is not always fraud. How surveillance analysts avoid accusing high-frequency market makers and arbitrageurs.",
        "content": (
            "A critical danger in financial surveillance is the 'False Positive' trap—misidentifying lawful, beneficial "
            "market-making activities as malicious market abuse.\n\n"
            "Legitimate High-Cancellation Scenarios:\n"
            "• Market Makers: Constantly cancel and replace quotes hundreds of times per second as underlying asset prices drift.\n"
            "• Latency Arbitrage: Algorithmic traders pulling resting quotes when external reference prices shift.\n"
            "• Iceberg Orders: Large institutional orders executing in small visible slices.\n\n"
            "Surveillance Rule of Law: Every alert must provide multi-dimensional corroborating evidence—not just a high cancellation rate, "
            "but proof of asymmetric contra-side execution or self-matching benefits."
        ),
    },
]

SURVEILLANCE_CHALLENGES = [
    {
        "id": "CHALLENGE-01",
        "title": "Case #101: The Disappearing Bid Wall",
        "difficulty": "BEGINNER",
        "symbol": "RELIANCE",
        "brief": (
            "At 11:02:14.210, a buy order for 2,500 shares (7.2x average depth) is posted at ₹1,182.90. "
            "At 11:02:14.390 (180ms later), the trader executes an aggressive market sell of 300 shares at ₹1,183.10. "
            "At 11:02:14.410, the 2,500-share bid order is completely cancelled with 0 fills."
        ),
        "options": [
            {"id": "A", "text": "Spoofing (SPOOF-01)", "is_correct": True},
            {"id": "B", "text": "Wash Trading (WASH-03)", "is_correct": False},
            {"id": "C", "text": "Legitimate Market Making (Benign)", "is_correct": False},
            {"id": "D", "text": "Abnormal Price Volatility (PRICE-06)", "is_correct": False},
        ],
        "evidence_metrics": {
            "order_size_ratio": 7.2,
            "cancel_latency_ms": 200,
            "fill_rate_pct": 0.0,
            "contra_execution": "YES (Sell filled while fake bid rested)",
        },
        "explanation": "This is textbook Spoofing. The massive bid was posted to create false upward momentum, allowing the trader to exit their sell at a higher price before pulling the fake wall with 0 fills.",
        "points": 100,
    },
    {
        "id": "CHALLENGE-02",
        "title": "Case #102: The Synchronized Bots",
        "difficulty": "INTERMEDIATE",
        "symbol": "INFY",
        "brief": (
            "Between 14:10:00 and 14:12:00, Account A and Account B execute 8 matched trades of exactly 500 shares each "
            "at ₹1,825.00. Account A sells to Account B, and within 4 seconds, Account B sells back to Account A at the same price. "
            "Net inventory change across both accounts after 4,000 shares traded is exactly 0."
        ),
        "options": [
            {"id": "A", "text": "Order Book Layering (LAYER-02)", "is_correct": False},
            {"id": "B", "text": "Wash Trading (WASH-03)", "is_correct": True},
            {"id": "C", "text": "Pump and Dump (PUMP-04)", "is_correct": False},
            {"id": "D", "text": "Routine Algorithmic TWAP (Benign)", "is_correct": False},
        ],
        "evidence_metrics": {
            "net_inventory_delta": 0,
            "matched_round_trips": 8,
            "price_delta": "0.00%",
            "volume_fabricated": 4000,
        },
        "explanation": "This represents circular Wash Trading. The matched round-trips generated 4,000 shares of artificial volume with zero economic risk and no change in beneficial ownership.",
        "points": 120,
    },
    {
        "id": "CHALLENGE-03",
        "title": "Case #103: The Sell-Side Staircase",
        "difficulty": "INTERMEDIATE",
        "symbol": "TCS",
        "brief": (
            "A trader enters 4 limit sell orders of 350 shares each at ₹3,481, ₹3,482, ₹3,483, and ₹3,484. "
            "Together they represent 80% of visible offer depth. 600ms later, the trader's resting buy order of 800 shares at ₹3,478 fills completely. "
            "Immediately after the buy fills, all 4 sell orders are cancelled simultaneously."
        ),
        "options": [
            {"id": "A", "text": "Order Book Layering (LAYER-02)", "is_correct": True},
            {"id": "B", "text": "Spoofing (SPOOF-01)", "is_correct": False},
            {"id": "C", "text": "Unusual Volume Surge (VOL-05)", "is_correct": False},
            {"id": "D", "text": "Index Arbitrage Rebalance (Benign)", "is_correct": False},
        ],
        "evidence_metrics": {
            "stacked_depth_tiers": 4,
            "cancellation_rate_pct": 100.0,
            "contra_execution_filled": "YES (800 shares bought at lower price)",
        },
        "explanation": "This is Order Book Layering. By stacking 4 tiers of fake sell orders, the trader created artificial downward pressure, pushing sellers down to fill their resting buy order before cancelling the sell ladder.",
        "points": 140,
    },
    {
        "id": "CHALLENGE-04",
        "title": "Case #104: The Telegram Rocket",
        "difficulty": "ADVANCED",
        "symbol": "BTCUSDT",
        "brief": (
            "A speculative token surges +16.8% in 2 minutes as automated buy sweeps consume thin liquidity. "
            "Social media channels report sudden hype. Exactly 45 seconds after reaching peak price, two primary wallets "
            "dump massive market sell orders, collapsing the price by -92% and leaving retail buyers stranded with heavy losses."
        ),
        "options": [
            {"id": "A", "text": "Wash Trading (WASH-03)", "is_correct": False},
            {"id": "B", "text": "Pump and Dump Scheme (PUMP-04)", "is_correct": True},
            {"id": "C", "text": "Order Book Layering (LAYER-02)", "is_correct": False},
            {"id": "D", "text": "Normal Volatility Breakout (Benign)", "is_correct": False},
        ],
        "evidence_metrics": {
            "markup_runup_pct": 16.8,
            "reversal_dump_pct": 92.0,
            "cycle_duration_sec": 165,
            "wallet_concentration": "2 primary distributing wallets",
        },
        "explanation": "Classic Pump and Dump scheme. An orchestrated markup pumped the price to lure in breakout buyers, followed by immediate exit dumping that exhausted market liquidity.",
        "points": 160,
    },
    {
        "id": "CHALLENGE-05",
        "title": "Case #105: The Accused Market Maker",
        "difficulty": "ADVANCED",
        "symbol": "HDFCBANK",
        "brief": (
            "During a volatile morning session, Account MM-1 cancels and replaces orders 450 times in 30 seconds. "
            "Average cancellation latency is 350ms, resulting in an Order-to-Trade Ratio (OTR) of 18:1. "
            "However, order sizes average 25 shares (0.5x median book size), orders are placed equally on both Bids and Asks, "
            "and MM-1 provided ₹4.2 Lakhs of two-sided execution fills."
        ),
        "options": [
            {"id": "A", "text": "Spoofing Attack (SPOOF-01)", "is_correct": False},
            {"id": "B", "text": "Order Book Layering (LAYER-02)", "is_correct": False},
            {"id": "C", "text": "Legitimate Market Making (FALSE POSITIVE)", "is_correct": True},
            {"id": "D", "text": "Wash Trading (WASH-03)", "is_correct": False},
        ],
        "evidence_metrics": {
            "order_size_ratio": 0.5,
            "two_sided_quoting": "YES (Equal Bid & Ask updates)",
            "actual_fills_executed": 25,
            "net_capital_provided": "₹4.2 Lakhs two-sided liquidity",
        },
        "explanation": "EXCELLENT ANALYSIS: This is a FALSE POSITIVE. The high cancellation rate and low latency reflect lawful algorithmic market-making adapting to shifting fair values, not manipulation.",
        "points": 200,
    },
]


# =============================================================================
# DETERMINISTIC SURVEILLANCE DETECTION ENGINES
# =============================================================================

def detect_spoofing(params: Dict[str, Any], thresholds: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Evaluate whether an order behavior pattern constitutes Spoofing."""
    cfg = thresholds or DEFAULT_THRESHOLDS["SPOOFING"]
    size_ratio = float(params.get("order_size_ratio", 0.0))
    if size_ratio == 0.0 and "order_size" in params:
        size_ratio = float(params["order_size"]) / 300.0
    latency_ms = float(params.get("cancel_latency_ms", 99999))
    fill_rate = float(params.get("fill_percentage", 0.0))

    # Evaluate deterministic thresholds
    is_spoof = (
        size_ratio >= cfg["order_size_ratio"] and
        latency_ms <= cfg["cancel_latency_ms"] and
        fill_rate <= cfg["fill_rate_max_pct"]
    )

    if not is_spoof:
        return None

    return {
        "rule_id": "SPOOF-01",
        "pattern": "Spoofing",
        "severity": "CRITICAL",
        "status": "CONFIRMED_SIMULATION",
        "metrics": {
            "order_size_ratio": round(size_ratio, 2),
            "cancel_latency_ms": round(latency_ms, 1),
            "fill_percentage": round(fill_rate, 2),
            "threshold_size_ratio": cfg["order_size_ratio"],
            "threshold_latency_ms": cfg["cancel_latency_ms"],
            "threshold_fill_pct": cfg["fill_rate_max_pct"],
        },
        "explanation": {
            "what_detected": "Large outsized order placed and rapidly cancelled before execution.",
            "rule_triggered": "SPOOF-01 (Order Size Ratio >= 3.0x AND Cancel Latency <= 1500ms AND Fill Rate <= 5%)",
            "evidence_summary": f"Observed order size {size_ratio:.1f}x median book depth, cancelled in {latency_ms:.0f}ms with {fill_rate:.1f}% fill.",
            "why_unusual": "Order creates false impression of deep demand/supply to induce other participants to trade at dislocated prices.",
            "additional_info_required": "Corroboration of contra-side trade executions across affiliated accounts; FIX message audit trails.",
            "false_positive_risk": "Low. However, sudden headline news could cause a legitimate large order to be cancelled quickly.",
        },
    }


def detect_layering(params: Dict[str, Any], thresholds: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Evaluate whether multi-tier order book activity constitutes Layering."""
    cfg = thresholds or DEFAULT_THRESHOLDS["LAYERING"]
    tier_count = int(params.get("tier_count", 1))
    cancel_rate = float(params.get("cancel_rate_pct", 0.0))

    is_layering = (
        tier_count >= cfg["min_depth_tiers"] and
        cancel_rate >= cfg["cancel_rate_min_pct"]
    )

    if not is_layering:
        return None

    return {
        "rule_id": "LAYER-02",
        "pattern": "Layering",
        "severity": "CRITICAL",
        "status": "CONFIRMED_SIMULATION",
        "metrics": {
            "tier_count": tier_count,
            "cancel_rate_pct": round(cancel_rate, 1),
            "threshold_min_tiers": cfg["min_depth_tiers"],
            "threshold_cancel_pct": cfg["cancel_rate_min_pct"],
        },
        "explanation": {
            "what_detected": "Multi-tier laddered order placements on one side of book with high cancellation rate.",
            "rule_triggered": "LAYER-02 (Stacked Tiers >= 3 AND Cancellation Rate >= 80%)",
            "evidence_summary": f"Observed {tier_count} stacked depth tiers with {cancel_rate:.1f}% cancellation rate.",
            "why_unusual": "Simulates synthetic market depth across multiple prices to manipulate fair-value algorithms before execution on contra side.",
            "additional_info_required": "Sub-account linkage and trading records on the opposite side of the book during the layering window.",
            "false_positive_risk": "Algorithmic scale-in orders or grid trading strategies that cancel when market conditions shift.",
        },
    }


def detect_wash_trading(params: Dict[str, Any], thresholds: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Evaluate whether matched trades constitute Wash Trading."""
    cfg = thresholds or DEFAULT_THRESHOLDS["WASH_TRADING"]
    round_trips = int(params.get("round_trips", 0))
    net_delta = float(params.get("net_delta_pct", 100.0))
    price_var = float(params.get("price_variance_pct", 10.0))

    is_wash = (
        round_trips >= cfg["min_round_trips"] and
        net_delta <= cfg["max_net_delta_pct"] and
        price_var <= cfg["max_price_variance_pct"]
    )

    if not is_wash:
        return None

    return {
        "rule_id": "WASH-03",
        "pattern": "Wash Trading",
        "severity": "HIGH",
        "status": "CONFIRMED_SIMULATION",
        "metrics": {
            "round_trips": round_trips,
            "net_delta_pct": round(net_delta, 2),
            "price_variance_pct": round(price_var, 3),
            "threshold_round_trips": cfg["min_round_trips"],
            "threshold_max_delta": cfg["max_net_delta_pct"],
        },
        "explanation": {
            "what_detected": "Circular transactions executed between coordinated accounts with near-zero change in net position.",
            "rule_triggered": "WASH-03 (Round Trips >= 2 AND Net Inventory Delta <= 5% AND Price Variance <= 0.20%)",
            "evidence_summary": f"{round_trips} matched round trips detected with {net_delta:.2f}% net delta and {price_var:.3f}% price variance.",
            "why_unusual": "Trades generate misleading volume without genuine transfer of market risk or beneficial ownership.",
            "additional_info_required": "Beneficial ownership registers, KYC documentation, shared IP/device fingerprints.",
            "false_positive_risk": "Independent desks within the same financial institution inadvertently crossing orders in liquid markets.",
        },
    }


def detect_pump_and_dump(params: Dict[str, Any], thresholds: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Evaluate whether price markup and collapse constitutes a Pump and Dump scheme."""
    cfg = thresholds or DEFAULT_THRESHOLDS["PUMP_AND_DUMP"]
    runup = float(params.get("runup_pct", 0.0))
    reversal = float(params.get("reversal_pct", 0.0))
    duration = float(params.get("cycle_duration_sec", 99999))

    is_pump = (
        runup >= cfg["min_runup_pct"] and
        reversal >= cfg["min_reversal_pct"] and
        duration <= cfg["max_cycle_duration_sec"]
    )

    if not is_pump:
        return None

    return {
        "rule_id": "PUMP-04",
        "pattern": "Pump and Dump",
        "severity": "CRITICAL",
        "status": "CONFIRMED_SIMULATION",
        "metrics": {
            "runup_pct": round(runup, 2),
            "reversal_pct": round(reversal, 2),
            "duration_sec": round(duration, 0),
            "threshold_runup": cfg["min_runup_pct"],
            "threshold_reversal": cfg["min_reversal_pct"],
        },
        "explanation": {
            "what_detected": "Rapid artificial price markup followed by sudden, heavy distribution and liquidity withdrawal.",
            "rule_triggered": "PUMP-04 (Price Runup >= 8% AND Reversal >= 70% within 300 seconds)",
            "evidence_summary": f"Observed +{runup:.1f}% surge followed by {reversal:.1f}% rapid collapse in {duration:.0f} seconds.",
            "why_unusual": "Creates artificial FOMO breakout to dump accumulated inventory onto retail buyers.",
            "additional_info_required": "Social media / chat channel activity timestamps; historical inventory accumulation logs of dumping accounts.",
            "false_positive_risk": "Earnings announcement volatility or biotech trial results creating extreme two-sided repricing.",
        },
    }


def detect_unusual_volume(params: Dict[str, Any], thresholds: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Evaluate whether volume constitutes an Unusual Volume surge."""
    cfg = thresholds or DEFAULT_THRESHOLDS["UNUSUAL_VOLUME"]
    vol_mult = float(params.get("volume_multiplier", 1.0))
    conc = float(params.get("concentration_pct", 0.0))

    is_unusual = vol_mult >= cfg["volume_multiplier"]

    if not is_unusual:
        return None

    return {
        "rule_id": "VOL-05",
        "pattern": "Unusual Volume",
        "severity": "WARNING",
        "status": "CONFIRMED_SIMULATION",
        "metrics": {
            "volume_multiplier": round(vol_mult, 2),
            "concentration_pct": round(conc, 1),
            "threshold_multiplier": cfg["volume_multiplier"],
        },
        "explanation": {
            "what_detected": "Trading volume spike significantly exceeding the rolling moving average baseline.",
            "rule_triggered": "VOL-05 (Volume Multiplier >= 4.0x baseline)",
            "evidence_summary": f"Volume spike of {vol_mult:.1f}x baseline detected, top participant concentration {conc:.1f}%.",
            "why_unusual": "Uncharacteristic liquidity surge without general market correlation can indicate pre-announcement positioning.",
            "additional_info_required": "News releases, corporate disclosures, insider lists, option flow corroboration.",
            "false_positive_risk": "Index rebalancing days, ETF creations/redemptions, or market-wide macro news.",
        },
    }


def detect_abnormal_price(params: Dict[str, Any], thresholds: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Evaluate whether a price movement constitutes an Abnormal Price Anomaly."""
    cfg = thresholds or DEFAULT_THRESHOLDS["ABNORMAL_PRICE"]
    sigma = float(params.get("sigma_deviation", 0.0))
    time_window = float(params.get("time_window_sec", 99999))

    is_abnormal = (
        sigma >= cfg["sigma_deviation"] and
        time_window <= cfg["max_time_window_sec"]
    )

    if not is_abnormal:
        return None

    return {
        "rule_id": "PRICE-06",
        "pattern": "Abnormal Price Movement",
        "severity": "WARNING",
        "status": "CONFIRMED_SIMULATION",
        "metrics": {
            "sigma_deviation": round(sigma, 2),
            "time_window_sec": round(time_window, 1),
            "threshold_sigma": cfg["sigma_deviation"],
            "threshold_max_window": cfg["max_time_window_sec"],
        },
        "explanation": {
            "what_detected": "Sudden price movement exceeding 3 standard deviations in ultra-short interval.",
            "rule_triggered": "PRICE-06 (Sigma Deviation >= 3.0 within 30 seconds)",
            "evidence_summary": f"Observed {sigma:.1f} sigma price shift over {time_window:.0f} seconds.",
            "why_unusual": "Price move disconnected from broader index and sector momentum, indicating order book vacuum or aggressive sweep.",
            "additional_info_required": "Full order book level-3 tick logs, stop-loss trigger cascade logs, circuit breaker status.",
            "false_positive_risk": "Flash news headlines, geopolitical breaking developments, or foreign market shockwaves.",
        },
    }


def run_surveillance_analysis(scenario_params: Dict[str, Any], thresholds: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run all detection modules against scenario parameters and synthesize investigation output."""
    detectors = [
        detect_spoofing,
        detect_layering,
        detect_wash_trading,
        detect_pump_and_dump,
        detect_unusual_volume,
        detect_abnormal_price,
    ]

    detected_alerts: List[Dict[str, Any]] = []

    for detector in detectors:
        res = detector(scenario_params, thresholds)
        if res:
            detected_alerts.append(res)

    symbol = str(scenario_params.get("symbol", "RELIANCE"))
    investigation_id = f"INV-2026-{uuid.uuid4().hex[:6].upper()}"
    alert_id = f"ALT-2026-{uuid.uuid4().hex[:4].upper()}"
    now_iso = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # If no manipulative rule triggered, classify as clean / false positive benchmark
    if not detected_alerts:
        return {
            "status": "CLEARED",
            "verdict": "FALSE_POSITIVE",
            "investigation_id": investigation_id,
            "alert_id": alert_id,
            "symbol": symbol,
            "detected_at": now_iso,
            "severity": "BENIGN",
            "primary_pattern": "Legitimate Trading / False Positive",
            "rules_triggered": [],
            "metrics": scenario_params,
            "explanation": {
                "what_detected": "Normal trading activity within statistical parameters.",
                "rule_triggered": "NONE (All rules evaluated clean)",
                "evidence_summary": "Order sizes, cancellation latencies, and execution ratios remain within normal market parameters.",
                "why_unusual": "Activity does not constitute market manipulation.",
                "additional_info_required": "None. Activity conforms to legitimate liquidity provision or ordinary retail order flow.",
                "false_positive_risk": "N/A - Correctly identified as benign trading.",
            },
            "related_orders": generate_synthetic_related_orders(symbol, "BENIGN", scenario_params),
            "timeline": generate_synthetic_timeline("BENIGN", scenario_params),
        }

    # Primary detected alert
    primary = detected_alerts[0]
    return {
        "status": "FLAGGED",
        "verdict": primary["status"],
        "investigation_id": investigation_id,
        "alert_id": alert_id,
        "symbol": symbol,
        "detected_at": now_iso,
        "severity": primary["severity"],
        "primary_pattern": primary["pattern"],
        "rule_id": primary["rule_id"],
        "rules_triggered": [a["rule_id"] for a in detected_alerts],
        "metrics": primary["metrics"],
        "explanation": primary["explanation"],
        "related_orders": generate_synthetic_related_orders(symbol, primary["pattern"], scenario_params),
        "timeline": generate_synthetic_timeline(primary["pattern"], scenario_params),
    }


# =============================================================================
# SYNTHETIC EVIDENCE GENERATORS
# =============================================================================

def generate_synthetic_related_orders(symbol: str, pattern: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate realistic audit trail orders for investigation inspection."""
    size = int(params.get("order_size", 1000))
    base_price = 1183.00 if symbol == "RELIANCE" else (3480.00 if symbol == "TCS" else 1820.00)

    if pattern == "Spoofing":
        return [
            {"order_id": "ORD-SP-101", "time": "10:14:02.100", "account": "ACC-SUSP-77", "side": "BUY", "price": base_price, "qty": size, "status": "SUBMITTED", "details": "Large non-bona fide buy wall placed"},
            {"order_id": "ORD-LG-202", "time": "10:14:02.240", "account": "ACC-SUSP-77", "side": "SELL", "price": base_price + 0.35, "qty": 150, "status": "FILLED", "details": "Contra sell executed into retail market buys"},
            {"order_id": "ORD-SP-101", "time": "10:14:02.380", "account": "ACC-SUSP-77", "side": "BUY", "price": base_price, "qty": size, "status": "CANCELLED", "details": "Buy wall cancelled in 280ms (0 fills)"},
        ]
    elif pattern == "Layering":
        return [
            {"order_id": "ORD-LY-01", "time": "10:14:05.100", "account": "ACC-LAYER-01", "side": "SELL", "price": base_price + 0.50, "qty": 400, "status": "CANCELLED", "details": "Layer tier 1 cancelled"},
            {"order_id": "ORD-LY-02", "time": "10:14:05.120", "account": "ACC-LAYER-01", "side": "SELL", "price": base_price + 0.70, "qty": 400, "status": "CANCELLED", "details": "Layer tier 2 cancelled"},
            {"order_id": "ORD-LY-03", "time": "10:14:05.140", "account": "ACC-LAYER-01", "side": "SELL", "price": base_price + 0.90, "qty": 400, "status": "CANCELLED", "details": "Layer tier 3 cancelled"},
            {"order_id": "ORD-EX-04", "time": "10:14:05.350", "account": "ACC-LAYER-01", "side": "BUY", "price": base_price - 0.20, "qty": 800, "status": "FILLED", "details": "Contra buy filled at depressed price"},
        ]
    elif pattern == "Wash Trading":
        return [
            {"order_id": "ORD-WSH-01", "time": "10:14:08.010", "account": "ACC-BOT-ALPHA", "side": "BUY", "price": base_price, "qty": 500, "status": "FILLED", "details": "Matched against ACC-BOT-BETA"},
            {"order_id": "ORD-WSH-02", "time": "10:14:08.012", "account": "ACC-BOT-BETA", "side": "SELL", "price": base_price, "qty": 500, "status": "FILLED", "details": "Matched against ACC-BOT-ALPHA"},
            {"order_id": "ORD-WSH-03", "time": "10:14:12.450", "account": "ACC-BOT-BETA", "side": "BUY", "price": base_price, "qty": 500, "status": "FILLED", "details": "Round-trip re-match (Net delta 0)"},
            {"order_id": "ORD-WSH-04", "time": "10:14:12.452", "account": "ACC-BOT-ALPHA", "side": "SELL", "price": base_price, "qty": 500, "status": "FILLED", "details": "Round-trip re-match (Net delta 0)"},
        ]
    elif pattern == "Pump and Dump":
        return [
            {"order_id": "ORD-PD-01", "time": "10:14:15.000", "account": "ACC-SYND-01", "side": "BUY", "price": base_price, "qty": 1200, "status": "FILLED", "details": "Aggressive market sweep buys (+5.2%)"},
            {"order_id": "ORD-PD-02", "time": "10:14:25.000", "account": "ACC-SYND-02", "side": "BUY", "price": base_price * 1.08, "qty": 1500, "status": "FILLED", "details": "Secondary markup sweep (+12.4% peak)"},
            {"order_id": "ORD-PD-03", "time": "10:14:45.000", "account": "ACC-SYND-01", "side": "SELL", "price": base_price * 1.07, "qty": 2700, "status": "FILLED", "details": "Heavy distribution dump (-95% reversal)"},
        ]
    else:
        return [
            {"order_id": "ORD-BN-01", "time": "10:14:20.100", "account": "ACC-MM-01", "side": "BUY", "price": base_price - 0.05, "qty": 50, "status": "FILLED", "details": "Normal two-sided passive quote"},
            {"order_id": "ORD-BN-02", "time": "10:14:20.100", "account": "ACC-MM-01", "side": "SELL", "price": base_price + 0.05, "qty": 50, "status": "FILLED", "details": "Normal two-sided passive quote"},
            {"order_id": "ORD-BN-03", "time": "10:14:22.300", "account": "ACC-RET-88", "side": "BUY", "price": base_price, "qty": 20, "status": "FILLED", "details": "Ordinary retail order execution"},
        ]


def generate_synthetic_timeline(pattern: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Generate chronological timeline steps for the investigation workspace."""
    if pattern == "Spoofing":
        return [
            {"step": 1, "time": "T+000ms", "title": "Large Bid Injected", "desc": "1,800 share buy placed at ₹1,183.00 (5.5x median depth), shifting book imbalance to 84% BUY."},
            {"step": 2, "time": "T+140ms", "title": "Market Reaction", "desc": "Retail orders and momentum algorithms move ask prices higher to capture anticipated demand."},
            {"step": 3, "time": "T+240ms", "title": "Contra Execution", "desc": "Manipulator fills resting sell order for 150 shares at ₹1,183.35 at inflated price."},
            {"step": 4, "time": "T+280ms", "title": "Instant Cancellation", "desc": "Manipulator pulls the 1,800-share bid order with 0 fills. Surveillance rule SPOOF-01 triggers."},
        ]
    elif pattern == "Layering":
        return [
            {"step": 1, "time": "T+000ms", "title": "Tier 1 Placed", "desc": "400 shares offered at ₹3,481.00."},
            {"step": 2, "time": "T+080ms", "title": "Tiers 2-4 Stacked", "desc": "Consecutive asks placed at ₹3,482, ₹3,483, ₹3,484 creating false sell-side liquidity wall."},
            {"step": 3, "time": "T+420ms", "title": "Contra Buy Filled", "desc": "Trader fills 800-share buy at depressed price of ₹3,478.00."},
            {"step": 4, "time": "T+580ms", "title": "Simultaneous Pull", "desc": "All 4 sell orders cancelled simultaneously. Rule LAYER-02 triggers."},
        ]
    elif pattern == "Wash Trading":
        return [
            {"step": 1, "time": "T+000s", "title": "Initial Matched Cross", "desc": "Account Alpha sells 450 shares to Account Beta at ₹1,820.00."},
            {"step": 2, "time": "T+004s", "title": "Synchronized Reversal", "desc": "Account Beta sells 450 shares back to Account Alpha at ₹1,820.00."},
            {"step": 3, "time": "T+012s", "title": "Repeated Cycles", "desc": "Pattern repeats across 6 cycles. Net position delta remains exactly 0 shares."},
            {"step": 4, "time": "T+020s", "title": "Surveillance Flag", "desc": "Cluster analysis identifies common control and zero economic risk. Rule WASH-03 triggers."},
        ]
    elif pattern == "Pump and Dump":
        return [
            {"step": 1, "time": "T+000s", "title": "Aggressive Markup", "desc": "High-frequency buy sweeps consume 12 price levels, driving price up +12.4%."},
            {"step": 2, "time": "T+090s", "title": "Peak FOMO Phase", "desc": "Retail momentum traders follow volume; social media channels broadcast pump alerts."},
            {"step": 3, "time": "T+110s", "title": "Heavy Distribution", "desc": "Syndicate dumps large market sell orders into retail liquidity."},
            {"step": 4, "time": "T+150s", "title": "Market Collapse", "desc": "Price plunges -95% of previous run-up. Liquidity vacuum triggers PUMP-04 alert."},
        ]
    else:
        return [
            {"step": 1, "time": "T+000s", "title": "Order Placed", "desc": "Standard limit order entered within normal spread."},
            {"step": 2, "time": "T+010s", "title": "Passive Execution", "desc": "Order filled against incoming market order."},
            {"step": 3, "time": "T+015s", "title": "Surveillance Check", "desc": "All metrics within 1.0 sigma. Clean status maintained."},
        ]


# =============================================================================
# INVESTIGATION REPORT & CSV EXPORTERS
# =============================================================================

def generate_investigation_csv(investigation: Dict[str, Any]) -> str:
    """Generate RFC 4180 compliant CSV string of investigation orders and timeline."""
    lines = [
        "INVESTIGATION_ID,ALERT_ID,SYMBOL,PATTERN,SEVERITY,STATUS,DETECTED_AT",
        f'"{investigation.get("investigation_id")}","{investigation.get("alert_id")}","{investigation.get("symbol")}","{investigation.get("primary_pattern")}","{investigation.get("severity")}","{investigation.get("status")}","{investigation.get("detected_at")}"',
        "",
        "ORDER_RECORDS",
        "ORDER_ID,TIME,ACCOUNT,SIDE,PRICE,QUANTITY,STATUS,DETAILS",
    ]

    orders = investigation.get("related_orders", [])
    for ord_item in orders:
        lines.append(
            f'"{ord_item.get("order_id")}","{ord_item.get("time")}","{ord_item.get("account")}","{ord_item.get("side")}",{ord_item.get("price")},{ord_item.get("qty")},"{ord_item.get("status")}","{ord_item.get("details")}"'
        )

    lines.append("")
    lines.append("TIMELINE_EVENTS")
    lines.append("STEP,TIME_OFFSET,TITLE,DESCRIPTION")
    for tm in investigation.get("timeline", []):
        lines.append(f'{tm.get("step")},"{tm.get("time")}","{tm.get("title")}","{tm.get("desc")}"')

    return "\n".join(lines)


def generate_investigation_dossier(investigation: Dict[str, Any]) -> str:
    """Generate a clean, print-friendly text dossier for regulatory and compliance review."""
    expl = investigation.get("explanation", {})
    metrics = investigation.get("metrics", {})

    return f"""================================================================================
CHRONOSMATCH MARKET SURVEILLANCE & FRAUD DETECTION LAB
OFFICIAL SIMULATED INVESTIGATION DOSSIER
================================================================================
CASE REFERENCE    : {investigation.get('investigation_id')}
ALERT ID          : {investigation.get('alert_id')}
TARGET SYMBOL     : {investigation.get('symbol')}
PRIMARY PATTERN   : {investigation.get('primary_pattern')}
SEVERITY LEVEL    : {investigation.get('severity')}
CURRENT STATUS    : {investigation.get('status')}
TIMESTAMP         : {investigation.get('detected_at')}
================================================================================

1. EXECUTIVE SUMMARY & BEHAVIORAL DIAGNOSIS:
--------------------------------------------------------------------------------
Behavior Detected : {expl.get('what_detected', 'N/A')}
Rule Triggered    : {expl.get('rule_triggered', 'N/A')}
Evidence Summary  : {expl.get('evidence_summary', 'N/A')}

2. MICROSTRUCTURAL IMPACT & MARKET MECHANICS:
--------------------------------------------------------------------------------
Impact Analysis   : {expl.get('why_unusual', 'N/A')}
Required Corrob.  : {expl.get('additional_info_required', 'N/A')}
False Positive Risk: {expl.get('false_positive_risk', 'N/A')}

3. QUANTITATIVE EVIDENCE METRICS:
--------------------------------------------------------------------------------
{chr(10).join([f"  • {k:<28}: {v}" for k, v in metrics.items()])}

4. REGULATORY DISCLAIMER:
--------------------------------------------------------------------------------
This report is generated by ChronosMatch as an educational financial surveillance
simulation. Findings represent mathematical pattern matching against simulated
market microstructure events and do not constitute real-world legal accusations.
================================================================================
"""
