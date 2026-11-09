"""Tests for Market Surveillance & Fraud Detection Lab engine."""

import pytest
from chronosmatch.engine.surveillance_engine import (
    DEFAULT_THRESHOLDS,
    DETECTION_RULES,
    INITIAL_SURVEILLANCE_FEED,
    PRESET_SCENARIOS,
    SURVEILLANCE_LESSONS,
    SURVEILLANCE_CHALLENGES,
    detect_spoofing,
    detect_layering,
    detect_wash_trading,
    detect_pump_and_dump,
    detect_unusual_volume,
    detect_abnormal_price,
    run_surveillance_analysis,
    generate_synthetic_related_orders,
    generate_synthetic_timeline,
    generate_investigation_csv,
    generate_investigation_dossier,
)


def test_detection_rules_catalog():
    """Verify detection rules catalog contains all 6 required manipulation patterns."""
    assert len(DETECTION_RULES) == 6
    patterns = {r["pattern"] for r in DETECTION_RULES}
    expected = {
        "Spoofing",
        "Layering",
        "Wash Trading",
        "Pump and Dump",
        "Unusual Volume",
        "Abnormal Price Movement",
    }
    assert patterns == expected
    for r in DETECTION_RULES:
        assert r["id"].strip()
        assert r["name"].strip()
        assert r["severity"] in {"CRITICAL", "HIGH", "WARNING"}
        assert "regulatory_basis" in r


def test_detect_spoofing():
    """Test spoofing detection triggers on outsized orders quickly cancelled."""
    # Positive case: 5.5x median size, cancelled in 280ms, 0 fills
    res = detect_spoofing({
        "order_size_ratio": 5.5,
        "cancel_latency_ms": 280,
        "fill_percentage": 0.0,
    })
    assert res is not None
    assert res["rule_id"] == "SPOOF-01"
    assert res["pattern"] == "Spoofing"
    assert res["severity"] == "CRITICAL"
    assert res["metrics"]["order_size_ratio"] == 5.5
    assert "SPOOF-01" in res["explanation"]["rule_triggered"]

    # Negative case: Normal order size (0.8x), cancelled in 400ms -> Clean
    clean = detect_spoofing({
        "order_size_ratio": 0.8,
        "cancel_latency_ms": 400,
        "fill_percentage": 0.0,
    })
    assert clean is None


def test_detect_layering():
    """Test layering detection triggers on multi-tier order books with high cancellations."""
    # Positive case: 4 depth tiers, 92.5% cancellation
    res = detect_layering({
        "tier_count": 4,
        "cancel_rate_pct": 92.5,
    })
    assert res is not None
    assert res["rule_id"] == "LAYER-02"
    assert res["pattern"] == "Layering"
    assert res["metrics"]["tier_count"] == 4
    assert res["metrics"]["cancel_rate_pct"] == 92.5

    # Negative case: 2 tiers, 50% cancellation -> Clean
    clean = detect_layering({
        "tier_count": 2,
        "cancel_rate_pct": 50.0,
    })
    assert clean is None


def test_detect_wash_trading():
    """Test wash trading detection triggers on circular matched round trips with zero delta."""
    # Positive case: 6 round trips, 0% net delta, 0.05% price variance
    res = detect_wash_trading({
        "round_trips": 6,
        "net_delta_pct": 0.0,
        "price_variance_pct": 0.05,
    })
    assert res is not None
    assert res["rule_id"] == "WASH-03"
    assert res["pattern"] == "Wash Trading"
    assert res["metrics"]["round_trips"] == 6
    assert res["metrics"]["net_delta_pct"] == 0.0

    # Negative case: 1 round trip with 25% net delta -> Clean
    clean = detect_wash_trading({
        "round_trips": 1,
        "net_delta_pct": 25.0,
        "price_variance_pct": 1.5,
    })
    assert clean is None


def test_detect_pump_and_dump():
    """Test pump and dump detection on aggressive markup followed by immediate reversal."""
    # Positive case: 12.4% runup, 95% reversal, 150s duration
    res = detect_pump_and_dump({
        "runup_pct": 12.4,
        "reversal_pct": 95.0,
        "cycle_duration_sec": 150,
    })
    assert res is not None
    assert res["rule_id"] == "PUMP-04"
    assert res["pattern"] == "Pump and Dump"
    assert res["metrics"]["runup_pct"] == 12.4
    assert res["metrics"]["reversal_pct"] == 95.0

    # Negative case: 3% runup, 20% pullback over 600s -> Clean
    clean = detect_pump_and_dump({
        "runup_pct": 3.0,
        "reversal_pct": 20.0,
        "cycle_duration_sec": 600,
    })
    assert clean is None


def test_detect_unusual_volume_and_price():
    """Test unusual volume and abnormal price movement detectors."""
    # Volume: 6.2x median
    vol_res = detect_unusual_volume({
        "volume_multiplier": 6.2,
        "concentration_pct": 78.0,
    })
    assert vol_res is not None
    assert vol_res["rule_id"] == "VOL-05"

    # Price: 4.1 sigma in 12s
    price_res = detect_abnormal_price({
        "sigma_deviation": 4.1,
        "time_window_sec": 12,
    })
    assert price_res is not None
    assert price_res["rule_id"] == "PRICE-06"


def test_false_positive_benign_market_maker():
    """Verify that legitimate market making activity is classified as FALSE_POSITIVE and not flagged."""
    benign_params = PRESET_SCENARIOS["SCN_BENIGN_MARKET_MAKER"]["params"]
    res = run_surveillance_analysis(benign_params)

    assert res["status"] == "CLEARED"
    assert res["verdict"] == "FALSE_POSITIVE"
    assert res["severity"] == "BENIGN"
    assert len(res["rules_triggered"]) == 0
    assert "Normal trading activity" in res["explanation"]["what_detected"]
    assert "NONE" in res["explanation"]["rule_triggered"]


def test_run_surveillance_analysis_full_pipeline():
    """Test full analysis pipeline with synthetic orders, timeline, and audit trails."""
    spoof_scenario = PRESET_SCENARIOS["SCN_SPOOFING"]
    res = run_surveillance_analysis(spoof_scenario["params"])

    assert res["status"] == "FLAGGED"
    assert res["verdict"] == "CONFIRMED_SIMULATION"
    assert res["primary_pattern"] == "Spoofing"
    assert res["rule_id"] == "SPOOF-01"
    assert len(res["related_orders"]) >= 3
    assert len(res["timeline"]) >= 3
    assert res["investigation_id"].startswith("INV-2026-")
    assert res["alert_id"].startswith("ALT-2026-")


def test_investigation_csv_and_dossier_generation():
    """Test CSV export and print-friendly text dossier generation."""
    spoof_scenario = PRESET_SCENARIOS["SCN_SPOOFING"]
    inv = run_surveillance_analysis(spoof_scenario["params"])

    csv_out = generate_investigation_csv(inv)
    assert "INVESTIGATION_ID,ALERT_ID,SYMBOL" in csv_out
    assert "ORDER_RECORDS" in csv_out
    assert "TIMELINE_EVENTS" in csv_out
    assert inv["investigation_id"] in csv_out

    dossier_out = generate_investigation_dossier(inv)
    assert "CHRONOSMATCH MARKET SURVEILLANCE & FRAUD DETECTION LAB" in dossier_out
    assert "OFFICIAL SIMULATED INVESTIGATION DOSSIER" in dossier_out
    assert inv["investigation_id"] in dossier_out
    assert "REGULATORY DISCLAIMER" in dossier_out


def test_surveillance_academy_and_challenges():
    """Verify lessons and challenge mode questions are well-formed and scored correctly."""
    assert len(SURVEILLANCE_LESSONS) >= 4
    for les in SURVEILLANCE_LESSONS:
        assert les["id"].startswith("LESSON-")
        assert les["title"]
        assert len(les["content"]) > 100

    assert len(SURVEILLANCE_CHALLENGES) >= 5
    total_pts = 0
    for ch in SURVEILLANCE_CHALLENGES:
        assert ch["id"].startswith("CHALLENGE-")
        assert ch["title"]
        assert len(ch["options"]) == 4
        # Exactly 1 correct option
        correct = [o for o in ch["options"] if o.get("is_correct")]
        assert len(correct) == 1
        assert ch["explanation"]
        assert ch["points"] > 0
        total_pts += ch["points"]

    assert total_pts >= 500


def test_db_surveillance_investigations(tmp_path):
    """Test saving, retrieving, and updating surveillance investigations in SQLite DB."""
    from chronosmatch.persistence.db import Database
    db_file = tmp_path / "test_surveillance.db"
    test_db = Database(db_path=str(db_file))

    # Create user first
    test_db.create_user("analyst@chronos.io", "Lead Analyst", "Secret123!")

    # Save investigation
    inv_data = {
        "investigation_id": "INV-TEST-001",
        "alert_id": "ALT-TEST-01",
        "symbol": "RELIANCE",
        "primary_pattern": "Spoofing",
        "rule_id": "SPOOF-01",
        "severity": "CRITICAL",
        "status": "NEW",
        "notes": "Initial alert logged by automated surveillance.",
    }
    saved = test_db.save_surveillance_investigation("analyst@chronos.io", inv_data)
    assert saved["investigation_id"] == "INV-TEST-001"
    assert saved["status"] == "NEW"

    # Retrieve investigations
    records = test_db.get_surveillance_investigations("analyst@chronos.io")
    assert len(records) == 1
    assert records[0]["investigation_id"] == "INV-TEST-001"
    assert records[0]["primary_pattern"] == "Spoofing"
    assert records[0]["status"] == "NEW"

    # Update status to UNDER_REVIEW
    ok = test_db.update_surveillance_investigation_status(
        "analyst@chronos.io", "INV-TEST-001", "UNDER_REVIEW", "Reviewing contra-side order logs."
    )
    assert ok is True

    # Verify update
    updated_records = test_db.get_surveillance_investigations("analyst@chronos.io")
    assert updated_records[0]["status"] == "UNDER_REVIEW"
    assert updated_records[0]["notes"] == "Reviewing contra-side order logs."


def test_surveillance_api_endpoints():
    """Test FastAPI REST endpoints for Surveillance Lab."""
    from starlette.testclient import TestClient
    from api.index import app

    client = TestClient(app)

    # 1. Dashboard
    r_dash = client.get("/api/surveillance/dashboard")
    assert r_dash.status_code == 200
    d_data = r_dash.json()
    assert d_data["status"] == "success"
    assert "total_events_monitored" in d_data["stats"]
    assert len(d_data["feed"]) > 0

    # 2. Rules
    r_rules = client.get("/api/surveillance/rules")
    assert r_rules.status_code == 200
    assert len(r_rules.json()["rules"]) == 6

    # 3. Scenarios
    r_scen = client.get("/api/surveillance/scenarios")
    assert r_scen.status_code == 200
    assert len(r_scen.json()["scenarios"]) >= 6

    # 4. Simulate Scenario
    r_sim = client.post("/api/surveillance/simulate", json={
        "scenario_id": "SCN_SPOOFING",
        "symbol": "RELIANCE",
        "params": {"order_size": 1800, "cancel_latency_ms": 280},
    })
    assert r_sim.status_code == 200
    sim_data = r_sim.json()
    assert sim_data["status"] == "success"
    assert sim_data["investigation"]["primary_pattern"] == "Spoofing"

    # 5. Challenges and submission
    r_chal = client.get("/api/surveillance/challenges")
    assert r_chal.status_code == 200
    ch_data = r_chal.json()
    assert len(ch_data["challenges"]) >= 5

    target_ch = ch_data["challenges"][0]
    # Submit correct answer A for Challenge 1
    r_sub = client.post("/api/surveillance/challenges/submit", json={
        "challenge_id": target_ch["id"],
        "selected_option_id": "A",
    })
    assert r_sub.status_code == 200
    sub_data = r_sub.json()
    assert sub_data["is_correct"] is True
    assert sub_data["points_awarded"] == 100

    # 6. CSV Export
    r_exp = client.get(f"/api/surveillance/export/INV-EXPORT-TEST?format=csv")
    assert r_exp.status_code == 200
    assert "INVESTIGATION_ID,ALERT_ID,SYMBOL" in r_exp.text


