# -*- coding: utf-8 -*-
"""Comprehensive tests for ChronosMatch Authentication, Registration, Password Hashing, and Account Isolation."""

import uuid
import pytest
from fastapi.testclient import TestClient

from api.index import app
from chronosmatch.persistence.db import db, verify_password


@pytest.fixture
def client():
    return TestClient(app)


def test_scenario_1_create_account_succeeds(client):
    """Scenario 1: Create a new account and verify registration succeeds."""
    email = f"new_trader_{uuid.uuid4().hex[:8]}@example.com"
    res = client.post("/api/virtual/register", json={
        "email": email,
        "name": "Aarav Sharma",
        "password": "SecurePassword123!",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "Account created successfully" in data["message"]
    assert data["user"]["email"] == email
    assert data["user"]["name"] == "Aarav Sharma"
    assert data["user"]["cash_balance"] == 100000.00
    # Verify password is never leaked in the response
    assert "password" not in data["user"]


def test_scenario_2_register_same_email_fails(client):
    """Scenario 2: Try registering the same email again - must display exact error message."""
    email = f"duplicate_{uuid.uuid4().hex[:8]}@example.com"
    # First registration
    res1 = client.post("/api/virtual/register", json={
        "email": email,
        "name": "First User",
        "password": "FirstPassword123",
    })
    assert res1.status_code == 200

    # Second registration with same email
    res2 = client.post("/api/virtual/register", json={
        "email": email,
        "name": "Second User",
        "password": "SecondPassword123",
    })
    assert res2.status_code == 400
    assert res2.json()["detail"] == "Account already exists. Please log in."


def test_scenario_3_login_registered_email_and_correct_password(client):
    """Scenario 3: Log in using a registered email and correct password."""
    email = f"valid_login_{uuid.uuid4().hex[:8]}@example.com"
    password = "CorrectPassword789!"
    # Register account
    client.post("/api/virtual/register", json={
        "email": email,
        "name": "Kavita Rao",
        "password": password,
    })

    # Log in
    res = client.post("/api/virtual/login", json={
        "email": email,
        "password": password,
    })
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["user"]["email"] == email
    assert data["user"]["name"] == "Kavita Rao"
    assert data["user"]["cash_balance"] == 100000.00
    assert "token" in data["user"]
    assert len(data["user"]["token"]) > 16


def test_scenario_4_login_incorrect_password(client):
    """Scenario 4: Log in using a registered email and incorrect password."""
    email = f"wrong_pwd_{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/virtual/register", json={
        "email": email,
        "name": "Security Tester",
        "password": "ActualPassword123!",
    })

    # Attempt login with wrong password
    res = client.post("/api/virtual/login", json={
        "email": email,
        "password": "WrongPassword999!",
    })
    assert res.status_code == 401
    assert res.json()["detail"] == "Incorrect password. Please try again."


def test_scenario_5_login_unregistered_email(client):
    """Scenario 5: Try logging in using an unregistered email."""
    email = f"nonexistent_{uuid.uuid4().hex[:8]}@example.com"
    res = client.post("/api/virtual/login", json={
        "email": email,
        "password": "AnyPassword123",
    })
    assert res.status_code == 404
    assert res.json()["detail"] == "Account not found. Please create an account first."


def test_scenario_6_logout_and_login_again(client):
    """Scenario 6: Log out and log in again, restoring user data."""
    email = f"logout_test_{uuid.uuid4().hex[:8]}@example.com"
    password = "MyPassword456!"
    client.post("/api/virtual/register", json={
        "email": email,
        "name": "Logout Tester",
        "password": password,
    })

    # Execute a trade to change state
    client.post("/api/virtual/trade", json={
        "email": email,
        "symbol": "RELIANCE",
        "action": "BUY",
        "order_type": "MARKET",
        "price": 1000.0,
        "quantity": 10.0,
    })

    # Call logout
    res_out = client.post("/api/virtual/logout")
    assert res_out.status_code == 200

    # Log in again
    res_in = client.post("/api/virtual/login", json={
        "email": email,
        "password": password,
    })
    assert res_in.status_code == 200
    user = res_in.json()["user"]
    assert user["email"] == email

    # Verify portfolio state was preserved and restored
    port_res = client.get(f"/api/virtual/portfolio/{email}")
    assert port_res.status_code == 200
    port = port_res.json()
    assert len(port["holdings"]) == 1
    assert port["holdings"][0]["symbol"] == "RELIANCE"
    assert port["holdings"][0]["quantity"] == 10.0


def test_scenario_7_two_accounts_remain_strictly_isolated(client):
    """Scenario 7: Create two different accounts and verify their portfolios remain separate."""
    alice_email = f"alice_{uuid.uuid4().hex[:8]}@example.com"
    bob_email = f"bob_{uuid.uuid4().hex[:8]}@example.com"

    client.post("/api/virtual/register", json={
        "email": alice_email,
        "name": "Alice Trader",
        "password": "AlicePassword123!",
    })
    client.post("/api/virtual/register", json={
        "email": bob_email,
        "name": "Bob Trader",
        "password": "BobPassword123!",
    })

    # Alice buys 10 RELIANCE at 1000 = 10,000 spent
    client.post("/api/virtual/trade", json={
        "email": alice_email,
        "symbol": "RELIANCE",
        "action": "BUY",
        "order_type": "MARKET",
        "price": 1000.0,
        "quantity": 10.0,
    })

    # Bob buys 5 TCS at 2000 = 10,000 spent
    client.post("/api/virtual/trade", json={
        "email": bob_email,
        "symbol": "TCS",
        "action": "BUY",
        "order_type": "MARKET",
        "price": 2000.0,
        "quantity": 5.0,
    })

    # Verify Alice's portfolio: has RELIANCE, NO TCS
    alice_port = client.get(f"/api/virtual/portfolio/{alice_email}").json()
    assert len(alice_port["holdings"]) == 1
    assert alice_port["holdings"][0]["symbol"] == "RELIANCE"
    assert alice_port["holdings"][0]["quantity"] == 10.0
    assert alice_port["cash_balance"] == 90000.00

    # Verify Bob's portfolio: has TCS, NO RELIANCE
    bob_port = client.get(f"/api/virtual/portfolio/{bob_email}").json()
    assert len(bob_port["holdings"]) == 1
    assert bob_port["holdings"][0]["symbol"] == "TCS"
    assert bob_port["holdings"][0]["quantity"] == 5.0
    assert bob_port["cash_balance"] == 90000.00

    # Verify orders are also isolated
    alice_orders = client.get(f"/api/virtual/orders/{alice_email}").json()
    bob_orders = client.get(f"/api/virtual/orders/{bob_email}").json()
    assert all(o["symbol"] == "RELIANCE" for o in alice_orders)
    assert all(o["symbol"] == "TCS" for o in bob_orders)


def test_scenario_8_session_recovery_and_user_profile(client):
    """Scenario 8: Verify that user profile and portfolio can be recovered without re-authenticating password."""
    email = f"profile_test_{uuid.uuid4().hex[:8]}@example.com"
    client.post("/api/virtual/register", json={
        "email": email,
        "name": "Pooja Patel",
        "password": "SecurePassword999!",
    })

    # Fetch public user profile
    res = client.get(f"/api/virtual/user/{email}")
    assert res.status_code == 200
    user_info = res.json()
    assert user_info["email"] == email
    assert user_info["name"] == "Pooja Patel"
    assert "password" not in user_info


def test_scenario_9_demo_mode_isolation(client):
    """Scenario 9: Verify demo mode remains separate from registered accounts."""
    demo_email = "demo.trader@chronos.local"
    user_email = f"real_trader_{uuid.uuid4().hex[:8]}@example.com"

    # Register real user
    client.post("/api/virtual/register", json={
        "email": user_email,
        "name": "Real User",
        "password": "RealPassword123!",
    })

    # Real user places trade
    client.post("/api/virtual/trade", json={
        "email": user_email,
        "symbol": "INFY",
        "action": "BUY",
        "order_type": "MARKET",
        "price": 1000.0,
        "quantity": 20.0,
    })

    # Demo account should not see Real User's trade
    user_port = client.get(f"/api/virtual/portfolio/{user_email}").json()
    demo_port = client.get(f"/api/virtual/portfolio/{demo_email}").json()

    assert any(h["symbol"] == "INFY" for h in user_port["holdings"])
    # Demo portfolio should not have user's INFY holding
    assert not any(h["symbol"] == "INFY" and h["quantity"] == 20.0 for h in demo_port["holdings"])


def test_security_never_store_plaintext_passwords():
    """Security Requirement 5: Passwords must be hashed using PBKDF2-HMAC-SHA256 and never stored in plaintext."""
    email = f"sec_check_{uuid.uuid4().hex[:8]}@example.com"
    raw_password = "SuperSecretPlainTextPassword123!"

    user = db.create_user(email=email, name="Hash Auditor", password=raw_password)
    assert user["email"] == email

    # Directly inspect raw SQLite database row
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT password FROM users WHERE email = ?", (email,))
        row = cursor.fetchone()
        stored_password = row["password"]

    # Must NOT be plaintext
    assert stored_password != raw_password
    # Must use secure PBKDF2 with SHA-256 and salt
    assert stored_password.startswith("pbkdf2:sha256:100000$")
    assert verify_password(raw_password, stored_password) is True
    assert verify_password("WrongPassword", stored_password) is False
