"""
Package 6 hardening verification tests.

Verifies:
1. Fresh database shows an empty fleet (count 0, transactions [], simulated_fleet_notice present).
2. Direct charge cannot come back CAPTURED without a capture ID PayPal issued:
   - In live mode (mock_mode=False) without credentials/capture, raises and fails closed.
   - In mock mode (mock_mode=True), calls capture_direct_payment and settles under M-002.
3. provision_compute_node refuses with LIVE_PROVISIONING_NOT_CONFIGURED in live mode (mock_external_apis=False)
   so the tool result does not claim PROVISIONED for compute that was not deployed.
4. Quote (/api/agent/quote) and lock-slot (/api/agent/dispatch/lock-slot) are not described as
   compute pricing or as a verified deposit.
"""

import pytest
from fastapi.testclient import TestClient
from ..server import app
from ..config import settings
from ..services.paypal_service import paypal_service
from ..services.ap2_gateway_service import Ap2GatewayService
from ..agents.seller_agent import seller_agent, _COMPLETED_SUBSCRIPTIONS
from ..database import (
    get_fleet_ledger,
    get_fleet_stats,
    get_fleet_schedule,
    seed_fleet_subscriptions_if_empty,
    save_subscription,
    register_vault_payment_source,
    register_buyer_key,
    get_connection,
)

client = TestClient(app)


def test_package6_fresh_database_shows_empty_fleet():
    """Done when: a fresh database shows an empty fleet."""
    # 1. GET /api/fleet/ledger returns count 0, empty list, and simulated_fleet_notice
    resp = client.get("/api/fleet/ledger")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["transactions"] == []
    assert "simulated_fleet_notice" in data
    assert len(data["simulated_fleet_notice"]) > 0

    # 2. Directly calling get_fleet_ledger returns []
    assert get_fleet_ledger() == []

    # 3. Fleet stats report 0 active lines and 0 MRR
    stats_resp = client.get("/api/fleet/stats")
    assert stats_resp.status_code == 200
    stats = stats_resp.json()
    assert stats["total_subscribers"] == 0
    assert stats["active_lines"] == 0
    assert stats["total_mrr"] == 0.0

    # 4. Schedule reports empty resources
    sched_resp = client.get("/api/fleet/schedule")
    assert sched_resp.status_code == 200
    sched = sched_resp.json()
    assert sched["resources"] == []


def test_package6_live_provision_refuses_undeployed_compute(monkeypatch):
    """provision_compute_node must not return PROVISIONED in live mode when nothing is deployed."""
    # Set up an active subscription in database
    sub_id = "I-SUB-ACTIVE-TEST"
    email = "live-buyer@example.com"
    save_subscription({
        "subscription_id": sub_id,
        "status": "ACTIVE",
        "contractor_email": email,
        "tier_id": "ap2-gateway",
        "agreed_monthly_rate": 79.99,
        "subscriber_country_code": "US",
    })
    _COMPLETED_SUBSCRIPTIONS[sub_id] = {
        "subscription_id": sub_id,
        "status": "ACTIVE",
        "contractor_email": email,
        "tier_id": "ap2-gateway",
        "agreed_monthly_rate": 79.99,
        "subscriber_country_code": "US",
    }

    # In mock mode, returns PROVISIONED under M-010
    monkeypatch.setattr(settings, "mock_external_apis", True)
    import asyncio
    prov_mock = asyncio.run(seller_agent.provision_compute_node(
        subscription_id=sub_id,
        buyer_email=email,
    ))
    assert prov_mock["status"] == "PROVISIONED"

    # In live mode (mock_external_apis=False), refuses with LIVE_PROVISIONING_NOT_CONFIGURED
    monkeypatch.setattr(settings, "mock_external_apis", False)
    prov_live = asyncio.run(seller_agent.provision_compute_node(
        subscription_id=sub_id,
        buyer_email=email,
    ))
    assert prov_live["status"] == "REJECTED"
    assert prov_live["error"] == "LIVE_PROVISIONING_NOT_CONFIGURED"
    assert "Live autonomous compute node deployment is not configured" in prov_live["reason"]


def test_package6_direct_charge_cannot_be_captured_without_paypal_issued_id(monkeypatch):
    """
    Done when: a direct charge cannot come back CAPTURED without a capture id PayPal issued.
    In live mode without PayPal credentials, direct payment capture fails closed.
    """
    # In live mode (mock_mode=False) with no PayPal credentials / token:
    monkeypatch.setattr(paypal_service, "mock_mode", False)
    monkeypatch.setattr(paypal_service, "get_sync_access_token", lambda *a, **k: None)

    # Calling capture_direct_payment raises RuntimeError
    with pytest.raises(RuntimeError) as exc_info:
        paypal_service.capture_direct_payment(
            payment_source_id="vault_tok_test",
            amount_cents=5000,
            currency="USD",
        )
    assert "LIVE_PAYPAL_NOT_CONFIGURED" in str(exc_info.value)


def test_package6_direct_charge_mock_mode_delegates_to_paypal_service(monkeypatch):
    """In mock mode, capture_direct_payment simulates capture under M-002."""
    monkeypatch.setattr(paypal_service, "mock_mode", True)
    res = paypal_service.capture_direct_payment(
        payment_source_id="vault_tok_test_mock",
        amount_cents=4999,
        currency="USD",
    )
    assert res["status"] == "COMPLETED"
    assert res["capture_id"].startswith("CAP-")
    assert res["amount_cents"] == 4999
    assert res["mock_mode"] is True


def test_package6_quote_and_lock_slot_not_described_as_compute_or_verified_deposit():
    """Quote and lock-slot must not be described as compute pricing or as a verified deposit."""
    from ..server import calculate_trade_quote, lock_dispatch_slot
    from ..models import QuoteResponse, DispatchLockResponse

    quote_doc = calculate_trade_quote.__doc__ or ""
    lock_doc = lock_dispatch_slot.__doc__ or ""

    # Quote must not be described as compute pricing
    assert "not compute pricing" in quote_doc.lower() or "physical trade" in quote_doc.lower()
    assert "compute pricing" not in quote_doc.lower() or "not compute pricing" in quote_doc.lower()

    # Lock slot must not be described as a verified deposit
    assert "upon verified paypal deposit" not in lock_doc.lower()
    assert "unverified deposit" in lock_doc.lower() or "unverified caller-supplied" in lock_doc.lower()
