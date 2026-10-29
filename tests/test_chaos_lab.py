"""Comprehensive automated tests for Chaos & Resilience Laboratory."""

import pytest
from fastapi.testclient import TestClient

from api.index import app
from chronosmatch.engine.chaos_lab import (
    ChaosConfig,
    ChaosSimulationEngine,
    FailureType,
    SimulationScenario,
    compare_chaos_scenarios,
    run_chaos_simulation,
)


@pytest.fixture
def client():
    return TestClient(app)


# =====================================================================
# 1. CORE SIMULATION ENGINE TESTS
# =====================================================================
def test_chaos_lab_normal_simulation():
    """Verify normal baseline simulation executes and all invariants pass cleanly."""
    res = run_chaos_simulation(
        seed=42,
        symbol="BTCUSDT",
        num_events=80,
        scenario="NORMAL",
        failure_type="NONE",
    )

    assert res["status"] == "success"
    assert res["is_simulated"] is True
    assert "disclaimer" in res

    # Telemetry checks
    telemetry = res["telemetry"]
    assert telemetry["total_incoming_orders"] == 80
    assert telemetry["total_processed_orders"] > 0
    assert telemetry["latency"]["p50_us"] > 0
    assert telemetry["latency"]["p99_us"] >= telemetry["latency"]["p50_us"]

    # Invariants checks
    invariants = res["invariants"]
    assert invariants["all_passed"] is True
    assert invariants["passed_count"] == invariants["total_checks"] == 5

    # Check report
    report = res["incident_report"]
    assert report["recovery_status"] == "FULL_RECOVERY"
    assert report["all_invariants_preserved"] is True
    assert len(report["recommendations"]) > 0


def test_chaos_lab_duplicate_order_idempotency_safeguard():
    """Verify duplicate order fault injection trips the idempotency filter and prevents double fills."""
    res = run_chaos_simulation(
        seed=101,
        symbol="BTCUSDT",
        num_events=100,
        scenario="NORMAL",
        failure_type="DUPLICATE_ORDER",
    )

    assert res["status"] == "success"
    sg = res["telemetry"]["safeguards_triggered"]
    assert sg["idempotency_blocked"] >= 1, "Expected idempotency safeguard to block at least one duplicate order"

    # Invariants must still hold because defense guard intercepted the duplicates
    inv = res["invariants"]
    assert inv["all_passed"] is True
    no_dup_check = next(c for c in inv["checks"] if c["name"] == "No Duplicate Executions")
    assert no_dup_check["passed"] is True


def test_chaos_lab_invalid_payload_sanitation():
    """Verify corrupted payloads are intercepted by input validator without crashing or mutating book."""
    res = run_chaos_simulation(
        seed=202,
        symbol="BTCUSDT",
        num_events=100,
        scenario="NORMAL",
        failure_type="INVALID_PAYLOAD",
    )

    assert res["status"] == "success"
    sg = res["telemetry"]["safeguards_triggered"]
    assert sg["invalid_payload_rejected"] >= 1, "Expected input validator to reject malformed payloads"

    inv = res["invariants"]
    assert inv["all_passed"] is True


def test_chaos_lab_queue_overflow_and_rate_limiting():
    """Verify queue overflow under high ingress triggers rate limiting queue shedding."""
    res = run_chaos_simulation(
        seed=303,
        symbol="BTCUSDT",
        num_events=120,
        incoming_rate=4000.0,
        processing_capacity=500.0,
        queue_capacity=15,
        scenario="HIGH_LOAD",
        failure_type="TRAFFIC_SPIKE",
    )

    assert res["status"] == "success"
    telemetry = res["telemetry"]
    assert telemetry["safeguards_triggered"]["queue_overflow_shed"] >= 1, "Expected queue overflow shedding to activate"
    assert telemetry["total_rejected_orders"] > 0


def test_chaos_lab_engine_pause_recovery():
    """Verify simulated engine stall queues backlog and drains back to zero with measured recovery duration."""
    res = run_chaos_simulation(
        seed=404,
        symbol="BTCUSDT",
        num_events=90,
        scenario="RECOVERY",
        failure_type="ENGINE_PAUSE",
    )

    assert res["status"] == "success"
    inv = res["invariants"]
    assert inv["all_passed"] is True
    # Backlog must have drained to 0
    assert inv["recovery_duration_ms"] > 0
    q_check = next(c for c in inv["checks"] if c["name"] == "Queue Backlog Drained & System Recovered")
    assert q_check["passed"] is True


def test_chaos_lab_liquidity_shock():
    """Verify liquidity shock causes wide spreads and book thinning."""
    res = run_chaos_simulation(
        seed=505,
        symbol="BTCUSDT",
        num_events=80,
        scenario="LIQUIDITY_SHOCK",
        failure_type="LIQUIDITY_DRYUP",
    )

    assert res["status"] == "success"
    assert res["telemetry"]["total_cancelled_orders"] > 0


def test_chaos_lab_deterministic_reproducibility():
    """Verify identical seeds produce identical results across simulation runs."""
    res1 = run_chaos_simulation(seed=777, symbol="BTCUSDT", num_events=75, scenario="NORMAL")
    res2 = run_chaos_simulation(seed=777, symbol="BTCUSDT", num_events=75, scenario="NORMAL")

    assert res1["telemetry"]["total_incoming_orders"] == res2["telemetry"]["total_incoming_orders"]
    assert res1["telemetry"]["total_processed_orders"] == res2["telemetry"]["total_processed_orders"]
    assert res1["telemetry"]["total_rejected_orders"] == res2["telemetry"]["total_rejected_orders"]
    assert res1["telemetry"]["max_queue_depth"] == res2["telemetry"]["max_queue_depth"]


def test_chaos_lab_scenario_comparison():
    """Verify side-by-side comparison executes baseline and failure with delta calculations."""
    comp = compare_chaos_scenarios(
        seed=888,
        symbol="BTCUSDT",
        num_events=80,
        baseline_scenario="NORMAL",
        stressed_scenario="HIGH_LOAD",
        failure_type="ENGINE_PAUSE",
    )

    assert comp["status"] == "success"
    assert comp["seed"] == 888
    assert "baseline" in comp
    assert "stressed" in comp
    deltas = comp["comparison_deltas"]
    assert "p50_latency_delta_us" in deltas
    assert "max_queue_depth_delta" in deltas
    assert "rejection_rate_base_pct" in deltas
    assert "rejection_rate_stress_pct" in deltas
    assert deltas["baseline_invariants_passed"] is True


# =====================================================================
# 2. FASTAPI ENDPOINT TESTS
# =====================================================================
def test_api_chaos_presets(client):
    """Verify GET /api/chaos/presets returns available presets."""
    response = client.get("/api/chaos/presets")
    assert response.status_code == 200
    data = response.json()
    assert "presets" in data
    assert "NORMAL" in data["presets"]
    assert "HIGH_LOAD" in data["presets"]
    assert "LIQUIDITY_SHOCK" in data["presets"]


def test_api_chaos_run_simulation(client):
    """Verify POST /api/chaos/run-simulation runs successfully."""
    payload = {
        "seed": 999,
        "symbol": "BTCUSDT",
        "num_events": 60,
        "incoming_rate": 800.0,
        "num_participants": 8,
        "cancel_rate_pct": 10.0,
        "liquidity_depth": 15,
        "processing_capacity": 2000.0,
        "network_delay_ms": 3.0,
        "queue_capacity": 80,
        "scenario": "NORMAL",
        "failure_type": "NONE",
    }
    response = client.post("/api/chaos/run-simulation", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["is_simulated"] is True
    assert data["invariants"]["all_passed"] is True


def test_api_chaos_compare_scenarios(client):
    """Verify POST /api/chaos/compare-scenarios returns comparative results."""
    payload = {
        "seed": 555,
        "symbol": "BTCUSDT",
        "num_events": 60,
        "baseline_scenario": "NORMAL",
        "stressed_scenario": "HIGH_LOAD",
        "failure_type": "DUPLICATE_ORDER",
    }
    response = client.post("/api/chaos/compare-scenarios", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "comparison_deltas" in data
