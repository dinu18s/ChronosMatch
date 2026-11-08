"""Automated tests for ChronosMatch Macroeconomic Simulator & Economic Events Terminal."""

import pytest
from fastapi.testclient import TestClient
from api.index import app
from chronosmatch.engine.macro_simulator import (
    ECONOMIC_EVENTS,
    PRESET_SCENARIOS,
    calculate_macro_impact,
    compare_macro_scenarios,
    get_cross_asset_flow_map,
)


@pytest.fixture
def client():
    return TestClient(app)


def test_economic_events_catalog(client):
    """Verify the economic events endpoint returns expected indicators with sample labels."""
    response = client.get("/api/macro/events")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    events = data["events"]
    assert len(events) >= 8

    # Check key expected indicators
    indicator_names = [e["name"] for e in events]
    assert any("RBI" in name for name in indicator_names)
    assert any("Federal Reserve" in name for name in indicator_names)
    assert any("CPI" in name for name in indicator_names)
    assert any("GDP" in name for name in indicator_names)
    assert any("Crude Oil" in name for name in indicator_names)
    assert any("USD / INR" in name for name in indicator_names)

    for ev in events:
        assert ev["is_simulated"] is True
        assert "previous" in ev
        assert "expected" in ev
        assert "actual" in ev
        assert "importance" in ev


def test_macro_presets(client):
    """Verify preset macroeconomic scenarios are available."""
    response = client.get("/api/macro/presets")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    presets = data["presets"]
    assert "HAWKISH_SHOCK" in presets
    assert "DOVISH_EASING" in presets
    assert "OIL_SURGE" in presets
    assert "STAGFLATION" in presets


def test_deterministic_macro_simulation():
    """Verify economic transmission mechanics: rate hikes, oil surges, and growth shocks."""
    # 1. Hawkish Rate Hike Shock
    hawkish = calculate_macro_impact({
        "rbi_rate_bps": 50.0,
        "fed_rate_bps": 75.0,
        "cpi_inflation_pct": 1.0,
        "gdp_growth_pct": -0.4,
    })
    assert hawkish["regime"] == "Hawkish Monetary Tightening"
    asset_map = {a["id"]: a["impact_pct"] for a in hawkish["assets"]}
    assert asset_map["SP500"] < 0, "Fed rate hike must compress US equities"
    assert asset_map["CRYPTO"] < -3.0, "Crypto must react negatively to aggressive rate hikes"
    assert "disclaimer" in hawkish

    # 2. Oil Surge Shock
    oil_surge = calculate_macro_impact({
        "crude_oil_pct": 30.0,
        "cpi_inflation_pct": 1.5,
        "usdinr_change_pct": 2.5,
    })
    assert oil_surge["regime"] == "Cost-Push Inflationary Shock"
    oil_asset_map = {a["id"]: a["impact_pct"] for a in oil_surge["assets"]}
    assert oil_asset_map["ENERGY"] > 5.0, "Energy sector must gain on crude surge"
    assert oil_asset_map["GOLD"] > 3.0, "Gold must gain on inflation/currency pressure"
    assert oil_asset_map["NIFTY50"] < 0, "High crude import bill must drag Indian equities"

    # 3. India Growth Boom
    growth = calculate_macro_impact({
        "gdp_growth_pct": 1.5,
        "usdinr_change_pct": -1.5,
    })
    growth_asset_map = {a["id"]: a["impact_pct"] for a in growth["assets"]}
    assert growth_asset_map["NIFTY50"] > 2.0, "Strong domestic GDP must boost Nifty"
    assert growth_asset_map["BANK_NIFTY"] > 3.0, "Strong domestic GDP accelerates bank credit"


def test_boundary_clamping_and_reproducibility():
    """Test extreme input clamping without crashes and deterministic reproducibility."""
    extreme_shocks = {
        "rbi_rate_bps": 99999.0,
        "fed_rate_bps": -99999.0,
        "crude_oil_pct": 500.0,
        "cpi_inflation_pct": 100.0,
        "gdp_growth_pct": -50.0,
        "usdinr_change_pct": 100.0,
    }
    res1 = calculate_macro_impact(extreme_shocks)
    res2 = calculate_macro_impact(extreme_shocks)
    assert res1 == res2, "Simulation calculations must be 100% reproducible"

    for asset in res1["assets"]:
        assert not any(str(asset["impact_pct"]) == v for v in ["nan", "inf", "-inf"])


def test_api_macro_simulate_endpoint(client):
    """Test POST /api/macro/simulate endpoint."""
    payload = {
        "rbi_rate_bps": 25.0,
        "fed_rate_bps": 50.0,
        "crude_oil_pct": 10.0,
        "cpi_inflation_pct": 0.5,
        "gdp_growth_pct": 0.2,
        "scenario_name": "Test Inflation Spike"
    }
    response = client.post("/api/macro/simulate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    sim = data["simulation"]
    assert sim["scenario_name"] == "Test Inflation Spike"
    assert len(sim["assets"]) == 8
    assert len(sim["top_winners"]) <= 3
    assert len(sim["top_losers"]) <= 3


def test_api_macro_compare_endpoint(client):
    """Test POST /api/macro/compare scenario comparison endpoint."""
    payload = {
        "scenarios": [
            {
                "id": "SC-1",
                "name": "Scenario 1: Hawkish Tightening",
                "shocks": {"rbi_rate_bps": 50.0, "fed_rate_bps": 75.0}
            },
            {
                "id": "SC-2",
                "name": "Scenario 2: Liquidity Easing",
                "shocks": {"rbi_rate_bps": -50.0, "fed_rate_bps": -75.0}
            }
        ]
    }
    response = client.post("/api/macro/compare", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    cmp = data["comparison"]
    assert cmp["scenario_count"] == 2
    assert "divergence" in cmp
    assert "NIFTY50" in cmp["divergence"]
    # Divergence between hawkish and easing should be positive
    assert cmp["divergence"]["NIFTY50"]["spread"] > 1.0


def test_macro_flow_map_endpoint(client):
    """Test GET /api/macro/flow-map/{scenario_type} endpoint."""
    res_rate = client.get("/api/macro/flow-map/rate_hike")
    assert res_rate.status_code == 200
    data_rate = res_rate.json()
    assert len(data_rate["flow_map"]["steps"]) >= 4

    res_oil = client.get("/api/macro/flow-map/oil_shock")
    assert res_oil.status_code == 200
    data_oil = res_oil.json()
    assert len(data_oil["flow_map"]["steps"]) >= 4
