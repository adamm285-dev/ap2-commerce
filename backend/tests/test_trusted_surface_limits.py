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
from jwcrypto.jwk import JWK

from ap2.sdk.generated.checkout_mandate import CheckoutMandate
from ap2.sdk.generated.payment_mandate import PaymentMandate
from ap2.sdk.generated.types.amount import Amount
from ap2.sdk.generated.types.merchant import Merchant
from ap2.sdk.generated.types.payment_instrument import PaymentInstrument
from ap2.sdk.mandate import MandateClient

from backend.config import settings
from backend.database import (
    get_buyer_key,
    get_open_mandate_settlement_totals,
    record_open_mandate_settlement,
)
from backend.server import app
from backend.services.ap2_keys import get_demo_agent_key, get_demo_user_key
from backend.services.ap2_service import (
    AP2_MERCHANT_ID,
    AP2_MERCHANT_NAME,
    compute_open_payment_mandate_hash,
    create_merchant_checkout,
    verify_ap2_chains,
)
from backend.services.crypto_mandate import sign_es256_challenge
from backend.services.trusted_surface_service import (
    create_trusted_surface_open_mandates,
)
from backend.agents.seller_agent import seller_agent

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


def test_attack_enroll_without_valid_challenge_rejected():
    """
    Verifies that open enrollment routes are removed (404),
    and registering without a valid challenge is rejected.
    """
    # 1. Old unauthenticated enrollment endpoints return 404
    assert client.post("/api/trusted-surface/enroll", json={}).status_code == 404
    assert client.post("/api/agent/trusted-surface/enroll", json={}).status_code == 404

    attacker_key = JWK.generate(kty="EC", crv="P-256", kid="attacker-p256-01")
    attacker_pub = attacker_key.export_public(as_dict=True)

    # 2. Registering with an unissued challenge returns 400
    res_fake = client.post(
        "/api/agent/keys/register",
        json={
            "kid": "attacker-p256-01",
            "publicKeyJwk": attacker_pub,
            "contractorEmail": "attacker@example.com",
            "businessEntity": "Attacker Systems LLC",
            "challenge": "fake-challenge-" + "a" * 50,
            "challengeSignature": "00" * 64,
        },
    )
    assert res_fake.status_code == 400

    # 3. Registering with a valid challenge but forged/invalid signature returns 401
    chal = client.get("/api/agent/keys/challenge").json()["challenge"]
    res_bad_sig = client.post(
        "/api/agent/keys/register",
        json={
            "kid": "attacker-p256-01",
            "publicKeyJwk": attacker_pub,
            "contractorEmail": "attacker@example.com",
            "businessEntity": "Attacker Systems LLC",
            "challenge": chal,
            "challengeSignature": "00" * 64,
        },
    )
    assert res_bad_sig.status_code == 401


def test_attack_duplicate_kid_registration_returns_409():
    """
    Verifies that attempting to re-register an existing kid returns 409 Conflict,
    and the original registered key is never overwritten.
    """
    victim_kid = "owner-p256-victim-key"
    victim_email = "victim@example.com"
    victim_key = JWK.generate(kty="EC", crv="P-256", kid=victim_kid)
    victim_pub = victim_key.export_public(as_dict=True)

    # 1. Legitimate owner registers key
    chal1 = client.get("/api/agent/keys/challenge").json()["challenge"]
    sig1 = sign_es256_challenge(chal1, victim_key)
    res1 = client.post(
        "/api/agent/keys/register",
        json={
            "kid": victim_kid,
            "publicKeyJwk": victim_pub,
            "contractorEmail": victim_email,
            "businessEntity": "Victim Autonomous Inc",
            "challenge": chal1,
            "challengeSignature": sig1,
        },
    )
    assert res1.status_code == 201

    # 2. Attacker attempts to overwrite the victim's kid with attacker key
    attacker_key = JWK.generate(kty="EC", crv="P-256", kid=victim_kid)
    attacker_pub = attacker_key.export_public(as_dict=True)
    chal2 = client.get("/api/agent/keys/challenge").json()["challenge"]
    sig2 = sign_es256_challenge(chal2, attacker_key)

    res2 = client.post(
        "/api/agent/keys/register",
        json={
            "kid": victim_kid,
            "publicKeyJwk": attacker_pub,
            "contractorEmail": "attacker@example.com",
            "businessEntity": "Attacker Systems LLC",
            "challenge": chal2,
            "challengeSignature": sig2,
        },
    )
    assert res2.status_code == 409
    assert "KEY_ALREADY_EXISTS" in res2.json()["detail"]["error"]

    # 3. Invariant: Original owner's public key remains unaltered in persistent registry
    stored_raw = get_buyer_key(victim_kid)
    assert victim_pub["x"] in stored_raw
    assert attacker_pub["x"] not in stored_raw


def test_trusted_surface_sign_limits_disabled_outside_mock_mode(monkeypatch):
    """Verifies POST /api/trusted-surface/sign-limits returns 404 when mock mode is disabled."""
    monkeypatch.setattr(settings, "mock_external_apis", False)
    resp = client.post(
        "/api/trusted-surface/sign-limits",
        json={
            "buyer_email": "real-buyer@example.com",
            "monthly_budget_cap": 80.00,
            "human_confirmed": True,
        },
    )
    assert resp.status_code == 404


def test_enforce_agent_recurrence_13th_payment_rejected():
    """
    Verifies that when AgentRecurrence specifies max_occurrences = 12,
    the 13th settlement attempt is rejected with ERR_UNRESOLVED_CONSTRAINT.
    """
    ts_res = create_trusted_surface_open_mandates(
        buyer_email="recurrence@example.com",
        monthly_budget_cap=60.00,
        yearly_budget_ceiling=1200.00,
        allowed_tiers=["ap2-batch"],
    )
    open_chk_tok = ts_res["open_checkout_mandate_token"]
    open_pay_tok = ts_res["open_payment_mandate_token"]
    open_pay_hash = compute_open_payment_mandate_hash(open_pay_tok)

    # Simulate 12 prior settled subscription payments (total_uses = 12)
    for i in range(12):
        record_open_mandate_settlement(open_pay_hash, f"sub-prior-{i}", 4999)

    tot_amt, tot_uses = get_open_mandate_settlement_totals(open_pay_hash)
    assert tot_uses == 12

    # Attempt 13th settlement
    chk_rec = create_merchant_checkout("ap2-batch", 49.99, "recurrence@example.com")
    agent_key = get_demo_agent_key()
    mandate_client = MandateClient()

    closed_chk = CheckoutMandate(vct="mandate.checkout.1", checkout_jwt=chk_rec["checkout_jwt"], checkout_hash=chk_rec["checkout_hash"])
    chk_chain = mandate_client.present(holder_key=agent_key, mandate_token=open_chk_tok, payloads=[closed_chk], aud=AP2_MERCHANT_ID, nonce=chk_rec["nonce"])

    closed_pay = PaymentMandate(
        vct="mandate.payment.1",
        transaction_id=chk_rec["checkout_hash"],
        payment_amount=Amount(amount=4999, currency="USD"),
        payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
        payment_instrument=PaymentInstrument(type="paypal_vault", id="vault_recurrence"),
    )
    pay_chain = mandate_client.present(holder_key=agent_key, mandate_token=open_pay_tok, payloads=[closed_pay], aud=AP2_MERCHANT_ID, nonce=chk_rec["nonce"])

    v_res = verify_ap2_chains(chk_chain, pay_chain, chk_rec["checkout_jwt"], buyer_email="recurrence@example.com")
    assert v_res["valid"] is False
    assert v_res["error"] in ("invalid_mandate", "unresolved_constraint")
    assert "recurrence" in v_res.get("error_description", "").lower() or "occurrences" in v_res.get("error_description", "").lower()


def test_enforce_budget_exceeded_rejected():
    """
    Verifies that when cumulative spend exceeds the open payment mandate's Budget.max ceiling,
    the purchase is rejected with ERR_UNRESOLVED_CONSTRAINT.
    """
    ts_res = create_trusted_surface_open_mandates(
        buyer_email="budget-ceiling@example.com",
        monthly_budget_cap=60.00,
        yearly_budget_ceiling=100.00,  # $100.00 yearly ceiling (10,000 cents)
        allowed_tiers=["ap2-batch"],
    )
    open_chk_tok = ts_res["open_checkout_mandate_token"]
    open_pay_tok = ts_res["open_payment_mandate_token"]
    open_pay_hash = compute_open_payment_mandate_hash(open_pay_tok)

    # Prior spend of $70.00 (7,000 cents)
    record_open_mandate_settlement(open_pay_hash, "sub-prior-spend-01", 7000)

    # Attempt new purchase of $49.99 (4,999 cents) -> Total would be 11,999 cents > 10,000 cents
    chk_rec = create_merchant_checkout("ap2-batch", 49.99, "budget-ceiling@example.com")
    agent_key = get_demo_agent_key()
    mandate_client = MandateClient()

    closed_chk = CheckoutMandate(vct="mandate.checkout.1", checkout_jwt=chk_rec["checkout_jwt"], checkout_hash=chk_rec["checkout_hash"])
    chk_chain = mandate_client.present(holder_key=agent_key, mandate_token=open_chk_tok, payloads=[closed_chk], aud=AP2_MERCHANT_ID, nonce=chk_rec["nonce"])

    closed_pay = PaymentMandate(
        vct="mandate.payment.1",
        transaction_id=chk_rec["checkout_hash"],
        payment_amount=Amount(amount=4999, currency="USD"),
        payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
        payment_instrument=PaymentInstrument(type="paypal_vault", id="vault_budget"),
    )
    pay_chain = mandate_client.present(holder_key=agent_key, mandate_token=open_pay_tok, payloads=[closed_pay], aud=AP2_MERCHANT_ID, nonce=chk_rec["nonce"])

    v_res = verify_ap2_chains(chk_chain, pay_chain, chk_rec["checkout_jwt"], buyer_email="budget-ceiling@example.com")
    assert v_res["valid"] is False
    assert v_res["error"] in ("invalid_mandate", "unresolved_constraint")
    assert "budget" in v_res.get("error_description", "").lower()


@pytest.mark.asyncio
async def test_idempotent_replay_does_not_increment_settlement():
    """
    Verifies that replaying an identical purchase returns the existing subscription
    and does NOT increment the open mandate's recorded settlement usage or cumulative spend.
    """
    ts_res = create_trusted_surface_open_mandates(
        buyer_email="replay-settle@example.com",
        monthly_budget_cap=60.00,
        allowed_tiers=["ap2-batch"],
    )
    open_chk_tok = ts_res["open_checkout_mandate_token"]
    open_pay_tok = ts_res["open_payment_mandate_token"]
    open_pay_hash = compute_open_payment_mandate_hash(open_pay_tok)

    chk_rec = create_merchant_checkout("ap2-batch", 49.99, "replay-settle@example.com")
    agent_key = get_demo_agent_key()
    mandate_client = MandateClient()

    closed_chk = CheckoutMandate(vct="mandate.checkout.1", checkout_jwt=chk_rec["checkout_jwt"], checkout_hash=chk_rec["checkout_hash"])
    chk_chain = mandate_client.present(holder_key=agent_key, mandate_token=open_chk_tok, payloads=[closed_chk], aud=AP2_MERCHANT_ID, nonce=chk_rec["nonce"])

    closed_pay = PaymentMandate(
        vct="mandate.payment.1",
        transaction_id=chk_rec["checkout_hash"],
        payment_amount=Amount(amount=4999, currency="USD"),
        payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
        payment_instrument=PaymentInstrument(type="paypal_vault", id="vault_replay"),
    )
    pay_chain = mandate_client.present(holder_key=agent_key, mandate_token=open_pay_tok, payloads=[closed_pay], aud=AP2_MERCHANT_ID, nonce=chk_rec["nonce"])

    offer_id = chk_rec["checkout_hash"][:16]

    # Initial purchase
    res1 = await seller_agent.purchase_subscription(
        offer_id=offer_id,
        contractor_email="replay-settle@example.com",
        checkout_mandate_chain=chk_chain,
        payment_mandate_chain=pay_chain,
        checkout_jwt=chk_rec["checkout_jwt"],
    )
    assert res1["status"] in ("ACTIVE", "APPROVAL_PENDING")
    sub_id = res1["subscription_id"]

    tot_amt1, tot_uses1 = get_open_mandate_settlement_totals(open_pay_hash)
    assert tot_uses1 == 1
    assert tot_amt1 == 4999

    # Replay identical purchase
    res2 = await seller_agent.purchase_subscription(
        offer_id=offer_id,
        contractor_email="replay-settle@example.com",
        checkout_mandate_chain=chk_chain,
        payment_mandate_chain=pay_chain,
        checkout_jwt=chk_rec["checkout_jwt"],
    )
    assert res2["status"] in ("ACTIVE", "APPROVAL_PENDING")
    assert res2["subscription_id"] == sub_id

    # Usage and amount MUST NOT increase
    tot_amt2, tot_uses2 = get_open_mandate_settlement_totals(open_pay_hash)
    assert tot_uses2 == 1
    assert tot_amt2 == 4999


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


@pytest.mark.asyncio
async def test_identifier_only_replay_rejected_with_zero_record_fields():
    """
    Verifies that calling purchase_subscription with only an identifier (mandate_proof_hash or offer_id)
    and no valid chains or matching authorized legacy proof is strictly rejected without returning
    any cached subscription record fields (subscription_id, payment_token, vault_id, payer_id, buyer_email).
    """
    email = "ident-only@example.com"
    ts_res = create_trusted_surface_open_mandates(
        buyer_email=email,
        monthly_budget_cap=60.00,
        allowed_tiers=["ap2-batch"],
    )
    chk_rec = create_merchant_checkout("ap2-batch", 49.99, email)
    agent_key = get_demo_agent_key()
    mandate_client = MandateClient()

    closed_chk = CheckoutMandate(vct="mandate.checkout.1", checkout_jwt=chk_rec["checkout_jwt"], checkout_hash=chk_rec["checkout_hash"])
    chk_chain = mandate_client.present(holder_key=agent_key, mandate_token=ts_res["open_checkout_mandate_token"], payloads=[closed_chk], aud=AP2_MERCHANT_ID, nonce=chk_rec["nonce"])

    closed_pay = PaymentMandate(
        vct="mandate.payment.1",
        transaction_id=chk_rec["checkout_hash"],
        payment_amount=Amount(amount=4999, currency="USD"),
        payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
        payment_instrument=PaymentInstrument(type="paypal_vault", id="vault_ident"),
    )
    pay_chain = mandate_client.present(holder_key=agent_key, mandate_token=ts_res["open_payment_mandate_token"], payloads=[closed_pay], aud=AP2_MERCHANT_ID, nonce=chk_rec["nonce"])

    # Legitimate first purchase
    first = await seller_agent.purchase_subscription(
        offer_id=chk_rec["checkout_hash"][:16],
        contractor_email=email,
        checkout_mandate_chain=chk_chain,
        payment_mandate_chain=pay_chain,
        checkout_jwt=chk_rec["checkout_jwt"],
    )
    assert first["status"] in ("ACTIVE", "APPROVAL_PENDING")

    # Attacker attempts replay carrying only the checkout hash / proof hash with zero chains
    attacker_res = await seller_agent.purchase_subscription(
        mandate_proof_hash=chk_rec["checkout_hash"],
    )
    assert attacker_res["status"] == "REJECTED"
    for field in ("subscription_id", "payment_token", "vault_id", "payer_id", "buyer_email"):
        assert field not in attacker_res


@pytest.mark.asyncio
@pytest.mark.parametrize("tier_id,price", [
    ("ap2-batch", 49.99),
    ("ap2-gateway", 79.99),
    ("ap2-cluster", 179.99),
])
async def test_twelve_payments_succeed_and_thirteenth_fails_all_three_tiers(tier_id, price):
    """
    Verifies that the default yearly budget ceiling (integer cents = monthly_cap * 12)
    allows exactly 12 payments for all three tiers ($49.99, $79.99, $179.99), and rejects
    the 13th payment with error code 'invalid_mandate'.
    """
    email = f"recur-{tier_id}@example.com"
    ts_res = create_trusted_surface_open_mandates(
        buyer_email=email,
        monthly_budget_cap=price,
        allowed_tiers=[tier_id],
    )
    open_chk_tok = ts_res["open_checkout_mandate_token"]
    open_pay_tok = ts_res["open_payment_mandate_token"]
    agent_key = get_demo_agent_key()
    mandate_client = MandateClient()
    price_cents = int(round(price * 100))

    results = []
    for i in range(13):
        chk_rec = create_merchant_checkout(tier_id, price, email)
        closed_chk = CheckoutMandate(vct="mandate.checkout.1", checkout_jwt=chk_rec["checkout_jwt"], checkout_hash=chk_rec["checkout_hash"])
        chk_chain = mandate_client.present(holder_key=agent_key, mandate_token=open_chk_tok, payloads=[closed_chk], aud=AP2_MERCHANT_ID, nonce=chk_rec["nonce"])

        closed_pay = PaymentMandate(
            vct="mandate.payment.1",
            transaction_id=chk_rec["checkout_hash"],
            payment_amount=Amount(amount=price_cents, currency="USD"),
            payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
            payment_instrument=PaymentInstrument(type="paypal_vault", id=f"vault_rec_{i}"),
        )
        pay_chain = mandate_client.present(holder_key=agent_key, mandate_token=open_pay_tok, payloads=[closed_pay], aud=AP2_MERCHANT_ID, nonce=chk_rec["nonce"])

        res = await seller_agent.purchase_subscription(
            tier_id=tier_id,
            agreed_monthly_rate=price,
            checkout_mandate_chain=chk_chain,
            payment_mandate_chain=pay_chain,
            checkout_jwt=chk_rec["checkout_jwt"],
            buyer_email=email,
            nonce=chk_rec["nonce"],
        )
        results.append(res)

    assert [r.get("status") in ("ACTIVE", "APPROVAL_PENDING") for r in results[:12]] == [True] * 12
    assert results[12].get("status") == "REJECTED"
    assert results[12].get("error") == "invalid_mandate"
