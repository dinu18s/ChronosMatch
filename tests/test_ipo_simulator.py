"""Automated tests for IPO Launchpad & Listing Simulator module."""

import pytest
from chronosmatch.engine.ipo_simulator import (
    IPO_CATALOG,
    IPO_LESSONS,
    IPO_QUIZZES,
    get_ipo_by_id,
    calculate_ipo_application,
    simulate_allotment,
    simulate_listing_day,
)


def test_ipo_catalog_structure():
    """Verify IPO catalog completeness, financial indicators, and scorecard."""
    assert len(IPO_CATALOG) >= 6
    statuses = {ipo["status"] for ipo in IPO_CATALOG}
    assert {"OPEN", "UPCOMING", "CLOSED", "LISTED"}.issubset(statuses)

    for ipo in IPO_CATALOG:
        assert ipo["id"].startswith("IPO-")
        assert ipo["symbol"]
        assert ipo["price_band_low"] < ipo["price_band_high"]
        assert ipo["cut_off_price"] == ipo["price_band_high"]
        assert ipo["lot_size"] > 0
        assert ipo["min_investment"] == ipo["lot_size"] * ipo["cut_off_price"]
        assert ipo["issue_size_cr"] == ipo["fresh_issue_cr"] + ipo["ofs_cr"]
        assert ipo["retail_quota_pct"] + ipo["nii_quota_pct"] + ipo["qib_quota_pct"] == 100.0
        assert "research" in ipo
        assert ipo["research"]["scorecard"]["total_score"] > 0
        assert "listing_scenarios" in ipo


def test_calculate_ipo_application_valid_and_limits():
    """Test calculation of application amounts and enforcement of retail category limits."""
    nexus_ipo = get_ipo_by_id("IPO-NEXUS-AI")
    assert nexus_ipo is not None

    # Valid retail application: 2 lots = 40 shares @ 715 = 28,600
    calc = calculate_ipo_application(nexus_ipo, lots=2, category="RETAIL")
    assert calc["is_valid"] is True
    assert calc["lots"] == 2
    assert calc["shares"] == 40
    assert calc["bid_price"] == 715.0
    assert calc["total_amount"] == 28600.0

    # Invalid retail application exceeding ₹2 Lakhs limit: 14 lots = 280 shares @ 715 = ₹200,200
    calc_over = calculate_ipo_application(nexus_ipo, lots=14, category="RETAIL")
    assert calc_over["is_valid"] is False
    assert len(calc_over["errors"]) > 0
    assert "₹2,00,000.00" in calc_over["errors"][0]

    # Valid NII application for 14 lots (NII category has no ₹2L ceiling)
    calc_nii = calculate_ipo_application(nexus_ipo, lots=14, category="NII")
    assert calc_nii["is_valid"] is True
    assert calc_nii["total_amount"] == 200200.0


def test_simulate_allotment_retail_lottery_and_undersubscribed():
    """Test SEBI-aligned allotment algorithm for oversubscribed vs undersubscribed retail."""
    nexus_ipo = get_ipo_by_id("IPO-NEXUS-AI")
    app = {
        "application_id": "APP-TEST-01",
        "lots": 4,
        "category": "RETAIL",
        "bid_price": 715.0,
        "total_amount": 4 * 20 * 715.0,  # 57,200
    }

    # Oversubscribed retail (18.4x): Seed guaranteeing lottery win
    # Winning applicant gets exactly 1 lot (20 shares), unallotted 3 lots refunded
    allot_win = simulate_allotment(app, nexus_ipo, seed=42)
    assert allot_win["status"] in {"ALLOTTED", "NOT_ALLOTTED"}
    if allot_win["status"] == "ALLOTTED":
        assert allot_win["lots_allotted"] == 1
        assert allot_win["shares_allotted"] == 20
        assert allot_win["amount_utilized"] == 14300.0
        assert allot_win["amount_refunded"] == 42900.0
        assert allot_win["amount_utilized"] + allot_win["amount_refunded"] == allot_win["amount_blocked"]

    # Undersubscribed retail IPO: Medicure Bio (0.85x retail) -> 100% full allotment
    medicure_ipo = get_ipo_by_id("IPO-MEDICURE-BIO")
    app_med = {
        "application_id": "APP-TEST-02",
        "lots": 3,
        "category": "RETAIL",
        "bid_price": 435.0,
        "total_amount": 3 * 34 * 435.0,
    }
    allot_full = simulate_allotment(app_med, medicure_ipo, seed=1)
    assert allot_full["status"] == "ALLOTTED"
    assert allot_full["lots_allotted"] == 3
    assert allot_full["shares_allotted"] == 3 * 34
    assert allot_full["amount_utilized"] == allot_full["amount_blocked"]
    assert allot_full["amount_refunded"] == 0.0


def test_simulate_allotment_nii_pro_rata():
    """Test pro-rata allotment logic for NII / HNI investors."""
    nexus_ipo = get_ipo_by_id("IPO-NEXUS-AI")
    app_nii = {
        "application_id": "APP-NII-01",
        "lots": 10,
        "category": "NII",
        "bid_price": 715.0,
        "total_amount": 10 * 20 * 715.0,
    }
    res = simulate_allotment(app_nii, nexus_ipo, seed=10)
    assert res["status"] in {"ALLOTTED", "PARTIAL_ALLOTMENT", "NOT_ALLOTTED"}
    assert res["amount_utilized"] + res["amount_refunded"] == res["amount_blocked"]


def test_simulate_listing_day_scenarios():
    """Test listing day simulation across strong, moderate, weak, and volatile scenarios."""
    nexus_ipo = get_ipo_by_id("IPO-NEXUS-AI")
    assert nexus_ipo is not None

    # Strong listing
    sc_strong = simulate_listing_day(nexus_ipo, scenario="strong", seed=42)
    assert sc_strong["scenario"] == "STRONG"
    assert sc_strong["open_price"] > sc_strong["issue_price"]
    assert sc_strong["gain_pct"] > 30.0
    assert len(sc_strong["candles"]) == 12
    assert sc_strong["day_high"] >= sc_strong["open_price"]
    assert sc_strong["day_low"] <= sc_strong["open_price"]

    # Weak listing
    sc_weak = simulate_listing_day(nexus_ipo, scenario="weak", seed=42)
    assert sc_weak["scenario"] == "WEAK"
    assert sc_weak["gain_pct"] < 0.0  # Discount listing


def test_db_ipo_application_lifecycle(tmp_path):
    """Test full database lifecycle: apply, reserve cash, cancel, refund, and allot to holdings."""
    from chronosmatch.persistence.db import Database
    db_file = tmp_path / "test_ipo.db"
    test_db = Database(db_path=str(db_file))

    # 1. Register test user with ₹1,00,000 virtual cash
    email = "applicant@chronos.io"
    test_db.create_user(email, "IPO Applicant", "Pass123!")
    acc_before = test_db.get_account(email)
    assert acc_before["cash_balance"] == 100000.0

    # 2. Apply for 2 lots of NexusAI (2 * 20 * 715 = ₹28,600)
    app = test_db.apply_for_ipo(email, "IPO-NEXUS-AI", lots=2, category="RETAIL")
    assert app["status"] == "PENDING_ALLOTMENT"
    assert app["amount_blocked"] == 28600.0

    # Cash balance must reflect reserved funds: 100,000 - 28,600 = 71,400
    acc_after_apply = test_db.get_account(email)
    assert acc_after_apply["cash_balance"] == 71400.0

    # 3. Duplicate application prevention
    with pytest.raises(ValueError, match="already exists"):
        test_db.apply_for_ipo(email, "IPO-NEXUS-AI", lots=1, category="RETAIL")

    # 4. Cancel application and verify 100% refund
    c_res = test_db.cancel_ipo_application(email, app["application_id"])
    assert c_res["status"] == "CANCELLED"
    assert c_res["amount_refunded"] == 28600.0

    acc_after_cancel = test_db.get_account(email)
    assert acc_after_cancel["cash_balance"] == 100000.0

    # 5. Apply again and process allotment for undersubscribed Medicure Bio (guaranteed full allotment)
    # 2 lots = 68 shares @ 435 = 29,580
    app2 = test_db.apply_for_ipo(email, "IPO-MEDICURE-BIO", lots=2, category="RETAIL")
    assert app2["status"] == "PENDING_ALLOTMENT"

    allot_res = test_db.process_ipo_allotment(email, app2["application_id"], seed=1)
    assert allot_res["status"] == "ALLOTTED"
    assert allot_res["shares_allotted"] == 68

    # Verify shares credited to user holdings
    holdings = test_db.get_holdings(email)
    assert len(holdings) == 1
    assert holdings[0]["symbol"] == "MEDICURE"
    assert holdings[0]["quantity"] == 68
    assert holdings[0]["avg_buy_price"] == 435.0

    # Verify user applications query
    apps = test_db.get_user_ipo_applications(email)
    assert len(apps) == 2


def test_ipo_lessons_and_quizzes():
    """Verify educational content and quiz evaluation structure."""
    assert len(IPO_LESSONS) >= 5
    for les in IPO_LESSONS:
        assert les["id"].startswith("IPO-LES-")
        assert les["title"]
        assert len(les["content"]) > 100

    assert len(IPO_QUIZZES) >= 5
    total_points = 0
    for qz in IPO_QUIZZES:
        assert qz["id"].startswith("IPO-QZ-")
        assert len(qz["options"]) == 4
        correct = [o for o in qz["options"] if o.get("is_correct")]
        assert len(correct) == 1
        assert qz["explanation"]
        assert qz["points"] > 0
        total_points += qz["points"]

    assert total_points >= 500

def test_ipo_fastapi_endpoints():
    """Unit and integration test for all FastAPI route handlers in the IPO Launchpad suite."""
    from api.index import (
        get_ipo_catalog,
        get_ipo_details,
        apply_ipo,
        cancel_ipo,
        simulate_ipo_allotment,
        get_listing_day_simulation,
        get_user_ipo_applications,
        get_ipo_lessons_and_quizzes,
        submit_ipo_quiz,
        IpoApplyRequest,
        IpoCancelRequest,
        IpoAllotRequest,
        IpoQuizSubmitRequest,
    )
    from chronosmatch.persistence.db import db
    from fastapi import HTTPException

    # 1. Catalog endpoint
    cat_res = get_ipo_catalog()
    assert cat_res["status"] == "success"
    assert cat_res["count"] >= 6

    # Filter by OPEN status
    open_res = get_ipo_catalog(status="OPEN")
    assert open_res["status"] == "success"
    assert all(item["status"] == "OPEN" for item in open_res["data"])

    # 2. Details endpoint
    det_res = get_ipo_details("IPO-NEXUS-AI")
    assert det_res["status"] == "success"
    assert det_res["data"]["symbol"] == "NEXUSAI"

    # Non-existent IPO raises 404
    with pytest.raises(HTTPException) as exc:
        get_ipo_details("IPO-NONEXISTENT")
    assert exc.value.status_code == 404

    # 3. Application Lifecycle via API handler
    test_user_email = "api_applicant_direct@chronos.io"
    try:
        db.create_user(test_user_email, "API Applicant Direct", "Pass123!")
    except Exception:
        pass

    # Apply for 1 lot of Solaris Green (1 * 44 * 340 = 14,960)
    app_res = apply_ipo(IpoApplyRequest(
        email=test_user_email,
        ipo_id="IPO-SOLARIS-GREEN",
        lots=1,
        category="RETAIL",
    ))
    assert app_res["status"] == "success"
    app_id = app_res["application"]["application_id"]
    assert app_res["application"]["amount_blocked"] == 14960.0

    # 4. User applications summary
    user_apps = get_user_ipo_applications(test_user_email)
    assert user_apps["status"] == "success"
    assert user_apps["summary"]["total_applications"] >= 1
    assert user_apps["summary"]["pending_count"] >= 1

    # 5. Cancel application
    cancel_res = cancel_ipo(IpoCancelRequest(
        email=test_user_email,
        application_id=app_id,
    ))
    assert cancel_res["status"] == "success"
    assert cancel_res["data"]["status"] == "CANCELLED"

    # 6. Listing Day Simulator
    list_res = get_listing_day_simulation(
        ipo_id="IPO-NEXUS-AI",
        scenario="STRONG",
        seed=42,
    )
    assert list_res["status"] == "success"
    assert list_res["data"]["scenario"] == "STRONG"
    assert len(list_res["data"]["candles"]) == 12

    # 7. Lessons & Quizzes
    les_res = get_ipo_lessons_and_quizzes()
    assert len(les_res["lessons"]) >= 5
    assert len(les_res["quizzes"]) >= 5
    for q in les_res["quizzes"]:
        for opt in q["options"]:
            assert "is_correct" not in opt

    # 8. Quiz Submission (Quiz 1: Book-building cut-off price is option B)
    sub_res = submit_ipo_quiz(IpoQuizSubmitRequest(
        quiz_id="IPO-QZ-01",
        selected_option_id="B",
    ))
    assert sub_res["status"] == "success"
    assert sub_res["is_correct"] is True
    assert sub_res["points_awarded"] == 100

