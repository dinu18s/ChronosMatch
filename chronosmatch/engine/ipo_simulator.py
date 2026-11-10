"""IPO Launchpad & Listing Simulator Engine for ChronosMatch.

Provides simulated IPO catalog, application calculations, SEBI-aligned allotment
simulation (lottery for retail, pro-rata for NII), listing-day price discovery,
company research evaluation scorecards, and learning academy quizzes.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional
import datetime
import math
import random
import uuid


# =============================================================================
# CURATED SIMULATED IPO CATALOG
# =============================================================================

IPO_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "IPO-NEXUS-AI",
        "name": "NexusAI Technologies Limited",
        "symbol": "NEXUSAI",
        "logo_icon": "🤖",
        "industry": "Enterprise Artificial Intelligence & Cloud Infrastructure",
        "description": "Provider of specialized enterprise LLM fine-tuning platforms, neural search pipelines, and sovereign AI compute clusters for Fortune 500 enterprises and defense contractors.",
        "price_band_low": 680.0,
        "price_band_high": 715.0,
        "cut_off_price": 715.0,
        "lot_size": 20,
        "min_investment": 14300.0,  # 20 * 715
        "issue_size_cr": 2400.0,
        "fresh_issue_cr": 1800.0,
        "ofs_cr": 600.0,
        "retail_quota_pct": 35.0,
        "nii_quota_pct": 15.0,
        "qib_quota_pct": 50.0,
        "open_date": "2026-11-10",
        "close_date": "2026-11-12",
        "allotment_date": "2026-11-15",
        "listing_date": "2026-11-18",
        "status": "OPEN",
        "gmp_estimate_inr": 285.0,
        "gmp_percent": 39.86,
        "subscriptions": {
            "retail_sub_x": 18.4,
            "nii_sub_x": 34.2,
            "qib_sub_x": 62.8,
            "total_sub_x": 42.5,
        },
        "research": {
            "business_model": "SaaS recurring revenue (78%) + dedicated AI GPU compute node reservations (22%). 112% Net Revenue Retention (NRR).",
            "industry_outlook": "Global Enterprise AI expenditure projected to grow at 34% CAGR from 2024 to 2030, driven by generative AI enterprise adoption.",
            "financials": {
                "revenue_fy24_cr": 840.0,
                "revenue_fy25_cr": 1420.0,
                "cagr_3y_pct": 48.2,
                "ebitda_margin_pct": 28.5,
                "pat_cr": 265.0,
                "debt_to_equity": 0.12,
                "pe_ratio": 42.5,
                "pb_ratio": 6.8,
                "roe_pct": 21.4,
            },
            "peers": [
                {"name": "Tata Elxsi", "pe": 54.2, "market_cap_cr": 48000.0},
                {"name": "Persistent Systems", "pe": 46.8, "market_cap_cr": 62000.0},
                {"name": "L&T Technology Services", "pe": 39.5, "market_cap_cr": 51000.0},
            ],
            "strengths": [
                "Proprietary low-latency inference orchestration engine with zero vendor lock-in.",
                "Multi-year anchor contracts with leading tier-1 banking institutions.",
                "High operating leverage with negative working capital cycle.",
            ],
            "risks": [
                "Heavy dependence on global semiconductor fabrication schedules for GPU accelerators.",
                "Intense competitive pressures from hyperscalers (AWS, Azure, Google Cloud).",
                "Key client concentration: Top 5 clients account for 41% of total revenue.",
            ],
            "scorecard": {
                "financial_health": 23,  # out of 25
                "valuation_attractiveness": 19,  # out of 25
                "business_moat": 24,  # out of 25
                "governance_promoters": 22,  # out of 25
                "total_score": 88,
                "recommendation": "SUBSCRIBE_LISTING_GAINS",
                "summary": "High-growth enterprise AI pure-play with robust margins and strong subscription demand. Attractive candidate for listing gains and medium-term portfolio allocation.",
            },
        },
        "listing_scenarios": {
            "strong": {"open_price": 1040.0, "gain_pct": 45.45, "day_high": 1110.0, "day_low": 980.0, "close": 1075.0, "volume": 14500000},
            "moderate": {"open_price": 820.0, "gain_pct": 14.68, "day_high": 860.0, "day_low": 790.0, "close": 835.0, "volume": 9800000},
            "weak": {"open_price": 670.0, "gain_pct": -6.29, "day_high": 700.0, "day_low": 640.0, "close": 655.0, "volume": 6200000},
            "volatile": {"open_price": 910.0, "gain_pct": 27.27, "day_high": 1150.0, "day_low": 780.0, "close": 890.0, "volume": 18200000},
        },
    },
    {
        "id": "IPO-SOLARIS-GREEN",
        "name": "Solaris Green Energy Limited",
        "symbol": "SOLARIS",
        "logo_icon": "☀️",
        "industry": "Renewable Energy & Battery Energy Storage (BESS)",
        "description": "Integrated utility-scale solar project developer, high-efficiency bifacial PV module manufacturer, and grid-scale lithium-ion battery storage operator across Western and Southern India.",
        "price_band_low": 320.0,
        "price_band_high": 340.0,
        "cut_off_price": 340.0,
        "lot_size": 44,
        "min_investment": 14960.0,  # 44 * 340
        "issue_size_cr": 1850.0,
        "fresh_issue_cr": 1450.0,
        "ofs_cr": 400.0,
        "retail_quota_pct": 35.0,
        "nii_quota_pct": 15.0,
        "qib_quota_pct": 50.0,
        "open_date": "2026-11-09",
        "close_date": "2026-11-11",
        "allotment_date": "2026-11-14",
        "listing_date": "2026-11-17",
        "status": "OPEN",
        "gmp_estimate_inr": 82.0,
        "gmp_percent": 24.12,
        "subscriptions": {
            "retail_sub_x": 12.8,
            "nii_sub_x": 22.4,
            "qib_sub_x": 44.1,
            "total_sub_x": 28.5,
        },
        "research": {
            "business_model": "Long-term Power Purchase Agreements (PPAs) with SECI and state discoms (25-year lock-in) + commercial EPC turnkey solutions.",
            "industry_outlook": "India target of 500 GW non-fossil capacity by 2030 guarantees sustained capex pipelines and preferential transmission corridor rights.",
            "financials": {
                "revenue_fy24_cr": 1120.0,
                "revenue_fy25_cr": 1680.0,
                "cagr_3y_pct": 36.4,
                "ebitda_margin_pct": 42.1,
                "pat_cr": 195.0,
                "debt_to_equity": 1.45,
                "pe_ratio": 29.8,
                "pb_ratio": 3.9,
                "roe_pct": 15.8,
            },
            "peers": [
                {"name": "Adani Green Energy", "pe": 115.0, "market_cap_cr": 285000.0},
                {"name": "Tata Power Renewable", "pe": 38.2, "market_cap_cr": 125000.0},
                {"name": "Suzlon Energy", "pe": 48.6, "market_cap_cr": 72000.0},
            ],
            "strengths": [
                "94% of operational capacity backed by sovereign-guaranteed PPAs with SECI.",
                "In-house EPC reduces capital deployment costs by 18% versus peers.",
                "Diversified solar-wind hybrid portfolio balancing diurnal power delivery.",
            ],
            "risks": [
                "Elevated debt-to-equity ratio (1.45x) due to capital-intensive development.",
                "Discom payment delays or grid curtailment risks during surplus generation hours.",
                "Fluctuations in global polysilicon and battery cell import tariffs.",
            ],
            "scorecard": {
                "financial_health": 18,
                "valuation_attractiveness": 22,
                "business_moat": 21,
                "governance_promoters": 20,
                "total_score": 81,
                "recommendation": "SUBSCRIBE_LONG_TERM",
                "summary": "Attractive valuation relative to bloated clean-energy peers with predictable 25-year annuity cash flows. Suitable for long-term thematic exposure.",
            },
        },
        "listing_scenarios": {
            "strong": {"open_price": 440.0, "gain_pct": 29.41, "day_high": 475.0, "day_low": 420.0, "close": 455.0, "volume": 11200000},
            "moderate": {"open_price": 385.0, "gain_pct": 13.24, "day_high": 405.0, "day_low": 370.0, "close": 395.0, "volume": 7600000},
            "weak": {"open_price": 325.0, "gain_pct": -4.41, "day_high": 345.0, "day_low": 310.0, "close": 320.0, "volume": 4900000},
            "volatile": {"open_price": 410.0, "gain_pct": 20.59, "day_high": 480.0, "day_low": 350.0, "close": 380.0, "volume": 14000000},
        },
    },
    {
        "id": "IPO-FINPULSE-PAY",
        "name": "FinPulse Payments Limited",
        "symbol": "FINPULSE",
        "logo_icon": "💳",
        "industry": "FinTech & Digital Payments Infrastructure",
        "description": "Full-stack payment aggregator, offline merchant QR soundbox network, and embedded credit distribution infrastructure powering over 4.2 million small merchants across Tier 2 and Tier 3 cities.",
        "price_band_low": 510.0,
        "price_band_high": 540.0,
        "cut_off_price": 540.0,
        "lot_size": 27,
        "min_investment": 14580.0,  # 27 * 540
        "issue_size_cr": 3100.0,
        "fresh_issue_cr": 1200.0,
        "ofs_cr": 1900.0,
        "retail_quota_pct": 35.0,
        "nii_quota_pct": 15.0,
        "qib_quota_pct": 50.0,
        "open_date": "2026-11-18",
        "close_date": "2026-11-20",
        "allotment_date": "2026-11-23",
        "listing_date": "2026-11-26",
        "status": "UPCOMING",
        "gmp_estimate_inr": 45.0,
        "gmp_percent": 8.33,
        "subscriptions": {
            "retail_sub_x": 0.0,
            "nii_sub_x": 0.0,
            "qib_sub_x": 0.0,
            "total_sub_x": 0.0,
        },
        "research": {
            "business_model": "Payment processing MDR (0.15-0.45%), monthly hardware soundbox subscription rentals (₹125/month), and loan origination fees from partnering NBFCs (2.5%).",
            "industry_outlook": "Merchant payment digitization accelerating toward contactless soundbox penetration with 28% CAGR in merchant credit disbursement.",
            "financials": {
                "revenue_fy24_cr": 1450.0,
                "revenue_fy25_cr": 2180.0,
                "cagr_3y_pct": 41.5,
                "ebitda_margin_pct": 11.2,
                "pat_cr": 88.0,
                "debt_to_equity": 0.22,
                "pe_ratio": 72.4,
                "pb_ratio": 8.5,
                "roe_pct": 9.2,
            },
            "peers": [
                {"name": "One97 Communications (Paytm)", "pe": -1.0, "market_cap_cr": 45000.0},
                {"name": "PB Fintech (PolicyBazaar)", "pe": 88.0, "market_cap_cr": 68000.0},
                {"name": "Fino Payments Bank", "pe": 28.5, "market_cap_cr": 2800.0},
            ],
            "strengths": [
                "Market leadership in rural and semi-urban merchant soundbox installations (4.2M active units).",
                "Proven turnaround from cash burn to net GAAP profitability in FY25.",
                "Proprietary transaction underwriting model enabling high conversion for NBFC partners.",
            ],
            "risks": [
                "Heavy OFS component (61% of total issue size) allowing early PE investors to exit.",
                "Regulatory uncertainty regarding UPI merchant interchange caps and RBI payment aggregator guidelines.",
                "Intense competition from PhonePe, Google Pay, and deep-pocketed telecom-backed payment banks.",
            ],
            "scorecard": {
                "financial_health": 17,
                "valuation_attractiveness": 14,
                "business_moat": 19,
                "governance_promoters": 16,
                "total_score": 66,
                "recommendation": "NEUTRAL",
                "summary": "Fast-growing franchise, but aggressive pricing (72x P/E) and outsized Offer For Sale (OFS) suggest modest listing gains. Apply with caution.",
            },
        },
        "listing_scenarios": {
            "strong": {"open_price": 630.0, "gain_pct": 16.67, "day_high": 660.0, "day_low": 590.0, "close": 615.0, "volume": 12500000},
            "moderate": {"open_price": 565.0, "gain_pct": 4.63, "day_high": 580.0, "day_low": 540.0, "close": 555.0, "volume": 8400000},
            "weak": {"open_price": 490.0, "gain_pct": -9.26, "day_high": 520.0, "day_low": 470.0, "close": 485.0, "volume": 7100000},
            "volatile": {"open_price": 575.0, "gain_pct": 6.48, "day_high": 640.0, "day_low": 505.0, "close": 530.0, "volume": 15200000},
        },
    },
    {
        "id": "IPO-AERO-DEFENSE",
        "name": "Garuda Aerospace & Defense Limited",
        "symbol": "GARUDAERO",
        "logo_icon": "🛩️",
        "industry": "Aerospace, UAV Drone Systems & Defense Electronics",
        "description": "Indigenous designer and manufacturer of autonomous surveillance drones, anti-drone electronic jamming systems, and tactical loitering munitions for armed forces and border security.",
        "price_band_low": 820.0,
        "price_band_high": 860.0,
        "cut_off_price": 860.0,
        "lot_size": 16,
        "min_investment": 13760.0,  # 16 * 860
        "issue_size_cr": 1500.0,
        "fresh_issue_cr": 1200.0,
        "ofs_cr": 300.0,
        "retail_quota_pct": 35.0,
        "nii_quota_pct": 15.0,
        "qib_quota_pct": 50.0,
        "open_date": "2026-11-04",
        "close_date": "2026-11-06",
        "allotment_date": "2026-11-10",
        "listing_date": "2026-11-13",
        "status": "CLOSED",
        "gmp_estimate_inr": 380.0,
        "gmp_percent": 44.19,
        "subscriptions": {
            "retail_sub_x": 42.6,
            "nii_sub_x": 78.4,
            "qib_sub_x": 115.2,
            "total_sub_x": 84.3,
        },
        "research": {
            "business_model": "Long-term defense procurement defense contracts (Make in India) + annual maintenance and electronic warfare upgrades.",
            "industry_outlook": "Indian defense modernization budget prioritizing indigenous procurement with positive import embargo lists on UAV systems.",
            "financials": {
                "revenue_fy24_cr": 680.0,
                "revenue_fy25_cr": 1190.0,
                "cagr_3y_pct": 52.8,
                "ebitda_margin_pct": 31.4,
                "pat_cr": 210.0,
                "debt_to_equity": 0.08,
                "pe_ratio": 38.4,
                "pb_ratio": 7.2,
                "roe_pct": 24.6,
            },
            "peers": [
                {"name": "Hindustan Aeronautics (HAL)", "pe": 39.5, "market_cap_cr": 310000.0},
                {"name": "Bharat Electronics (BEL)", "pe": 44.2, "market_cap_cr": 215000.0},
                {"name": "Zen Technologies", "pe": 62.0, "market_cap_cr": 14000.0},
            ],
            "strengths": [
                "Unassailable order book of ₹4,850 Cr (4.1x FY25 revenue) offering multi-year revenue visibility.",
                "In-house defense IP with 100% indigenous components escaping export control restrictions.",
                "Zero net debt balance sheet with high return on equity (24.6%).",
            ],
            "risks": [
                "Single-customer concentration risk (Ministry of Defense accounts for 82% of order book).",
                "Lumpy milestone-based cash collection cycles characteristic of defense contracts.",
                "Long tender gestation periods and risk of RFP cancellation.",
            ],
            "scorecard": {
                "financial_health": 24,
                "valuation_attractiveness": 21,
                "business_moat": 25,
                "governance_promoters": 23,
                "total_score": 93,
                "recommendation": "STRONG_SUBSCRIBE",
                "summary": "Blockbuster defense candidate with massive order book visibility, pristine balance sheet, and extraordinary 84x institutional oversubscription. Strong candidate for bumper listing gains.",
            },
        },
        "listing_scenarios": {
            "strong": {"open_price": 1350.0, "gain_pct": 56.98, "day_high": 1440.0, "day_low": 1280.0, "close": 1390.0, "volume": 18500000},
            "moderate": {"open_price": 1050.0, "gain_pct": 22.09, "day_high": 1120.0, "day_low": 1010.0, "close": 1080.0, "volume": 11400000},
            "weak": {"open_price": 840.0, "gain_pct": -2.33, "day_high": 870.0, "day_low": 800.0, "close": 820.0, "volume": 6900000},
            "volatile": {"open_price": 1200.0, "gain_pct": 39.53, "day_high": 1500.0, "day_low": 980.0, "close": 1150.0, "volume": 22000000},
        },
    },
    {
        "id": "IPO-URBAN-CART",
        "name": "UrbanCart QuickCommerce Limited",
        "symbol": "URBANCART",
        "logo_icon": "🛍️",
        "industry": "Hyperlocal 10-Minute Quick Commerce & Dark Store Logistics",
        "description": "On-demand grocery and household essentials delivery network operating 850 automated micro-fulfillment dark stores across 28 metropolitan cities in India.",
        "price_band_low": 210.0,
        "price_band_high": 225.0,
        "cut_off_price": 225.0,
        "lot_size": 65,
        "min_investment": 14625.0,  # 65 * 225
        "issue_size_cr": 4200.0,
        "fresh_issue_cr": 3200.0,
        "ofs_cr": 1000.0,
        "retail_quota_pct": 10.0,
        "nii_quota_pct": 15.0,
        "qib_quota_pct": 75.0,
        "open_date": "2026-10-15",
        "close_date": "2026-10-17",
        "allotment_date": "2026-10-20",
        "listing_date": "2026-10-24",
        "status": "LISTED",
        "gmp_estimate_inr": 32.0,
        "gmp_percent": 14.22,
        "subscriptions": {
            "retail_sub_x": 8.2,
            "nii_sub_x": 16.5,
            "qib_sub_x": 38.4,
            "total_sub_x": 22.1,
        },
        "research": {
            "business_model": "Product markup margins (14%) + delivery and surge handling fees + advertising platform revenues from FMCG brands (4.2% of GMV).",
            "industry_outlook": "Quick commerce expanding rapidly into electronics, beauty, and festive gifting, eroding market share of traditional supermarkets.",
            "financials": {
                "revenue_fy24_cr": 3200.0,
                "revenue_fy25_cr": 5800.0,
                "cagr_3y_pct": 81.2,
                "ebitda_margin_pct": 2.1,
                "pat_cr": -45.0,
                "debt_to_equity": 0.05,
                "pe_ratio": -1.0,
                "pb_ratio": 9.4,
                "roe_pct": -3.2,
            },
            "peers": [
                {"name": "Zomato (Blinkit)", "pe": 118.0, "market_cap_cr": 220000.0},
                {"name": "Swiggy (Instamart)", "pe": -1.0, "market_cap_cr": 95000.0},
            ],
            "strengths": [
                "Exceptional top-line momentum (81% CAGR) with industry-leading dark store throughput.",
                "Advertising and FMCG monetization engine generating high-margin ancillary revenue.",
                "Dense metropolitan store footprint providing substantial customer switching costs.",
            ],
            "risks": [
                "Thin operating margins susceptible to delivery gig-worker minimum wage and gig regulations.",
                "Heavy cash burn in customer acquisition discounts for non-metro tier-2 expansion.",
                "High warehouse lease commitments and perishable product shrinkage losses.",
            ],
            "scorecard": {
                "financial_health": 15,
                "valuation_attractiveness": 16,
                "business_moat": 20,
                "governance_promoters": 18,
                "total_score": 69,
                "recommendation": "SUBSCRIBE_LISTING_GAINS",
                "summary": "Hyper-growth consumer favorite with strong institutional demand. Suitable for momentum traders seeking listing pop, though structural profitability remains nascent.",
            },
        },
        "listing_scenarios": {
            "strong": {"open_price": 272.0, "gain_pct": 20.89, "day_high": 290.0, "day_low": 260.0, "close": 281.0, "volume": 32000000},
            "moderate": {"open_price": 245.0, "gain_pct": 8.89, "day_high": 255.0, "day_low": 235.0, "close": 242.0, "volume": 21000000},
            "weak": {"open_price": 212.0, "gain_pct": -5.78, "day_high": 225.0, "day_low": 198.0, "close": 205.0, "volume": 16500000},
            "volatile": {"open_price": 260.0, "gain_pct": 15.56, "day_high": 310.0, "day_low": 220.0, "close": 235.0, "volume": 44000000},
        },
    },
    {
        "id": "IPO-MEDICURE-BIO",
        "name": "Medicure Therapeutics Limited",
        "symbol": "MEDICURE",
        "logo_icon": "🧬",
        "industry": "Biopharmaceuticals, Oncology Biosimilars & CDMO",
        "description": "Specialty biopharmaceutical research company developing biosimilar monoclonal antibodies for oncology, autoimmune disorders, and contract biologics manufacturing.",
        "price_band_low": 410.0,
        "price_band_high": 435.0,
        "cut_off_price": 435.0,
        "lot_size": 34,
        "min_investment": 14790.0,  # 34 * 435
        "issue_size_cr": 1100.0,
        "fresh_issue_cr": 900.0,
        "ofs_cr": 200.0,
        "retail_quota_pct": 35.0,
        "nii_quota_pct": 15.0,
        "qib_quota_pct": 50.0,
        "open_date": "2026-10-08",
        "close_date": "2026-10-10",
        "allotment_date": "2026-10-13",
        "listing_date": "2026-10-17",
        "status": "LISTED",
        "gmp_estimate_inr": -15.0,
        "gmp_percent": -3.45,
        "subscriptions": {
            "retail_sub_x": 0.85,  # Undersubscribed retail
            "nii_sub_x": 1.15,
            "qib_sub_x": 2.40,
            "total_sub_x": 1.67,
        },
        "research": {
            "business_model": "Global drug licensing royalties + commercial batch manufacturing services for European and US generic pharmaceutical leaders.",
            "industry_outlook": "Patent cliff for major biologics expected to unlock $120B in biosimilar addressable market through 2030.",
            "financials": {
                "revenue_fy24_cr": 480.0,
                "revenue_fy25_cr": 590.0,
                "cagr_3y_pct": 18.2,
                "ebitda_margin_pct": 19.5,
                "pat_cr": 54.0,
                "debt_to_equity": 0.45,
                "pe_ratio": 48.0,
                "pb_ratio": 4.1,
                "roe_pct": 10.4,
            },
            "peers": [
                {"name": "Biocon", "pe": 34.0, "market_cap_cr": 38000.0},
                {"name": "Syngene International", "pe": 41.5, "market_cap_cr": 32000.0},
            ],
            "strengths": [
                "US FDA and EMA approved cGMP biologics manufacturing facility in Hyderabad.",
                "Robust pipeline of 6 biosimilar candidates in late Phase III clinical trials.",
            ],
            "risks": [
                "Regulatory scrutiny: Any FDA Form 483 warning letters can halt exports.",
                "Rich valuation pricing relative to established peers without guaranteed clinical trial approval.",
                "Subdued retail subscription interest with negative grey market premium (GMP).",
            ],
            "scorecard": {
                "financial_health": 16,
                "valuation_attractiveness": 12,
                "business_moat": 18,
                "governance_promoters": 17,
                "total_score": 63,
                "recommendation": "AVOID",
                "summary": "Full pricing with negative GMP and tepid retail subscription. High likelihood of listing at a discount; wait for post-listing price stabilization.",
            },
        },
        "listing_scenarios": {
            "strong": {"open_price": 450.0, "gain_pct": 3.45, "day_high": 465.0, "day_low": 430.0, "close": 442.0, "volume": 5200000},
            "moderate": {"open_price": 420.0, "gain_pct": -3.45, "day_high": 435.0, "day_low": 410.0, "close": 418.0, "volume": 3800000},
            "weak": {"open_price": 385.0, "gain_pct": -11.49, "day_high": 405.0, "day_low": 370.0, "close": 378.0, "volume": 4100000},
            "volatile": {"open_price": 415.0, "gain_pct": -4.60, "day_high": 460.0, "day_low": 365.0, "close": 390.0, "volume": 6800000},
        },
    },
]


# =============================================================================
# IPO LEARNING ACADEMY LESSONS & QUIZZES
# =============================================================================

IPO_LESSONS: List[Dict[str, Any]] = [
    {
        "id": "IPO-LES-01",
        "title": "IPO Fundamentals: From Private Venture to Public Exchange",
        "category": "Basics",
        "read_time": "3 min",
        "summary": "What is an Initial Public Offering, why companies go public, and the difference between primary and secondary markets.",
        "content": (
            "An Initial Public Offering (IPO) is the process by which a privately held company raises equity capital from "
            "institutional and retail investors by issuing shares on a recognized stock exchange (e.g. NSE, BSE).\n\n"
            "Key Reasons Companies Conduct an IPO:\n"
            "1. Capital Raising: Fund major capital expenditures (capex), repay expensive debt, or fund R&D.\n"
            "2. Liquidity & Exit: Provide an exit mechanism for early venture capital (VC) and private equity (PE) backers.\n"
            "3. Brand Visibility & Prestige: Elevate public transparency, customer trust, and corporate governance.\n"
            "4. Acquisition Currency: Utilize publicly quoted stock as consideration for future mergers and acquisitions."
        ),
    },
    {
        "id": "IPO-LES-02",
        "title": "Fresh Issue vs. Offer for Sale (OFS): Where Does Your Money Go?",
        "category": "Due Diligence",
        "read_time": "4 min",
        "summary": "Understand the critical distinction between capital flowing into company coffers versus cashing out promoters.",
        "content": (
            "When analyzing an IPO Red Herring Prospectus (DRHP), always check the composition of the issue:\n\n"
            "• Fresh Issue: New shares are created and sold to the public. 100% of these proceeds (net of issue expenses) "
            "go directly into the company balance sheet to fund new factories, working capital, or debt repayment.\n\n"
            "• Offer for Sale (OFS): Existing promoters, founders, or venture capital funds sell their existing shares. "
            "None of this money enters the company's treasury; it goes directly to the selling shareholders' personal bank accounts.\n\n"
            "Investor Rule of Thumb: A high Fresh Issue proportion is generally bullish for future earnings expansion, whereas a 100% OFS "
            "indicates insiders are cashing out at peak valuations."
        ),
    },
    {
        "id": "IPO-LES-03",
        "title": "The Book-Building Process & The Cut-Off Price",
        "category": "Bidding Mechanics",
        "read_time": "4 min",
        "summary": "How merchant bankers discover the market-clearing price and why retail bidders should always select the Cut-Off Price.",
        "content": (
            "Modern Indian IPOs use the 'Book-Building' mechanism rather than fixed-price offerings.\n\n"
            "• Price Band: The issuer specifies a floor and ceiling price (e.g. ₹680 to ₹715). The maximum spread between "
            "floor and cap is legally capped at 20%.\n\n"
            "• The Cut-Off Price: This is the final issue price decided by the lead managers after aggregating all institutional "
            "and retail bids. In almost all oversubscribed IPOs, the cut-off price is set at the exact upper ceiling.\n\n"
            "Golden Retail Rule: Retail investors should always select the 'Cut-Off Price' checkbox. If you bid at the lower price "
            "and the cut-off settles at the upper band, your application is automatically disqualified!"
        ),
    },
    {
        "id": "IPO-LES-04",
        "title": "Allotment Mathematics: SEBI Lottery vs. Pro-Rata Rules",
        "category": "Allotment Rules",
        "read_time": "5 min",
        "summary": "How computerized algorithms distribute shares across Retail, HNI/NII, and QIB investor buckets.",
        "content": (
            "SEBI guidelines establish strict computerized rules for how oversubscribed IPO shares are distributed:\n\n"
            "1. Retail Category (RII - Up to ₹2,00,000):\n"
            "Under SEBI rules, the retail allotment aims to treat all applicants equally regardless of whether you applied for 1 lot or 13 lots. "
            "If retail is oversubscribed (e.g., 18x), a computerized computerized lottery is conducted. "
            "Lucky winners receive exactly 1 minimum lot (never more), while the remaining applicants receive zero lots and a 100% refund.\n\n"
            "2. Non-Institutional Category (NII / HNI - Above ₹2,00,000):\n"
            "Divided into Small HNI (₹2L-₹10L) and Big HNI (>₹10L). Allotment is proportionate or via lottery draw for minimum NII lots.\n\n"
            "Pro-Tip: Applying for 10 lots in the retail bucket does NOT increase your lottery odds. To maximize odds, apply for 1 lot each "
            "across different family members' unique PAN and Demat accounts."
        ),
    },
    {
        "id": "IPO-LES-05",
        "title": "Listing Day Dynamics: Pre-Open Discovery & The 10:00 AM Bell",
        "category": "Trading & Listing",
        "read_time": "4 min",
        "summary": "How equilibrium opening prices are discovered during the pre-market auction call without price band limits.",
        "content": (
            "Listing Day is the most volatile session in an equity lifecycle:\n\n"
            "• Pre-Open Call Auction (9:00 AM - 9:45 AM): Bids and offers are collected to discover the equilibrium opening price. "
            "Unlike secondary market trading where circuit filters (e.g. 5% or 10%) apply, IPO listing sessions have unrestricted "
            "discovery bands (or up to 90% circuit filters based on market cap).\n\n"
            "• Grey Market Premium (GMP): Unofficial, unregulated forward pricing conducted by brokers before official listing. "
            "While GMP offers directional sentiment, it is speculative and carries no legal backing.\n\n"
            "Exit Strategy: Allotted investors must decide whether to 'flip' for listing gains at the opening bell or hold for multi-year compounding."
        ),
    },
]

IPO_QUIZZES: List[Dict[str, Any]] = [
    {
        "id": "IPO-QZ-01",
        "title": "Question 1: Where Do IPO Proceeds Go?",
        "points": 100,
        "question": "If an IPO has a total issue size of ₹1,000 Cr consisting of ₹800 Cr Fresh Issue and ₹200 Cr Offer for Sale (OFS), how much money enters the company's bank account for business expansion?",
        "options": [
            {"id": "A", "text": "₹1,000 Cr (The entire issue proceeds)", "is_correct": False},
            {"id": "B", "text": "₹800 Cr (Only the Fresh Issue proceeds)", "is_correct": True},
            {"id": "C", "text": "₹200 Cr (Only the OFS proceeds)", "is_correct": False},
            {"id": "D", "text": "Zero, all money goes to investment bankers", "is_correct": False},
        ],
        "explanation": "Correct! Fresh issue proceeds enter the company balance sheet to fund capex and working capital. The ₹200 Cr OFS proceeds go directly to selling existing shareholders.",
    },
    {
        "id": "IPO-QZ-02",
        "title": "Question 2: Maximizing Retail Allotment Odds",
        "points": 120,
        "question": "An IPO retail category is oversubscribed 25 times. A retail investor wants to maximize their probability of getting at least 1 lot. What is the most effective strategy under SEBI rules?",
        "options": [
            {"id": "A", "text": "Apply for the maximum 13 lots from a single Demat account", "is_correct": False},
            {"id": "B", "text": "Apply for 1 lot each across 3 separate Demat accounts with distinct family PAN cards", "is_correct": True},
            {"id": "C", "text": "Bid at the lowest price in the price band to secure queue priority", "is_correct": False},
            {"id": "D", "text": "Wait until 4:59 PM on the final day to submit the bid", "is_correct": False},
        ],
        "explanation": "Correct! Under SEBI's computerized lottery rules, applying for 13 lots on one PAN provides only 1 lottery ticket. Applying with 3 separate PAN accounts provides 3 independent lottery chances.",
    },
    {
        "id": "IPO-QZ-03",
        "title": "Question 3: The Critical Cut-Off Price",
        "points": 100,
        "question": "An IPO has a price band of ₹480 to ₹500. A retail applicant manually bids at ₹485. The issue is heavily oversubscribed and the cut-off price is finalized at ₹500. What happens to the applicant's bid?",
        "options": [
            {"id": "A", "text": "The applicant automatically gets allotted at ₹485", "is_correct": False},
            {"id": "B", "text": "The applicant gets rejected and receives a 100% refund because the bid was below cut-off", "is_correct": True},
            {"id": "C", "text": "The exchange automatically upgrades the bid to ₹500", "is_correct": False},
            {"id": "D", "text": "The applicant receives half the requested shares", "is_correct": False},
        ],
        "explanation": "Correct! If an applicant bids below the discovered cut-off price, the bid is invalid and completely disqualified. Retail investors should always select 'Cut-Off Price'.",
    },
    {
        "id": "IPO-QZ-04",
        "title": "Question 4: Calculating Refund Amount",
        "points": 130,
        "question": "You apply for 4 lots of an IPO (25 shares/lot at ₹400/share = ₹40,000 blocked). Under pro-rata NII allotment, you are allotted exactly 1 lot (25 shares). How much virtual money is refunded to your account?",
        "options": [
            {"id": "A", "text": "₹40,000 (Full refund)", "is_correct": False},
            {"id": "B", "text": "₹10,000 (1 lot refund)", "is_correct": False},
            {"id": "C", "text": "₹30,000 (Refund for the 3 unallotted lots)", "is_correct": True},
            {"id": "D", "text": "Zero, unallotted money is retained for future IPOs", "is_correct": False},
        ],
        "explanation": "Correct! Total blocked = ₹40,000. Utilized for 1 allotted lot = 25 * ₹400 = ₹10,000. Refund credited back = ₹40,000 - ₹10,000 = ₹30,000.",
    },
    {
        "id": "IPO-QZ-05",
        "title": "Question 5: Realizing Listing Gains",
        "points": 150,
        "question": "You were allotted 20 shares of an IPO at the issue price of ₹700. On listing day, the stock opens at ₹1,050 and you immediately sell all shares. What is your listing gain in rupees and percentage?",
        "options": [
            {"id": "A", "text": "₹3,500 profit (+25.0%)", "is_correct": False},
            {"id": "B", "text": "₹7,000 profit (+50.0%)", "is_correct": True},
            {"id": "C", "text": "₹14,000 profit (+100.0%)", "is_correct": False},
            {"id": "D", "text": "₹5,000 profit (+35.7%)", "is_correct": False},
        ],
        "explanation": "Correct! Invested = 20 * ₹700 = ₹14,000. Proceeds = 20 * ₹1,050 = ₹21,000. Profit = ₹7,000, representing a (+50.0%) listing gain.",
    },
]


# =============================================================================
# CALCULATION & ALLOTMENT SIMULATION ENGINES
# =============================================================================

def get_ipo_by_id(ipo_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve IPO details by ID."""
    for ipo in IPO_CATALOG:
        if ipo["id"] == ipo_id:
            return ipo
    return None


def calculate_ipo_application(
    ipo: Dict[str, Any],
    lots: int,
    category: str = "RETAIL",
    bid_price: Optional[float] = None,
) -> Dict[str, Any]:
    """Calculate application parameters, shares, and validate category limits."""
    lots = max(1, int(lots))
    lot_size = int(ipo["lot_size"])
    total_shares = lots * lot_size
    price = float(bid_price) if bid_price and bid_price > 0 else float(ipo["cut_off_price"])

    # Ensure price is within band
    price = max(float(ipo["price_band_low"]), min(float(ipo["price_band_high"]), price))
    total_amount = round(total_shares * price, 2)

    category = category.upper()
    is_retail = category == "RETAIL"
    max_retail_amount = 200000.0

    validation_errors = []
    if is_retail and total_amount > max_retail_amount:
        validation_errors.append(
            f"Retail category (RII) maximum application limit is ₹2,00,000.00. Current application is ₹{total_amount:,.2f}. Please reduce lots or switch to Non-Institutional Investor (NII) category."
        )

    return {
        "ipo_id": ipo["id"],
        "symbol": ipo["symbol"],
        "lots": lots,
        "lot_size": lot_size,
        "shares": total_shares,
        "bid_price": price,
        "total_amount": total_amount,
        "category": category,
        "is_valid": len(validation_errors) == 0,
        "errors": validation_errors,
    }


def simulate_allotment(
    application: Dict[str, Any],
    ipo: Dict[str, Any],
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """Simulate realistic SEBI allotment algorithm for Retail vs NII.

    - Retail: If oversubscribed, lottery draw where winning applicant gets exactly 1 lot.
              If undersubscribed (<= 1.0x), full allotment.
    - NII: Pro-rata allocation based on NII oversubscription ratio.
    """
    if seed is not None:
        rnd = random.Random(seed)
    else:
        rnd = random.Random()

    category = str(application.get("category", "RETAIL")).upper()
    lots_applied = int(application.get("lots", 1))
    lot_size = int(ipo.get("lot_size", 20))
    shares_applied = lots_applied * lot_size
    bid_price = float(application.get("bid_price", ipo.get("cut_off_price", 100.0)))
    amount_blocked = float(application.get("total_amount", shares_applied * bid_price))

    subs = ipo.get("subscriptions", {})
    retail_sub = float(subs.get("retail_sub_x", 1.0))
    nii_sub = float(subs.get("nii_sub_x", 1.0))

    lots_allotted = 0
    status = "NOT_ALLOTTED"
    rationale = ""

    if category == "RETAIL":
        if retail_sub <= 1.0:
            # Undersubscribed or exact: 100% full allotment
            lots_allotted = lots_applied
            status = "ALLOTTED"
            rationale = f"Retail category undersubscribed ({retail_sub:.1f}x). Full allotment of {lots_applied} lots granted."
        else:
            # Oversubscribed: SEBI lottery rule -> Probability = 1 / retail_sub
            lottery_prob = min(1.0, 1.0 / retail_sub)
            draw = rnd.random()
            if draw <= lottery_prob:
                # Won lottery -> exactly 1 lot allotted under SEBI retail rule
                lots_allotted = 1
                status = "ALLOTTED"
                rationale = f"Retail category oversubscribed ({retail_sub:.1f}x). Computerized lottery drawn: Congratulations! Exactly 1 lot allotted per SEBI guidelines."
            else:
                lots_allotted = 0
                status = "NOT_ALLOTTED"
                rationale = f"Retail category oversubscribed ({retail_sub:.1f}x). Computerized lottery draw: Application not selected for allotment. 100% refund issued."

    else:  # NII Category (Pro-rata or lottery)
        if nii_sub <= 1.0:
            lots_allotted = lots_applied
            status = "ALLOTTED"
            rationale = f"NII category undersubscribed ({nii_sub:.1f}x). Full {lots_applied} lots allotted."
        else:
            # Pro-rata with fractional rounding
            allot_float = lots_applied / nii_sub
            lots_allotted = max(1 if rnd.random() < 0.6 else 0, math.floor(allot_float))
            lots_allotted = min(lots_applied, lots_allotted)

            if lots_allotted >= lots_applied:
                status = "ALLOTTED"
                rationale = f"NII category ({nii_sub:.1f}x oversubscribed). Pro-rata allocation granted {lots_allotted} lots."
            elif lots_allotted > 0:
                status = "PARTIAL_ALLOTMENT"
                rationale = f"NII category ({nii_sub:.1f}x oversubscribed). Pro-rata partial allotment of {lots_allotted} out of {lots_applied} lots."
            else:
                status = "NOT_ALLOTTED"
                rationale = f"NII category ({nii_sub:.1f}x oversubscribed). Pro-rata allocation fell below minimum lot threshold. Full refund issued."

    shares_allotted = lots_allotted * lot_size
    amount_utilized = round(shares_allotted * bid_price, 2)
    amount_refunded = round(amount_blocked - amount_utilized, 2)

    return {
        "application_id": application.get("application_id", f"APP-{uuid.uuid4().hex[:6].upper()}"),
        "ipo_id": ipo["id"],
        "symbol": ipo["symbol"],
        "category": category,
        "lots_applied": lots_applied,
        "shares_applied": shares_applied,
        "lots_allotted": lots_allotted,
        "shares_allotted": shares_allotted,
        "bid_price": bid_price,
        "amount_blocked": amount_blocked,
        "amount_utilized": amount_utilized,
        "amount_refunded": amount_refunded,
        "status": status,
        "rationale": rationale,
        "allotted_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def simulate_listing_day(
    ipo: Dict[str, Any],
    scenario: str = "strong",
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """Generate listing-day price discovery, price metrics, and intraday candles."""
    scenarios = ipo.get("listing_scenarios", {})
    target_sc = scenarios.get(scenario.lower(), scenarios.get("strong", {}))

    issue_price = float(ipo.get("cut_off_price", 500.0))
    open_price = float(target_sc.get("open_price", issue_price * 1.25))
    day_high = float(target_sc.get("day_high", open_price * 1.08))
    day_low = float(target_sc.get("day_low", open_price * 0.94))
    close_price = float(target_sc.get("close", open_price * 1.03))
    volume = int(target_sc.get("volume", 10000000))

    gain_inr = round(open_price - issue_price, 2)
    gain_pct = round((gain_inr / issue_price) * 100.0, 2)

    if seed is not None:
        rnd = random.Random(seed)
    else:
        rnd = random.Random()

    # Generate 12 intraday 30-minute interval candles
    candles = []
    cur_p = open_price
    times = [
        "10:00", "10:30", "11:00", "11:30", "12:00", "12:30",
        "13:00", "13:30", "14:00", "14:30", "15:00", "15:30",
    ]

    for idx, t in enumerate(times):
        if idx == 0:
            c_open = open_price
        else:
            c_open = cur_p

        if idx == len(times) - 1:
            c_close = close_price
        else:
            drift = (close_price - open_price) / len(times)
            noise = (rnd.random() - 0.48) * (open_price * 0.02)
            c_close = round(c_open + drift + noise, 2)

        c_high = round(max(c_open, c_close) + rnd.random() * (open_price * 0.015), 2)
        c_low = round(min(c_open, c_close) - rnd.random() * (open_price * 0.015), 2)
        c_vol = int((volume / len(times)) * (0.7 + rnd.random() * 0.6))

        candles.append({
            "time": t,
            "open": c_open,
            "high": c_high,
            "low": c_low,
            "close": c_close,
            "volume": c_vol,
        })
        cur_p = c_close

    return {
        "ipo_id": ipo["id"],
        "symbol": ipo["symbol"],
        "scenario": scenario.upper(),
        "issue_price": issue_price,
        "open_price": open_price,
        "gain_inr": gain_inr,
        "gain_pct": gain_pct,
        "day_high": day_high,
        "day_low": day_low,
        "close_price": close_price,
        "volume": volume,
        "candles": candles,
    }
