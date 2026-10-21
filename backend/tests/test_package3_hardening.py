"""
Tests for Package 3 hardening:
1. Two presentations of the same closed mandate do not create two settlements after a restart.
2. A new chain plus an old offer_id is REJECTED (OFFER_MISMATCH_DETECTED).
3. A thrown evaluate_sale leaves the webhook event ID unrecorded in processed_webhooks.
4. A refund larger than its sale does not increase remaining budget (capped at parent sale's cents),
   and a refund with no parent is not filed under unknown_hash.
5. A budget reset does not clear processed_webhooks.
6. First stored sale for a subscription is classified as INITIAL by sale identity, not a 15-day clock.
7. APPROVAL_PENDING does not write settlement before approval; ACTIVATED persists to SQLite.
"""

import datetime
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from jwcrypto.jwk import JWK

from backend.agents.seller_agent import (
    _COMPLETED_SUBSCRIPTIONS,
    seller_agent,
)
from backend.config import settings
from backend.database import (
    get_connection,
    get_open_mandate_total_usage,
    get_recurring_charge,
    get_recurring_mandate,
    get_subscription,
    record_recurring_charge,
    save_subscription,
)
from backend.services.mandate_evaluator import get_authorized_mandate
from backend.server import (
    _PROCESSED_WEBHOOK_IDS,
    app,
)
from backend.services.ap2_service import (
    _RECEIPT_STORE,
    compute_open_payment_mandate_hash,
    get_merchant_public_jwk,
    get_stored_receipt,
)
from backend.services.crypto_mandate import sign_es256_challenge
from backend.services.paypal_service import paypal_service
from backend.services.trusted_surface_service import (
    create_trusted_surface_open_mandates,
)
from backend.tests.test_recurring_mandate_renewals import (
    _agent_purchase,
    _new_key,
)
from backend.wallet.wallet import BuyerWallet, init_agent_key

client = TestClient(app)


def _post_signed_webhook(event_type: str, resource: dict, event_id: str = None) -> tuple[int, dict]:
    evt_id = event_id or f"WH-{uuid.uuid4().hex}"
    raw = json.dumps({"id": evt_id, "event_type": event_type, "resource": resource})
    sig = paypal_service.generate_mock_webhook_signature(raw)
    res = client.post(
        "/api/paypal/webhook",
        content=raw,
        headers={"Content-Type": "application/json", "PAYPAL-TRANSMISSION-SIG": sig},
    )
    return res.status_code, res.json()


@pytest.mark.asyncio
async def test_two_presentations_same_closed_mandate_do_not_create_two_settlements_after_restart(tmp_path):
    """
    Two presentations of the same closed mandate do not create two settlements after a restart.
    The first replay rejection does not erase the Success receipt marker.
    """
    p = await _agent_purchase(tmp_path, cap=100.0)

    # Find the closed mandate reference used for the checkout receipt
    db_sub = get_subscription(p.sub_id)
    assert db_sub is not None
    offer_id = db_sub["offer_id"]

    auth = get_authorized_mandate(offer_id)
    assert auth is not None
    chk_jwt = auth.get("counter_checkout_jwt") or auth.get("checkout_jwt")

    wdir = tmp_path / "wallet"
    wallet = BuyerWallet(wdir)
    signed = wallet.sign_checkout(chk_jwt)
    closed_ref = signed["checkout_hash"]

    # Verify 1 settlement was recorded
    conn = get_connection()
    try:
        cur = conn.execute("SELECT count(*) as c FROM open_mandate_settlements WHERE subscription_id = ?", (p.sub_id,))
        assert cur.fetchone()["c"] == 1
    finally:
        conn.close()

    # Verify receipt is Success
    receipt = get_stored_receipt(closed_ref)
    assert receipt is not None
    assert receipt.get("status") == "Success"

    # Simulate server restart by clearing in-memory caches (SQLite remains)
    _RECEIPT_STORE.clear()

    # In a new process / post-restart, SQLite still has the receipt
    db_rec = get_stored_receipt(closed_ref)
    assert db_rec is not None
    assert db_rec.get("status") == "Success"

    # Second presentation of same closed mandate after restart
    replay_res = await seller_agent.purchase_subscription(
        offer_id=offer_id,
        buyer_email=p.email,
        checkout_mandate_chain=signed["checkout_mandate_chain"],
        payment_mandate_chain=signed["payment_mandate_chain"],
    )

    # Verify settlements count did not increase (still exactly 1)
    conn = get_connection()
    try:
        cur = conn.execute("SELECT count(*) as c FROM open_mandate_settlements WHERE subscription_id = ?", (p.sub_id,))
        assert cur.fetchone()["c"] == 1
    finally:
        conn.close()

    # Verify receipt status is STILL Success (not overwritten by Error)
    receipt_after = get_stored_receipt(closed_ref)
    assert receipt_after is not None
    assert receipt_after.get("status") == "Success"


@pytest.mark.asyncio
async def test_new_chain_plus_old_offer_id_is_rejected(tmp_path):
    """
    A new chain plus an old offer_id is REJECTED with OFFER_MISMATCH_DETECTED.
    It does not turn off replay defense or return the old completed subscription.
    """
    # 1. Complete purchase for offer 1
    p1 = await _agent_purchase(tmp_path, cap=200.0)
    db_sub1 = get_subscription(p1.sub_id)
    old_offer_id = db_sub1["offer_id"]

    # 2. Negotiate an upgrade/second tier for the same buyer
    nego2 = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="renewal-test",
        tier_id="ap2-cluster",
        monthly_budget_cap=200.0,
        contractor_email=p1.email,
        buyer_email=p1.email,
    )
    assert nego2["status"] == "APPROVED", nego2
    wdir = tmp_path / "wallet"
    signed2 = BuyerWallet(wdir).sign_checkout(nego2["checkout_jwt"])

    # 3. Attempt to purchase by presenting new chains with the old offer_id
    res = await seller_agent.purchase_subscription(
        offer_id=old_offer_id,
        buyer_email=p1.email,
        checkout_mandate_chain=signed2["checkout_mandate_chain"],
        payment_mandate_chain=signed2["payment_mandate_chain"],
    )

    assert res["status"] == "REJECTED"
    assert res.get("error") == "OFFER_MISMATCH_DETECTED"


@pytest.mark.asyncio
async def test_thrown_evaluate_sale_leaves_event_id_unrecorded(monkeypatch):
    """
    A thrown evaluate_sale leaves the webhook event ID unrecorded in processed_webhooks,
    so that PayPal retry is not blocked as duplicate.
    """
    evt_id = f"WH-FAIL-{uuid.uuid4().hex}"

    def crashing_evaluate_sale(*args, **kwargs):
        raise RuntimeError("Simulated crash inside evaluate_sale!")

    monkeypatch.setattr("backend.server.evaluate_sale", crashing_evaluate_sale)

    resource = {
        "id": f"SALE-{uuid.uuid4().hex[:8].upper()}",
        "billing_agreement_id": "I-NONEXISTENT-CRASH",
        "amount": {"total": "79.99", "currency": "USD"},
    }

    # Webhook handler will crash during evaluate_sale
    with pytest.raises(RuntimeError, match="Simulated crash inside evaluate_sale"):
        raw = json.dumps({"id": evt_id, "event_type": "PAYMENT.SALE.COMPLETED", "resource": resource})
        sig = paypal_service.generate_mock_webhook_signature(raw)
        client.post(
            "/api/paypal/webhook",
            content=raw,
            headers={"Content-Type": "application/json", "PAYPAL-TRANSMISSION-SIG": sig},
        )

    # Event ID must NOT be recorded
    assert evt_id not in _PROCESSED_WEBHOOK_IDS

    conn = get_connection()
    try:
        cur = conn.execute("SELECT 1 FROM processed_webhooks WHERE event_id = ?", (evt_id,))
        assert cur.fetchone() is None
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_refund_larger_than_sale_does_not_increase_remaining_budget(tmp_path):
    """
    A refund larger than its sale does not increase remaining budget (capped at parent sale).
    A refund with no parent is not filed under unknown_hash.
    """
    p = await _agent_purchase(tmp_path, cap=100.0)
    mandate_hash = compute_open_payment_mandate_hash(p.limits["open_payment_mandate_token"])

    # Initial purchase settled p.amount (7999 cents)
    sale_id = f"SALE-{uuid.uuid4().hex[:8].upper()}"
    record_recurring_charge(
        sale_id=sale_id,
        subscription_id=p.sub_id,
        mandate_hash=mandate_hash,
        amount_cents=p.amount,
        currency="USD",
        status="INITIAL",
        reason="First charge",
        charged_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )

    # Post an excessive refund ($150 on a $79.99 sale)
    refund_id = f"REF-{uuid.uuid4().hex[:8].upper()}"
    code, body = _post_signed_webhook(
        "PAYMENT.SALE.REFUNDED",
        {
            "id": refund_id,
            "sale_id": sale_id,
            "billing_agreement_id": p.sub_id,
            "amount": {"total": "150.00", "currency": "USD"},
            "reason_code": "CUSTOMER_SATISFACTION",
            "create_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        },
    )
    assert code == 200, body

    # Verify the stored refund is capped at p.amount (7999 cents)
    refund_chg = get_recurring_charge(refund_id)
    assert refund_chg is not None
    assert refund_chg["status"] == "REFUNDED"
    assert refund_chg["amount_cents"] == -p.amount  # Capped at parent sale, NOT -15000

    # Total usage check
    used_cents, _ = get_open_mandate_total_usage(mandate_hash)
    # Settled cents was 7999, refund is -7999, net is 0
    assert used_cents == 0

    # Test refund with no parent is NOT recorded under unknown_hash
    orphan_refund_id = f"REF-ORPHAN-{uuid.uuid4().hex[:8].upper()}"
    code_orphan, body_orphan = _post_signed_webhook(
        "PAYMENT.SALE.REFUNDED",
        {
            "id": orphan_refund_id,
            "sale_id": "NONEXISTENT_SALE_ID",
            "billing_agreement_id": "NONEXISTENT_SUB_ID",
            "amount": {"total": "20.00", "currency": "USD"},
            "reason_code": "ORPHAN_REFUND",
            "create_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        },
    )
    assert code_orphan == 200
    orphan_chg = get_recurring_charge(orphan_refund_id)
    assert orphan_chg is None  # Not recorded in recurring_charges under unknown_hash


@pytest.mark.asyncio
async def test_budget_reset_does_not_clear_processed_webhooks():
    """
    A budget reset (POST /api/agent/spending-mandate/reset) must not clear processed_webhooks.
    """
    evt_id = f"WH-PERSIST-{uuid.uuid4().hex}"
    _PROCESSED_WEBHOOK_IDS.add(evt_id)
    assert evt_id in _PROCESSED_WEBHOOK_IDS

    # Issue a budget reset with admin key
    admin_key = settings.admin_api_key or "secret-admin-key"
    res = client.post(
        "/api/agent/spending-mandate/reset",
        headers={"X-Admin-Key": admin_key},
        json={},
    )
    assert res.status_code == 200, res.text

    # Webhook ID must STILL be present
    assert evt_id in _PROCESSED_WEBHOOK_IDS


@pytest.mark.asyncio
async def test_classify_first_stored_sale_as_initial_by_sale_identity(tmp_path):
    """
    Classify the first stored sale for that subscription as INITIAL by sale identity,
    not by a 15-day clock.
    """
    p = await _agent_purchase(tmp_path, cap=100.0)

    # First sale arrives 45 days later
    sale1_id = f"SALE-LATE-{uuid.uuid4().hex[:8].upper()}"
    code1, body1 = _post_signed_webhook(
        "PAYMENT.SALE.COMPLETED",
        {
            "id": sale1_id,
            "billing_agreement_id": p.sub_id,
            "amount": {"total": "79.99", "currency": "USD"},
            "create_time": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=45)).isoformat(),
        },
    )
    assert code1 == 200, body1
    rec1 = body1["recurring_check"]
    assert rec1["outcome"] == "INITIAL"

    # Second sale arrives after that: classified as renewal, not INITIAL
    sale2_id = f"SALE-RENEW-{uuid.uuid4().hex[:8].upper()}"
    code2, body2 = _post_signed_webhook(
        "PAYMENT.SALE.COMPLETED",
        {
            "id": sale2_id,
            "billing_agreement_id": p.sub_id,
            "amount": {"total": "79.99", "currency": "USD"},
            "create_time": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=75)).isoformat(),
        },
    )
    assert code2 == 200, body2
    rec2 = body2["recurring_check"]
    assert rec2["outcome"] in ("VERIFIED", "OUT_OF_MANDATE")
    assert rec2["outcome"] != "INITIAL"


@pytest.mark.asyncio
async def test_billing_subscription_activated_persists_to_sqlite_and_settles():
    """
    APPROVAL_PENDING does not write settlement before buyer approval.
    BILLING.SUBSCRIPTION.ACTIVATED updates SQLite, sets ACTIVE, and records settlement.
    """
    sub_id = f"I-PENDING-{uuid.uuid4().hex[:8].upper()}"
    mandate_hash = f"hash_{uuid.uuid4().hex}"
    email = "buyer-pending@example.com"

    # Save pending subscription in SQLite
    save_subscription({
        "subscription_id": sub_id,
        "status": "APPROVAL_PENDING",
        "contractor_email": email,
        "contractor_name": "Pending Buyer",
        "tier_id": "ap2-gateway",
        "agreed_monthly_rate": 79.99,
        "mandate_proof_hash": mandate_hash,
    })

    # Verify no settlement exists yet for APPROVAL_PENDING
    conn = get_connection()
    try:
        cur = conn.execute("SELECT count(*) as c FROM open_mandate_settlements WHERE subscription_id = ?", (sub_id,))
        assert cur.fetchone()["c"] == 0
    finally:
        conn.close()

    # Send BILLING.SUBSCRIPTION.ACTIVATED webhook
    code, body = _post_signed_webhook(
        "BILLING.SUBSCRIPTION.ACTIVATED",
        {"id": sub_id},
    )
    assert code == 200, body

    # Verify subscription is now ACTIVE in SQLite
    db_sub = get_subscription(sub_id)
    assert db_sub is not None
    assert db_sub["status"] == "ACTIVE"

    # Verify settlement was recorded upon activation
    conn = get_connection()
    try:
        cur = conn.execute("SELECT count(*) as c, amount_cents FROM open_mandate_settlements WHERE subscription_id = ?", (sub_id,))
        row = cur.fetchone()
        assert row["c"] == 1
        assert row["amount_cents"] == 7999
    finally:
        conn.close()
