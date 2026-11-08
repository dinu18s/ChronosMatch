"""Macroeconomic scenario simulator and transmission engine for ChronosMatch."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import math


ECONOMIC_EVENTS = [
    {
        "id": "EVT-RBI-REPO-2026",
        "name": "RBI Monetary Policy Committee (MPC) Rate Decision",
        "category": "Interest Rates",
        "region": "India",
        "frequency": "Bi-monthly",
        "previous": "6.50%",
        "expected": "6.50%",
        "actual": "6.50%",
        "surprise": "0.00%",
        "importance": "HIGH",
        "release_date": "2026-10-09",
        "next_date": "2026-12-06",
        "is_simulated": True,
        "description": "Reserve Bank of India repo rate setting policy stance, guiding bank loan benchmarks and sovereign bond yields.",
        "transmission_channel": "Repo rate changes directly impact Marginal Cost of Funds Based Lending Rate (MCLR), home loans, corporate debt costs, and banking NIMs."
    },
    {
        "id": "EVT-FED-FUNDS-2026",
        "name": "US Federal Reserve FOMC Interest Rate Decision",
        "category": "Interest Rates",
        "region": "United States",
        "frequency": "6-8 weeks",
        "previous": "5.25% - 5.50%",
        "expected": "5.00% - 5.25%",
        "actual": "5.00% - 5.25%",
        "surprise": "-0.25%",
        "importance": "HIGH",
        "release_date": "2026-09-18",
        "next_date": "2026-11-07",
        "is_simulated": True,
        "description": "US Federal Reserve benchmark target range. The world's primary global discount rate anchor.",
        "transmission_channel": "Fed rate cuts reduce US Treasury yields, compress the dollar index (DXY), and encourage global liquidity flows into emerging market equities."
    },
    {
        "id": "EVT-IN-CPI-2026",
        "name": "India Consumer Price Index (CPI) Inflation YoY",
        "category": "Inflation",
        "region": "India",
        "frequency": "Monthly",
        "previous": "5.49%",
        "expected": "5.20%",
        "actual": "5.10%",
        "surprise": "-0.10%",
        "importance": "HIGH",
        "release_date": "2026-10-14",
        "next_date": "2026-11-12",
        "is_simulated": True,
        "description": "Headline retail inflation gauge monitored under RBI's 4% (+/-2%) flexible inflation targeting framework.",
        "transmission_channel": "Lower inflation provides headroom for central bank monetary easing, boosting consumer discretionary spending and bond valuations."
    },
    {
        "id": "EVT-US-CPI-2026",
        "name": "US Consumer Price Index (CPI) Inflation YoY",
        "category": "Inflation",
        "region": "United States",
        "frequency": "Monthly",
        "previous": "2.90%",
        "expected": "2.60%",
        "actual": "2.50%",
        "surprise": "-0.10%",
        "importance": "HIGH",
        "release_date": "2026-10-10",
        "next_date": "2026-11-13",
        "is_simulated": True,
        "description": "Key price pressures indicator determining real yields and US monetary policy trajectories.",
        "transmission_channel": "Cooling US inflation reduces bond yield pressures, easing global cost of capital and boosting tech stock valuations."
    },
    {
        "id": "EVT-IN-GDP-2026",
        "name": "India Real GDP Growth YoY",
        "category": "Economic Growth",
        "region": "India",
        "frequency": "Quarterly",
        "previous": "6.70%",
        "expected": "7.00%",
        "actual": "7.20%",
        "surprise": "+0.20%",
        "importance": "HIGH",
        "release_date": "2026-08-30",
        "next_date": "2026-11-29",
        "is_simulated": True,
        "description": "Comprehensive measure of total domestic output and national economic expansion across agriculture, manufacturing, and services.",
        "transmission_channel": "Stronger GDP expands corporate revenues, accelerates industrial credit demand, and drives foreign institutional capital inflows."
    },
    {
        "id": "EVT-US-GDP-2026",
        "name": "US GDP Annualized Growth Rate",
        "category": "Economic Growth",
        "region": "United States",
        "frequency": "Quarterly",
        "previous": "2.80%",
        "expected": "3.00%",
        "actual": "3.00%",
        "surprise": "0.00%",
        "importance": "HIGH",
        "release_date": "2026-09-26",
        "next_date": "2026-10-30",
        "is_simulated": True,
        "description": "Annualized pace of economic activity in the world's largest economy.",
        "transmission_channel": "Sustained US expansion sustains demand for global trade and Indian IT services exports, while mitigating recessionary fears."
    },
    {
        "id": "EVT-CRUDE-OIL-2026",
        "name": "Brent Crude Oil ($/Barrel)",
        "category": "Commodities",
        "region": "Global",
        "frequency": "Daily / Continuous",
        "previous": "$74.50",
        "expected": "$76.00",
        "actual": "$75.20",
        "surprise": "-$0.80",
        "importance": "MEDIUM",
        "release_date": "2026-10-24",
        "next_date": "Continuous",
        "is_simulated": True,
        "description": "Global benchmark crude oil price. High sensitivity driver for India's trade balance and fiscal deficit.",
        "transmission_channel": "Higher crude increases India's import bill, widens the Current Account Deficit (CAD), fuels domestic fuel inflation, and depresses auto/paint margins."
    },
    {
        "id": "EVT-USD-INR-2026",
        "name": "USD / INR Currency Exchange Rate",
        "category": "Forex",
        "region": "India / US",
        "frequency": "Daily / Continuous",
        "previous": "₹83.95",
        "expected": "₹84.10",
        "actual": "₹84.05",
        "surprise": "-₹0.05",
        "importance": "MEDIUM",
        "release_date": "2026-10-24",
        "next_date": "Continuous",
        "is_simulated": True,
        "description": "Bilateral foreign exchange rate between the Indian Rupee and the US Dollar.",
        "transmission_channel": "Rupee depreciation raises landed costs of imported electronics and crude, but provides windfall translation margins to IT exporters."
    },
    {
        "id": "EVT-IN-MFG-PMI-2026",
        "name": "India HSBC Manufacturing PMI",
        "category": "Business Activity",
        "region": "India",
        "frequency": "Monthly",
        "previous": "58.1",
        "expected": "58.5",
        "actual": "58.9",
        "surprise": "+0.4",
        "importance": "MEDIUM",
        "release_date": "2026-10-01",
        "next_date": "2026-11-04",
        "is_simulated": True,
        "description": "Purchasing Managers' Index surveying factory output, new orders, employment, and supplier deliveries (>50 indicates expansion).",
        "transmission_channel": "Robust manufacturing PMI signals capital expenditure recovery, factory capacity utilization, and corporate earnings momentum."
    },
    {
        "id": "EVT-US-UNEMPLOYMENT-2026",
        "name": "US Unemployment Rate (U-3)",
        "category": "Labor Market",
        "region": "United States",
        "frequency": "Monthly",
        "previous": "4.30%",
        "expected": "4.20%",
        "actual": "4.10%",
        "surprise": "-0.10%",
        "importance": "HIGH",
        "release_date": "2026-10-04",
        "next_date": "2026-11-01",
        "is_simulated": True,
        "description": "Percentage of total labor force that is unemployed and actively seeking work in the US.",
        "transmission_channel": "Tight labor markets support wage growth and consumer spending but can keep service inflation sticky, delaying central bank rate cuts."
    }
]


PRESET_SCENARIOS = {
    "HAWKISH_SHOCK": {
        "id": "HAWKISH_SHOCK",
        "name": "🦅 Aggressive Central Bank Rate Hikes",
        "description": "Coordinated monetary tightening: RBI hikes repo rate by 50 bps and US Fed hikes by 75 bps amidst sticky headline inflation (+1.0%).",
        "shocks": {
            "rbi_rate_bps": 50.0,
            "fed_rate_bps": 75.0,
            "crude_oil_pct": 5.0,
            "cpi_inflation_pct": 1.0,
            "gdp_growth_pct": -0.4,
            "usdinr_change_pct": 1.2
        }
    },
    "DOVISH_EASING": {
        "id": "DOVISH_EASING",
        "name": "🕊️ Dovish Monetary Easing & Rate Cuts",
        "description": "Global liquidity expansion: RBI cuts repo rate by 50 bps and US Fed cuts rates by 75 bps as inflation cools significantly (-1.2%).",
        "shocks": {
            "rbi_rate_bps": -50.0,
            "fed_rate_bps": -75.0,
            "crude_oil_pct": -8.0,
            "cpi_inflation_pct": -1.2,
            "gdp_growth_pct": 0.6,
            "usdinr_change_pct": -1.0
        }
    },
    "OIL_SURGE": {
        "id": "OIL_SURGE",
        "name": "🛢️ Geopolitical Energy Shock (Crude +30%)",
        "description": "Severe Middle East supply disruption causes Brent Crude to jump +30%, expanding India's trade deficit and driving rupee depreciation (+3.5%).",
        "shocks": {
            "rbi_rate_bps": 25.0,
            "fed_rate_bps": 25.0,
            "crude_oil_pct": 30.0,
            "cpi_inflation_pct": 1.8,
            "gdp_growth_pct": -0.8,
            "usdinr_change_pct": 3.5
        }
    },
    "STAGFLATION": {
        "id": "STAGFLATION",
        "name": "📉 Stagflation Squeeze (High Inflation, Stagnant Growth)",
        "description": "Worst-case macro environment: GDP growth slumps by -1.5% while CPI inflation spikes by +2.2% alongside a +20% crude oil surge.",
        "shocks": {
            "rbi_rate_bps": 50.0,
            "fed_rate_bps": 50.0,
            "crude_oil_pct": 20.0,
            "cpi_inflation_pct": 2.2,
            "gdp_growth_pct": -1.5,
            "usdinr_change_pct": 2.8
        }
    },
    "INDIA_GROWTH_BOOM": {
        "id": "INDIA_GROWTH_BOOM",
        "name": "🚀 India Capex & Manufacturing Boom",
        "description": "Strong domestic investment: Real GDP growth surges +1.5% above expectations, PMI hits multi-year highs, and currency strengthens.",
        "shocks": {
            "rbi_rate_bps": 0.0,
            "fed_rate_bps": -25.0,
            "crude_oil_pct": -5.0,
            "cpi_inflation_pct": -0.5,
            "gdp_growth_pct": 1.5,
            "usdinr_change_pct": -1.8
        }
    }
}


def _classify_stance(impact_pct: float) -> str:
    """Classify qualitative stance based on estimated percentage impact."""
    if impact_pct >= 2.5:
        return "Strongly Bullish"
    elif impact_pct >= 0.8:
        return "Moderately Bullish"
    elif impact_pct > -0.8:
        return "Neutral / Rangebound"
    elif impact_pct > -2.5:
        return "Moderately Bearish"
    else:
        return "Strongly Bearish"


def calculate_macro_impact(shocks: Dict[str, float]) -> Dict[str, Any]:
    """Calculate deterministic multi-asset and sector percentage impacts from macro shocks."""
    # Sanitize and extract shocks with safety boundaries
    rbi_bps = float(shocks.get("rbi_rate_bps", 0.0))
    fed_bps = float(shocks.get("fed_rate_bps", 0.0))
    oil_pct = float(shocks.get("crude_oil_pct", 0.0))
    cpi_pct = float(shocks.get("cpi_inflation_pct", 0.0))
    gdp_pct = float(shocks.get("gdp_growth_pct", 0.0))
    usdinr_pct = float(shocks.get("usdinr_change_pct", 0.0))

    # Clamp extreme inputs to realistic simulated boundaries
    rbi_bps = max(-300.0, min(500.0, rbi_bps))
    fed_bps = max(-300.0, min(500.0, fed_bps))
    oil_pct = max(-60.0, min(120.0, oil_pct))
    cpi_pct = max(-5.0, min(10.0, cpi_pct))
    gdp_pct = max(-5.0, min(6.0, gdp_pct))
    usdinr_pct = max(-15.0, min(25.0, usdinr_pct))

    # 1. Indian Equities (Nifty 50 / Sensex)
    # Higher rates & oil hurt; higher GDP helps; inflation compresses multiples
    nifty_impact = (
        (-0.022 * rbi_bps)
        + (-0.014 * fed_bps)
        + (-0.140 * oil_pct)
        + (-1.400 * cpi_pct)
        + (2.100 * gdp_pct)
        + (-0.180 * usdinr_pct)
    )

    # 2. US Equities (S&P 500 / Nasdaq)
    us_impact = (
        (-0.032 * fed_bps)
        + (-0.070 * oil_pct)
        + (-1.800 * cpi_pct)
        + (2.300 * gdp_pct)
        + (0.050 * usdinr_pct)
    )

    # 3. Cryptocurrency (Bitcoin / Ethereum) - High-Beta Liquidity Asset
    crypto_impact = (
        (-0.075 * fed_bps)
        + (-0.030 * rbi_bps)
        + (-0.150 * oil_pct)
        + (-2.200 * cpi_pct)
        + (1.500 * gdp_pct)
    )

    # 4. Banking Sector (Bank Nifty)
    # Moderate rate hikes expand initial NIMs, but large hikes (>75 bps) or negative GDP hurt credit
    rbi_bank_factor = (0.016 * rbi_bps) if abs(rbi_bps) <= 75 else (0.016 * 75 - 0.020 * (abs(rbi_bps) - 75))
    bank_impact = (
        rbi_bank_factor
        + (3.100 * gdp_pct)
        + (-1.300 * cpi_pct)
        + (-0.080 * oil_pct)
        + (-0.120 * usdinr_pct)
    )

    # 5. IT Services Sector (Nifty IT)
    # Strong US tech spending helps; weaker INR significantly expands operating margins
    it_impact = (
        (-0.035 * fed_bps)
        + (0.850 * usdinr_pct)
        + (1.900 * gdp_pct)
        + (-0.600 * cpi_pct)
    )

    # 6. Energy Sector (Oil & Gas Producers & Refiners)
    # Directly benefits from higher crude prices; hurts if crude crashes
    energy_impact = (
        (0.420 * oil_pct)
        + (0.800 * gdp_pct)
        + (-0.008 * rbi_bps)
        + (0.150 * usdinr_pct)
    )

    # 7. Gold & Precious Metals (Safe Haven)
    # Real yields hurt gold; inflation & geopolitical oil shocks help gold; INR depreciation boosts local gold price
    gold_impact = (
        (-0.018 * fed_bps)
        + (1.750 * cpi_pct)
        + (0.160 * oil_pct)
        + (0.920 * usdinr_pct)
        + (-0.400 * gdp_pct)
    )

    # 8. Currency Markets (USD/INR)
    # Higher Fed rates & high crude depreciate rupee (+ USD/INR); higher RBI rates defend rupee
    usdinr_implied = (
        (0.010 * fed_bps)
        + (-0.008 * rbi_bps)
        + (0.110 * oil_pct)
        + (0.600 * cpi_pct)
        + (-0.400 * gdp_pct)
        + (1.0 * usdinr_pct)
    )

    # Structure asset results
    assets = [
        {
            "id": "NIFTY50",
            "name": "Indian Equities (Nifty 50)",
            "category": "Equities",
            "impact_pct": round(nifty_impact, 2),
            "stance": _classify_stance(nifty_impact),
            "sensitivity": "High",
            "primary_driver": "Cost of capital discount rate and domestic growth outlook",
            "key_risk": "FII outflows from rising US yields and elevated crude import bill",
            "icon": "🇮🇳"
        },
        {
            "id": "SP500",
            "name": "US Equities (S&P 500 & Nasdaq)",
            "category": "Equities",
            "impact_pct": round(us_impact, 2),
            "stance": _classify_stance(us_impact),
            "sensitivity": "High",
            "primary_driver": "Fed funds discount rate and corporate tech earnings multiples",
            "key_risk": "Terminal rate expectations and wage inflation persistence",
            "icon": "🇺🇸"
        },
        {
            "id": "BANK_NIFTY",
            "name": "Banking Sector (Bank Nifty)",
            "category": "Sectors",
            "impact_pct": round(bank_impact, 2),
            "stance": _classify_stance(bank_impact),
            "sensitivity": "High",
            "primary_driver": "Net interest margins (NIMs) vs. systemic credit growth rate",
            "key_risk": "Rising default provisions if elevated interest rates stifle borrower cash flows",
            "icon": "🏦"
        },
        {
            "id": "NIFTY_IT",
            "name": "IT Services Sector (Nifty IT)",
            "category": "Sectors",
            "impact_pct": round(it_impact, 2),
            "stance": _classify_stance(it_impact),
            "sensitivity": "High",
            "primary_driver": "USD/INR currency translation tailwind vs. US corporate IT budget cycles",
            "key_risk": "US recessionary slowdown curbing discretionary digital transformation budgets",
            "icon": "💻"
        },
        {
            "id": "ENERGY",
            "name": "Energy & Oil Sector",
            "category": "Sectors",
            "impact_pct": round(energy_impact, 2),
            "stance": _classify_stance(energy_impact),
            "sensitivity": "Medium",
            "primary_driver": "Upstream crude realization per barrel and refinery crack spreads",
            "key_risk": "Windfall profit taxes and government fuel price intervention",
            "icon": "⚡"
        },
        {
            "id": "GOLD",
            "name": "Gold & Precious Metals",
            "category": "Commodities",
            "impact_pct": round(gold_impact, 2),
            "stance": _classify_stance(gold_impact),
            "sensitivity": "Medium",
            "primary_driver": "Inflation hedging demand, real bond yields, and domestic currency depreciation",
            "key_risk": "Sharp spike in inflation-adjusted real interest rates",
            "icon": "🪙"
        },
        {
            "id": "CRYPTO",
            "name": "Cryptocurrency (BTC / ETH)",
            "category": "Digital Assets",
            "impact_pct": round(crypto_impact, 2),
            "stance": _classify_stance(crypto_impact),
            "sensitivity": "Very High",
            "primary_driver": "Global central bank M2 liquidity conditions and speculative risk appetite",
            "key_risk": "Aggressive monetary quantitative tightening draining speculative capital",
            "icon": "₿"
        },
        {
            "id": "USDINR",
            "name": "Currency Market (USD / INR)",
            "category": "Forex",
            "impact_pct": round(usdinr_implied, 2),
            "stance": "Dollar Bullish / Rupee Depreciation" if usdinr_implied > 0.5 else ("Rupee Strengthening" if usdinr_implied < -0.5 else "Stable Range"),
            "sensitivity": "Medium",
            "primary_driver": "US-India interest rate differential and crude oil import trade balance",
            "key_risk": "Aggressive RBI foreign exchange reserve interventions",
            "icon": "💵"
        }
    ]

    # Sort winners and losers
    sorted_assets = sorted([a for a in assets if a["id"] != "USDINR"], key=lambda x: x["impact_pct"], reverse=True)
    top_winners = [a for a in sorted_assets if a["impact_pct"] > 0]
    top_losers = [a for a in sorted_assets if a["impact_pct"] < 0]

    # Determine macro regime
    if rbi_bps > 25 and fed_bps > 25 and cpi_pct >= 0:
        regime = "Hawkish Monetary Tightening"
    elif rbi_bps < -25 and fed_bps < -25:
        regime = "Global Liquidity Easing"
    elif oil_pct > 15.0 and cpi_pct > 0.8:
        regime = "Cost-Push Inflationary Shock"
    elif gdp_pct < -0.8 and cpi_pct > 1.0:
        regime = "Stagflationary Pressure"
    elif gdp_pct > 0.8 and abs(cpi_pct) <= 0.5:
        regime = "Reflationary Growth Expansion"
    else:
        regime = "Macro Neutral / Rangebound"

    return {
        "regime": regime,
        "shocks": {
            "rbi_rate_bps": rbi_bps,
            "fed_rate_bps": fed_bps,
            "crude_oil_pct": oil_pct,
            "cpi_inflation_pct": cpi_pct,
            "gdp_growth_pct": gdp_pct,
            "usdinr_change_pct": usdinr_pct
        },
        "assets": assets,
        "top_winners": top_winners[:3],
        "top_losers": top_losers[::-1][:3],
        "disclaimer": "HYPOTHETICAL SIMULATION: Educational model based on historical macro coefficients. Not investment advice or guaranteed market forecast."
    }


def compare_macro_scenarios(scenario_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compare multiple macroeconomic scenarios and calculate asset divergence."""
    if not scenario_list:
        return {"scenarios": [], "divergence": {}}

    evaluated = []
    for sc in scenario_list:
        name = sc.get("name", "Custom Scenario")
        sc_id = sc.get("id", "custom")
        shocks = sc.get("shocks", {})
        result = calculate_macro_impact(shocks)
        evaluated.append({
            "id": sc_id,
            "name": name,
            "description": sc.get("description", ""),
            "regime": result["regime"],
            "shocks": result["shocks"],
            "assets": {a["id"]: a["impact_pct"] for a in result["assets"]},
            "raw_assets": result["assets"],
            "top_winner": result["top_winners"][0] if result["top_winners"] else None,
            "top_loser": result["top_losers"][0] if result["top_losers"] else None
        })

    # Calculate asset spread between best and worst scenarios
    asset_keys = ["NIFTY50", "SP500", "BANK_NIFTY", "NIFTY_IT", "ENERGY", "GOLD", "CRYPTO", "USDINR"]
    spreads = {}
    for k in asset_keys:
        vals = [sc["assets"].get(k, 0.0) for sc in evaluated]
        spreads[k] = {
            "max": max(vals),
            "min": min(vals),
            "spread": round(max(vals) - min(vals), 2)
        }

    return {
        "scenario_count": len(evaluated),
        "evaluated_scenarios": evaluated,
        "divergence": spreads
    }


def get_cross_asset_flow_map(scenario_type: str = "rate_hike") -> Dict[str, Any]:
    """Provide transmission flow diagrams for cross-asset impact mapping."""
    maps = {
        "rate_hike": {
            "title": "Central Bank Interest Rate Hike Transmission Channel",
            "trigger": "RBI / Federal Reserve raises benchmark interest rates (+50 bps)",
            "steps": [
                {
                    "step": 1,
                    "title": "Interbank Money Markets & Repo",
                    "description": "Commercial banks face higher overnight borrowing costs from the central bank. Treasury bill yields immediately adjust higher.",
                    "primary_asset": "Sovereign Bonds & Yield Curves",
                    "effect": "Yields rise, bond prices fall"
                },
                {
                    "step": 2,
                    "title": "Commercial Bank Lending & Deposits",
                    "description": "Banks increase MCLR and external benchmark lending rates. Fixed deposit rates rise to attract deposits.",
                    "primary_asset": "Banking Sector (Bank Nifty)",
                    "effect": "Short-term NIM expansion, but loan demand decelerates"
                },
                {
                    "step": 3,
                    "title": "Corporate Cost of Capital & Discount Rates",
                    "description": "Discount rate in DCF valuations increases. Growth equities with distant cash flows experience price-to-earnings (P/E) compression.",
                    "primary_asset": "Nifty 50 & Tech Stocks",
                    "effect": "Valuation multiples compress"
                },
                {
                    "step": 4,
                    "title": "Currency & Capital Flows",
                    "description": "Higher interest rate differential supports domestic currency attractiveness, counteracting speculative capital flight.",
                    "primary_asset": "Forex (USD/INR)",
                    "effect": "Currency stabilizes or appreciates"
                }
            ]
        },
        "oil_shock": {
            "title": "Crude Oil Geopolitical Supply Shock (+25%)",
            "trigger": "Brent Crude leaps from $75 to $95+ per barrel due to supply bottlenecks",
            "steps": [
                {
                    "step": 1,
                    "title": "Upstream Realizations vs Input Costs",
                    "description": "Upstream oil extractors realize windfall revenues per barrel, while paints, airlines, and logistics absorb higher input costs.",
                    "primary_asset": "Energy Sector (+), Auto & Aviation (-)",
                    "effect": "Energy profits surge; transport margins squeeze"
                },
                {
                    "step": 2,
                    "title": "National Import Bill & Current Account",
                    "description": "As India imports ~85% of crude, monthly trade deficit expands by billions of dollars, increasing foreign exchange demand.",
                    "primary_asset": "Currency (USD/INR)",
                    "effect": "Rupee depreciates against US Dollar"
                },
                {
                    "step": 3,
                    "title": "Inflation Passthrough to Consumer Basket",
                    "description": "Transport costs spill over into food distribution and manufacturing supply chains, driving headline CPI inflation upward.",
                    "primary_asset": "Retail Inflation (CPI)",
                    "effect": "Headline inflation rises by 0.5% - 1.2%"
                },
                {
                    "step": 4,
                    "title": "Central Bank Stance & Equity Valuations",
                    "description": "Central banks must delay rate cuts or consider emergency hikes to defend currency and anchor inflation expectations.",
                    "primary_asset": "Broad Market Equities (Nifty 50)",
                    "effect": "Equities face dual margin and discount rate headwinds"
                }
            ]
        }
    }
    return maps.get(scenario_type, maps["rate_hike"])

