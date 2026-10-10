"""
Recurring charge enforcement (month 2 onward) under AP2 v0.2 open payment mandates.

Each test makes a real agent purchase through the buyer wallet (owner key enrolled through
the challenge flow, owner-signed limits, wallet-signed chains), then feeds signed PayPal
PAYMENT.SALE.COMPLETED webhooks into /api/paypal/webhook and checks what is counted,
cancelled or suspended. Mock mode only: PayPal stop calls are recorded, never sent.
"""

import datetime
import json
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from jwcrypto.jwk import JWK

from backend.agents.seller_agent import _COMPLETED_SUBSCRIPTIONS, seller_agent
from backend.database import get_connection, get_recurring_charge, get_recurring_mandate
from backend.server import app
from backend.services.ap2_keys import get_merchant_public_jwk
from backend.services.ap2_service import compute_open_payment_mandate_hash
from backend.services.crypto_mandate import sign_es256_challenge
from backend.services.paypal_service import paypal_service
from backend.services.trusted_surface_service import (
    BILLING_CYCLE_SECONDS,
    DEFAULT_BILLING_TERM_SECONDS,
    MAX_MONTHLY_OCCURRENCES,
    create_trusted_surface_open_mandates,
)
from backend.wallet.wallet import BuyerWallet, init_agent_key

client = TestClient(app)
CYCLE_DAYS = BILLING_CYCLE_SECONDS // 86400


def _new_key(prefix: str) -> JWK:
    return JWK.generate(kty="EC", crv="P-256", kid=f"{prefix}-{uuid.uuid4().hex[:8]}")


@pytest.fixture
def stops(monkeypatch):
    """Records PayPal cancel/suspend calls instead of making them."""
    calls = []

    async def fake_stop(subscription_id, action, reason):
        calls.append((subscription_id, action, reason))
        return {"subscription_id": subscription_id, "action": action, "mock_mode": True}

    monkeypatch.setattr(paypal_service, "stop_subscription", fake_stop)
    return calls


async def _agent_purchase(tmp_path, cap=60.0, ceiling=None, term=None):
    """Owner signs limits, the wallet signs the checkout, the seller activates a subscription."""
    wdir = tmp_path / "wallet"
    agent_pub = init_agent_key(wdir)
    owner = _new_key("owner-renewal-test")
    email = f"renewal-owner-{uuid.uuid4().hex[:8]}@example.com"
    challenge = client.get("/api/agent/keys/challenge").json()["challenge"]
    enrolled = client.post("/api/agent/keys/register", json={
        "kid": owner.kid, "publicKeyJwk": owner.export_public(as_dict=True), "contractorEmail": email,
        "businessEntity": "Renewal Test Corp", "challenge": challenge,
        "challengeSignature": sign_es256_challenge(challenge, owner),
    })
    assert enrolled.status_code == 201, enrolled.text
    limits = create_trusted_surface_open_mandates(
        buyer_email=email, monthly_budget_cap=cap, yearly_budget_ceiling=ceiling,
        agent_key=JWK(**agent_pub), user_key=owner, billing_term_seconds=term,
    )
    (wdir / "merchant_public.jwk").write_text(json.dumps(get_merchant_public_jwk()), encoding="utf-8")
    (wdir / "owner_public.jwk").write_text(owner.export_public(), encoding="utf-8")
    (wdir / "owner_limits.json").write_text(json.dumps({
        "buyer_email": email,
        "open_checkout_mandate_token": limits["open_checkout_mandate_token"],
        "open_payment_mandate_token": limits["open_payment_mandate_token"],
    }), encoding="utf-8")

    nego = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="renewal-test", tier_id="ap2-gateway", monthly_budget_cap=cap,
        contractor_email=email, buyer_email=email,
    )
    signed = BuyerWallet(wdir).sign_checkout(nego["checkout_jwt"])
    purchase = await seller_agent.purchase_subscription(
        offer_id=nego["offer_id"], buyer_email=email,
        checkout_mandate_chain=signed["checkout_mandate_chain"],
        payment_mandate_chain=signed["payment_mandate_chain"],
    )
    assert purchase["status"] == "ACTIVE", purchase
    return SimpleNamespace(sub_id=purchase["subscription_id"], email=email, amount=signed["amount_cents"], limits=limits)


def _sale(sub_id, days_after=0, amount="49.99", currency="USD", sale_id=None, sign=True, billing_agreement=True):
    """Posts a signed PAYMENT.SALE.COMPLETED webhook and returns (http_status, json)."""
    charged = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days_after)
    resource = {
        "id": sale_id or f"SALE-{uuid.uuid4().hex[:10].upper()}",
        "state": "completed",
        "amount": {"total": amount, "currency": currency},
        "create_time": charged.isoformat(),
    }
    if billing_agreement:
        resource["billing_agreement_id"] = sub_id
    raw = json.dumps({"id": f"WH-{uuid.uuid4().hex}", "event_type": "PAYMENT.SALE.COMPLETED", "resource": resource})
    sig = paypal_service.generate_mock_webhook_signature(raw) if sign else "forged-signature"
    res = client.post("/api/paypal/webhook", content=raw,
                      headers={"Content-Type": "application/json", "PAYPAL-TRANSMISSION-SIG": sig})
    return res.status_code, res.json()


def _check(sub_id, **kwargs):
    code, body = _sale(sub_id, **kwargs)
    assert code == 200, body
    return body["recurring_check"]


# ── 1. The owner's mandate covers the subscription term ─────────────────────


def test_payment_mandate_covers_billing_term_while_purchase_window_stays_short():
    limits = create_trusted_surface_open_mandates(buyer_email="term@example.com", monthly_budget_cap=60.0,
                                                  user_key=_new_key("owner"), agent_key=_new_key("agent"))
    c = limits["constraints"]
    assert c["exp"] - c["iat"] == 86400  # window to start a purchase
    assert c["billing_term_exp"] - c["iat"] == DEFAULT_BILLING_TERM_SECONDS
    # Every one of the 12 monthly charges falls inside the term
    assert DEFAULT_BILLING_TERM_SECONDS >= (MAX_MONTHLY_OCCURRENCES - 1) * BILLING_CYCLE_SECONDS + BILLING_CYCLE_SECONDS
    assert c["max_occurrences"] == MAX_MONTHLY_OCCURRENCES


@pytest.mark.parametrize("bad_term", [0, -1, True, 1.5])
def test_invalid_billing_term_is_rejected(bad_term):
    with pytest.raises(ValueError):
        create_trusted_surface_open_mandates(buyer_email="term@example.com", monthly_budget_cap=60.0,
                                             user_key=_new_key("owner"), agent_key=_new_key("agent"),
                                             billing_term_seconds=bad_term)


@pytest.mark.asyncio
async def test_purchase_stores_owner_mandate_for_renewals(tmp_path):
    p = await _agent_purchase(tmp_path)
    record = get_recurring_mandate(p.sub_id)
    assert record["status"] == "ACTIVE"
    assert record["agreed_amount_cents"] == 4999 and record["currency"] == "USD"
    assert record["buyer_email"] == p.email
    assert record["mandate_hash"] == compute_open_payment_mandate_hash(p.limits["open_payment_mandate_token"])


# ── 2. Every renewal is verified and counted ────────────────────────────────


@pytest.mark.asyncio
async def test_first_sale_binds_to_purchase_and_renewals_count_down(tmp_path, stops):
    p = await _agent_purchase(tmp_path)
    first = _check(p.sub_id, days_after=0)
    assert first["outcome"] == "INITIAL" and first["action"] == "NONE"
    assert first["payments_used"] == 1 and first["payments_remaining"] == 11

    second = _check(p.sub_id, days_after=CYCLE_DAYS)
    assert second["outcome"] == "VERIFIED" and second["action"] == "NONE"
    assert second["payments_used"] == 2 and second["payments_remaining"] == 10
    assert stops == []


@pytest.mark.asyncio
async def test_duplicate_sale_is_counted_once(tmp_path, stops):
    p = await _agent_purchase(tmp_path)
    _check(p.sub_id, days_after=0)
    renewal = _check(p.sub_id, days_after=CYCLE_DAYS, sale_id="SALE-DUP-1")
    again = _check(p.sub_id, days_after=CYCLE_DAYS, sale_id="SALE-DUP-1")  # same sale, new webhook event id
    assert again["outcome"] == "ALREADY_PROCESSED"
    nxt = _check(p.sub_id, days_after=2 * CYCLE_DAYS)
    assert nxt["payments_used"] == renewal["payments_used"] + 1


# ── 3. Out-of-mandate charges stop the subscription ─────────────────────────


@pytest.mark.asyncio
async def test_twelfth_payment_cancels_before_a_thirteenth(tmp_path, stops):
    p = await _agent_purchase(tmp_path)
    _check(p.sub_id, days_after=0)
    for month in range(1, 11):
        assert _check(p.sub_id, days_after=month * CYCLE_DAYS)["action"] == "NONE"

    twelfth = _check(p.sub_id, days_after=11 * CYCLE_DAYS)
    assert twelfth["outcome"] == "VERIFIED"  # the 12th charge itself is authorized
    assert twelfth["action"] == "CANCEL" and twelfth["action_result"] == "DONE"
    assert twelfth["reason"].startswith("MANDATE_FULFILLED")
    assert twelfth["payments_remaining"] == 0
    assert stops == [(p.sub_id, "cancel", twelfth["reason"])]
    assert _COMPLETED_SUBSCRIPTIONS[p.sub_id]["status"] == "CANCELLED"
    assert get_recurring_mandate(p.sub_id)["status"] == "CANCELLED"

    # If PayPal charges anyway, the charge is flagged and the cancel is repeated
    thirteenth = _check(p.sub_id, days_after=12 * CYCLE_DAYS)
    assert thirteenth["outcome"] == "OUT_OF_MANDATE" and thirteenth["action"] == "CANCEL"
    assert thirteenth["reason"].startswith("CHARGE_AFTER_STOP")


@pytest.mark.asyncio
async def test_charge_above_owner_cap_cancels(tmp_path, stops):
    p = await _agent_purchase(tmp_path)
    _check(p.sub_id, days_after=0)
    over = _check(p.sub_id, days_after=CYCLE_DAYS, amount="79.99")
    assert over["outcome"] == "OUT_OF_MANDATE" and over["action"] == "CANCEL"
    assert "exceeds maximum" in over["reason"]
    assert stops[0][:2] == (p.sub_id, "cancel")
    assert get_recurring_charge(over["sale_id"])["status"] == "OUT_OF_MANDATE"


@pytest.mark.asyncio
async def test_price_change_within_cap_suspends_for_review(tmp_path, stops):
    p = await _agent_purchase(tmp_path)
    _check(p.sub_id, days_after=0)
    changed = _check(p.sub_id, days_after=CYCLE_DAYS, amount="55.00")
    assert changed["outcome"] == "UNVERIFIED" and changed["action"] == "SUSPEND"
    assert changed["reason"].startswith("AMOUNT_MISMATCH")
    assert stops[0][:2] == (p.sub_id, "suspend")
    assert _COMPLETED_SUBSCRIPTIONS[p.sub_id]["status"] == "SUSPENDED"


@pytest.mark.asyncio
async def test_budget_running_out_cancels_before_the_unaffordable_charge(tmp_path, stops):
    p = await _agent_purchase(tmp_path, cap=60.0, ceiling=150.0)  # three charges of 49.99 fit, a fourth does not
    _check(p.sub_id, days_after=0)
    assert _check(p.sub_id, days_after=CYCLE_DAYS)["action"] == "NONE"
    third = _check(p.sub_id, days_after=2 * CYCLE_DAYS)
    assert third["outcome"] == "VERIFIED" and third["action"] == "CANCEL"
    assert "remaining budget" in third["reason"]
    assert third["budget_used_cents"] == 3 * 4999


@pytest.mark.asyncio
async def test_mandate_shorter_than_a_month_cancels_after_first_charge(tmp_path, stops):
    p = await _agent_purchase(tmp_path, term=10 * 86400)
    first = _check(p.sub_id, days_after=0)
    assert first["outcome"] == "INITIAL" and first["action"] == "CANCEL"
    assert "expires before the next billing date" in first["reason"]


@pytest.mark.asyncio
async def test_charge_after_mandate_expiry_cancels(tmp_path, stops):
    p = await _agent_purchase(tmp_path)
    late = _check(p.sub_id, days_after=400)
    assert late["outcome"] == "OUT_OF_MANDATE" and late["action"] == "CANCEL"
    assert late["reason"].startswith("MANDATE_EXPIRED")


# ── 4. Unverifiable charges freeze the subscription ─────────────────────────


@pytest.mark.asyncio
async def test_tampered_stored_mandate_suspends(tmp_path, stops):
    p = await _agent_purchase(tmp_path)
    other = create_trusted_surface_open_mandates(buyer_email=p.email, monthly_budget_cap=500.0,
                                                 user_key=_new_key("owner"), agent_key=_new_key("agent"))
    conn = get_connection()
    with conn:
        conn.execute("UPDATE recurring_mandates SET open_payment_mandate_token = ? WHERE subscription_id = ?",
                     (other["open_payment_mandate_token"], p.sub_id))
    conn.close()
    result = _check(p.sub_id, days_after=0)
    assert result["outcome"] == "UNVERIFIED" and result["action"] == "SUSPEND"
    assert result["reason"].startswith("MANDATE_HASH_MISMATCH")


@pytest.mark.asyncio
async def test_mandate_from_unregistered_key_suspends(tmp_path, stops):
    p = await _agent_purchase(tmp_path)
    forged = create_trusted_surface_open_mandates(buyer_email=p.email, monthly_budget_cap=500.0,
                                                  user_key=_new_key("attacker"), agent_key=_new_key("agent"))
    token = forged["open_payment_mandate_token"]
    conn = get_connection()
    with conn:
        conn.execute("UPDATE recurring_mandates SET open_payment_mandate_token = ?, mandate_hash = ? WHERE subscription_id = ?",
                     (token, compute_open_payment_mandate_hash(token), p.sub_id))
    conn.close()
    result = _check(p.sub_id, days_after=0)
    assert result["outcome"] == "UNVERIFIED" and result["action"] == "SUSPEND"
    assert result["reason"].startswith("MANDATE_SIGNATURE_INVALID")


@pytest.mark.asyncio
async def test_mandate_rebound_to_another_email_suspends(tmp_path, stops):
    p = await _agent_purchase(tmp_path)
    conn = get_connection()
    with conn:
        conn.execute("UPDATE recurring_mandates SET buyer_email = ? WHERE subscription_id = ?",
                     ("someone-else@example.com", p.sub_id))
    conn.close()
    result = _check(p.sub_id, days_after=0)
    assert result["outcome"] == "UNVERIFIED" and result["action"] == "SUSPEND"
    assert "EMAIL_KEY_BINDING_MISMATCH" in result["reason"]


@pytest.mark.asyncio
async def test_agent_subscription_without_stored_mandate_suspends(tmp_path, stops):
    p = await _agent_purchase(tmp_path)
    conn = get_connection()
    with conn:
        conn.execute("DELETE FROM recurring_mandates WHERE subscription_id = ?", (p.sub_id,))
    conn.close()
    result = _check(p.sub_id, days_after=CYCLE_DAYS)
    assert result["outcome"] == "UNVERIFIED" and result["action"] == "SUSPEND"
    assert result["reason"].startswith("NO_MANDATE_ON_FILE")


@pytest.mark.asyncio
async def test_inexact_amount_suspends(tmp_path, stops):
    p = await _agent_purchase(tmp_path)
    result = _check(p.sub_id, days_after=0, amount="49.999")
    assert result["outcome"] == "UNVERIFIED" and result["action"] == "SUSPEND"
    assert result["reason"].startswith("MALFORMED_AMOUNT")


@pytest.mark.asyncio
async def test_failed_paypal_stop_is_recorded_and_retried(tmp_path, monkeypatch):
    p = await _agent_purchase(tmp_path)

    async def failing_stop(subscription_id, action, reason):
        raise RuntimeError("PayPal unavailable")

    monkeypatch.setattr(paypal_service, "stop_subscription", failing_stop)
    _check(p.sub_id, days_after=0)
    over = _check(p.sub_id, days_after=CYCLE_DAYS, amount="79.99")
    assert over["action"] == "CANCEL" and over["action_result"] == "FAILED"
    assert get_recurring_mandate(p.sub_id)["status"] == "STOP_FAILED"
    retry = _check(p.sub_id, days_after=2 * CYCLE_DAYS)
    assert retry["outcome"] == "OUT_OF_MANDATE" and retry["reason"].startswith("CHARGE_AFTER_STOP")


# ── 5. What is not checked, and what is rejected before checking ────────────


def test_unsigned_webhook_is_rejected_before_any_lookup(stops):
    code, _ = _sale("I-ANY", sale_id="SALE-FORGED-1", sign=False)
    assert code == 400
    assert get_recurring_charge("SALE-FORGED-1") is None
    assert stops == []


def test_human_approved_subscription_is_not_checked(stops):
    result = _check("I-HUMAN-CHECKOUT-01", days_after=0)
    assert result["outcome"] == "IGNORED" and result["reason"] == "NOT_AGENT_MANDATED"
    assert stops == []


def test_sale_without_subscription_is_ignored(stops):
    result = _check(None, billing_agreement=False)
    assert result["outcome"] == "IGNORED" and result["reason"] == "NOT_A_SUBSCRIPTION_SALE"
    assert stops == []
