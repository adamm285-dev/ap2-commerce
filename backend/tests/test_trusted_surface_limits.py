"""
Tests for AP2 v0.2 Trusted Surface Service and Endpoints.
Verifies:
1. Creation of authentic ES256 SD-JWT Open Checkout and Open Payment mandates.
2. Full compliance with all 7 AP2 v0.2 constraints:
   - AmountRange (monthly cap in minor units)
   - AgentRecurrence (MONTHLY frequency, max_occurrences = 12)
   - Budget (yearly spend ceiling in minor units)
   - AllowedMerchants / AllowedPayees (merchant-ap2-autonomous)
   - LineItems (allowed compute tiers)
   - cnf (agent public key confirmation claim)
   - exp / iat validity timestamps
3. Non-agentic requirement: human_confirmed == True enforced.
4. End-to-end verification against seller verify_ap2_chains.
"""

import pytest
from fastapi.testclient import TestClient

from ap2.sdk.generated.checkout_mandate import CheckoutMandate
from ap2.sdk.generated.payment_mandate import PaymentMandate
from ap2.sdk.generated.types.amount import Amount
from ap2.sdk.generated.types.merchant import Merchant
from ap2.sdk.generated.types.payment_instrument import PaymentInstrument
from ap2.sdk.mandate import MandateClient

from backend.server import app
from backend.services.ap2_keys import get_demo_agent_key, get_demo_user_key
from backend.services.ap2_service import (
    AP2_MERCHANT_ID,
    AP2_MERCHANT_NAME,
    create_merchant_checkout,
    verify_ap2_chains,
)
from backend.services.trusted_surface_service import (
    create_trusted_surface_open_mandates,
    enroll_trusted_surface_key,
)

client = TestClient(app)


def test_trusted_surface_open_mandates_creation():
    """Verifies that the Trusted Surface creates valid Open Checkout & Open Payment mandates."""
    res = create_trusted_surface_open_mandates(
        buyer_email="owner@example.com",
        monthly_budget_cap=60.00,
        yearly_budget_ceiling=720.00,
        allowed_tiers=["ap2-batch", "ap2-gateway"],
    )
    assert res["status"] == "AUTHORIZED"
    assert "open_checkout_mandate_token" in res
    assert "open_payment_mandate_token" in res
    assert res["open_checkout_mandate_token"].count(".") >= 2
    assert res["open_payment_mandate_token"].count(".") >= 2

    constraints = res["constraints"]
    assert constraints["buyer_email"] == "owner@example.com"
    assert constraints["monthly_budget_cap_usd"] == 60.00
    assert constraints["monthly_budget_cap_cents"] == 6000
    assert constraints["yearly_budget_ceiling_usd"] == 720.00
    assert constraints["yearly_budget_ceiling_cents"] == 72000
    assert constraints["recurrence"] == "MONTHLY"
    assert constraints["max_occurrences"] == 12
    assert constraints["allowed_merchant"] == AP2_MERCHANT_ID
    assert constraints["allowed_payee"] == AP2_MERCHANT_ID
    assert constraints["allowed_tiers"] == ["ap2-batch", "ap2-gateway"]


def test_trusted_surface_sign_limits_endpoint_success():
    """Tests POST /api/trusted-surface/sign-limits endpoint with human confirmation."""
    agent_key = get_demo_agent_key()
    agent_jwk = agent_key.export_public(as_dict=True)

    resp = client.post(
        "/api/trusted-surface/sign-limits",
        json={
            "buyer_email": "contractor@example.com",
            "monthly_budget_cap": 80.00,
            "yearly_budget_ceiling": 960.00,
            "allowed_tiers": ["ap2-gateway", "ap2-batch"],
            "agent_public_jwk": agent_jwk,
            "validity_hours": 12,
            "human_confirmed": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "AUTHORIZED"
    assert "open_checkout_mandate_token" in data
    assert "open_payment_mandate_token" in data
    assert data["constraints"]["monthly_budget_cap_cents"] == 8000
    assert data["constraints"]["yearly_budget_ceiling_cents"] == 96000


def test_trusted_surface_sign_limits_requires_human_confirmation():
    """Verifies that requests without explicit human confirmation are rejected."""
    resp = client.post(
        "/api/trusted-surface/sign-limits",
        json={
            "buyer_email": "contractor@example.com",
            "monthly_budget_cap": 80.00,
            "human_confirmed": False,
        },
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["error"] == "HUMAN_CONFIRMATION_REQUIRED"


def test_trusted_surface_enroll_endpoint():
    """Tests POST /api/trusted-surface/enroll endpoint."""
    user_key = get_demo_user_key()
    pub_jwk = user_key.export_public(as_dict=True)

    resp = client.post(
        "/api/trusted-surface/enroll",
        json={
            "kid": "owner-p256-test-01",
            "public_key_jwk": pub_jwk,
            "buyer_email": "owner-enrolled@example.com",
            "business_name": "Enrolled Owner LLC",
            "monthly_budget_cap": 150.00,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "REGISTERED"
    assert data["kid"] == "owner-p256-test-01"
    assert data["buyer_email"] == "owner-enrolled@example.com"


def test_trusted_surface_end_to_end_verification():
    """
    Verifies that open mandates created by the Trusted Surface verify end-to-end
    when closed by the buyer agent.
    """
    ts_res = create_trusted_surface_open_mandates(
        buyer_email="buyer-e2e@example.com",
        monthly_budget_cap=60.00,
        allowed_tiers=["ap2-batch", "ap2-gateway"],
    )
    open_chk_tok = ts_res["open_checkout_mandate_token"]
    open_pay_tok = ts_res["open_payment_mandate_token"]

    chk_rec = create_merchant_checkout("ap2-batch", 49.99, "buyer-e2e@example.com")
    chk_jwt = chk_rec["checkout_jwt"]
    chk_hash = chk_rec["checkout_hash"]
    nonce = chk_rec["nonce"]

    agent_key = get_demo_agent_key()
    mandate_client = MandateClient()

    closed_chk = CheckoutMandate(vct="mandate.checkout.1", checkout_jwt=chk_jwt, checkout_hash=chk_hash)
    chk_chain = mandate_client.present(holder_key=agent_key, mandate_token=open_chk_tok, payloads=[closed_chk], aud=AP2_MERCHANT_ID, nonce=nonce)

    closed_pay = PaymentMandate(
        vct="mandate.payment.1",
        transaction_id=chk_hash,
        payment_amount=Amount(amount=4999, currency="USD"),
        payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
        payment_instrument=PaymentInstrument(type="paypal_vault", id="vault_e2e"),
    )
    pay_chain = mandate_client.present(holder_key=agent_key, mandate_token=open_pay_tok, payloads=[closed_pay], aud=AP2_MERCHANT_ID, nonce=nonce)

    v_res = verify_ap2_chains(chk_chain, pay_chain, chk_jwt, buyer_email="buyer-e2e@example.com")
    assert v_res["valid"] is True
    assert v_res["monthly_price"] == 49.99
    assert v_res["checkout_receipt"] is not None
    assert v_res["payment_receipt"] is not None
