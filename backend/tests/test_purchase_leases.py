"""
Unit tests for SQLite purchase_leases table and lease lifecycle in purchase_subscription.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import io
import uuid

import pytest
from ap2.sdk.generated.checkout_mandate import CheckoutMandate
from ap2.sdk.generated.payment_mandate import PaymentMandate
from ap2.sdk.generated.types.amount import Amount
from ap2.sdk.generated.types.merchant import Merchant
from ap2.sdk.generated.types.payment_instrument import PaymentInstrument
from ap2.sdk.mandate import MandateClient
from jwcrypto.jwk import JWK

from backend.agents.seller_agent import seller_agent
from backend.database import (
    acquire_purchase_lease,
    get_connection,
    register_buyer_key,
    release_purchase_lease,
)
from backend.services.ap2_keys import get_demo_agent_key
from backend.services.ap2_service import (
    AP2_MERCHANT_ID,
    AP2_MERCHANT_NAME,
    compute_open_payment_mandate_hash,
    create_merchant_checkout,
)
from backend.services.mandate_evaluator import ledger
from backend.services.paypal_service import paypal_service
from backend.services.trusted_surface_service import create_trusted_surface_open_mandates

SETTLED = ("ACTIVE", "APPROVAL_PENDING")


def _run(coro):
    with contextlib.redirect_stdout(io.StringIO()):
        return asyncio.run(coro)


def _lease_rows():
    conn = get_connection()
    try:
        return conn.execute("SELECT * FROM purchase_leases ORDER BY lease_key").fetchall()
    finally:
        conn.close()


def _signed_purchase(email: str, tier: str = "ap2-batch", monthly_cap: float = 500.0, ceiling: float = 1000.0):
    owner = JWK.generate(kty="EC", crv="P-256", kid=f"lease-owner-{uuid.uuid4().hex[:8]}")
    register_buyer_key(
        kid=owner.kid,
        public_key_hex=owner.export_public(),
        contractor_email=email,
        business_name="Lease Test Co",
    )
    ts = create_trusted_surface_open_mandates(
        buyer_email=email,
        monthly_budget_cap=monthly_cap,
        yearly_budget_ceiling=ceiling,
        allowed_tiers=["ap2-batch", "ap2-gateway", "ap2-cluster"],
        user_key=owner,
    )
    open_chk = ts["open_checkout_mandate_token"]
    open_pay = ts["open_payment_mandate_token"]
    price = 49.99 if tier == "ap2-batch" else 79.99
    cents = int(round(price * 100))
    rec = create_merchant_checkout(tier, price, email)
    key, mc = get_demo_agent_key(), MandateClient()
    chk = mc.present(
        holder_key=key,
        mandate_token=open_chk,
        aud=AP2_MERCHANT_ID,
        nonce=rec["nonce"],
        payloads=[
            CheckoutMandate(
                vct="mandate.checkout.1",
                checkout_jwt=rec["checkout_jwt"],
                checkout_hash=rec["checkout_hash"],
            )
        ],
    )
    pay = mc.present(
        holder_key=key,
        mandate_token=open_pay,
        aud=AP2_MERCHANT_ID,
        nonce=rec["nonce"],
        payloads=[
            PaymentMandate(
                vct="mandate.payment.1",
                transaction_id=rec["checkout_hash"],
                payment_amount=Amount(amount=cents, currency="USD"),
                payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
                payment_instrument=PaymentInstrument(type="paypal_vault", id=f"vault_{uuid.uuid4().hex[:8]}"),
            )
        ],
    )
    return {
        "offer_id": f"offer-{uuid.uuid4().hex[:12]}",
        "contractor_email": email,
        "checkout_mandate_chain": chk,
        "payment_mandate_chain": pay,
        "checkout_jwt": rec["checkout_jwt"],
        "open_pay_hash": compute_open_payment_mandate_hash(pay),
    }


def test_expired_lease_does_not_block_purchase():
    """An expired lease row inserted directly into purchase_leases does not block a purchase."""
    email = f"expired-lease-{uuid.uuid4().hex[:8]}@example.com"
    p = _signed_purchase(email)
    expired_iso = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=10)).isoformat()
    conn = get_connection()
    try:
        with conn:
            conn.execute(
                "INSERT INTO purchase_leases (lease_key, holder, expires_at) VALUES (?, ?, ?)",
                (f"mandate:{p['open_pay_hash']}", "dead-worker-holder", expired_iso),
            )
            conn.execute(
                "INSERT INTO purchase_leases (lease_key, holder, expires_at) VALUES (?, ?, ?)",
                (f"buyer:{email}", "dead-worker-holder", expired_iso),
            )
    finally:
        conn.close()

    res = _run(
        seller_agent.purchase_subscription(
            offer_id=p["offer_id"],
            contractor_email=p["contractor_email"],
            checkout_mandate_chain=p["checkout_mandate_chain"],
            payment_mandate_chain=p["payment_mandate_chain"],
            checkout_jwt=p["checkout_jwt"],
        )
    )
    assert res["status"] in SETTLED
    assert _lease_rows() == []


def test_release_purchase_lease_never_deletes_another_holders_lease():
    """Releasing with a different holder token leaves the active holder's lease intact."""
    mandate_hash = f"mh_{uuid.uuid4().hex}"
    email = f"holder-{uuid.uuid4().hex[:8]}@example.com"
    holder_a = acquire_purchase_lease(mandate_hash, email, holder="holder-A")
    assert holder_a == "holder-A"
    assert acquire_purchase_lease(mandate_hash, email, holder="holder-B") is None

    # Releasing with holder-B must delete 0 rows and leave holder-A's rows intact
    deleted_wrong = release_purchase_lease("holder-B")
    assert deleted_wrong == 0
    rows = _lease_rows()
    assert len(rows) == 2
    assert all(r["holder"] == "holder-A" for r in rows)

    # Releasing with holder-A deletes both rows
    deleted_right = release_purchase_lease("holder-A")
    assert deleted_right == 2
    assert _lease_rows() == []


def test_lease_released_on_every_post_acquisition_rejection_and_success(monkeypatch):
    """Lease rows are always cleaned up on BUDGET_EXHAUSTED, PayPal error, and normal completion."""
    email = f"release-paths-{uuid.uuid4().hex[:8]}@example.com"
    p1 = _signed_purchase(email, tier="ap2-gateway", monthly_cap=100.0, ceiling=500.0)

    # Pre-commit $60 against $100 monthly cap so a $79.99 purchase hits BUDGET_EXHAUSTED after acquiring the lease
    ledger.sync_contractor_commitment(contractor_email=email, active_monthly_rate=60.0, agent_id="agent-1")
    rej_budget = _run(
        seller_agent.purchase_subscription(
            offer_id=p1["offer_id"],
            contractor_email=p1["contractor_email"],
            checkout_mandate_chain=p1["checkout_mandate_chain"],
            payment_mandate_chain=p1["payment_mandate_chain"],
            checkout_jwt=p1["checkout_jwt"],
        )
    )
    assert rej_budget["status"] == "REJECTED"
    assert rej_budget["error"] == "BUDGET_EXHAUSTED"
    assert _lease_rows() == []

    # Reset commitment and simulate PayPal failure on p1 (retryable because receipt was cleared on rejection)
    ledger.sync_contractor_commitment(contractor_email=email, active_monthly_rate=0.0, agent_id="agent-1")
    original_create = paypal_service.create_subscription

    async def boom(**kwargs):
        raise RuntimeError("PayPal gateway down")

    monkeypatch.setattr(paypal_service, "create_subscription", boom)
    rej_paypal = _run(
        seller_agent.purchase_subscription(
            offer_id=p1["offer_id"],
            contractor_email=p1["contractor_email"],
            checkout_mandate_chain=p1["checkout_mandate_chain"],
            payment_mandate_chain=p1["payment_mandate_chain"],
            checkout_jwt=p1["checkout_jwt"],
        )
    )
    assert rej_paypal["status"] == "REJECTED"
    assert rej_paypal["error"] == "PAYPAL_SUBSCRIPTION_ERROR"
    assert _lease_rows() == []

    # Restore PayPal and verify normal completion also releases the lease
    monkeypatch.setattr(paypal_service, "create_subscription", original_create)
    ok = _run(
        seller_agent.purchase_subscription(
            offer_id=p1["offer_id"],
            contractor_email=p1["contractor_email"],
            checkout_mandate_chain=p1["checkout_mandate_chain"],
            payment_mandate_chain=p1["payment_mandate_chain"],
            checkout_jwt=p1["checkout_jwt"],
        )
    )
    assert ok["status"] in SETTLED
    assert _lease_rows() == []


def test_unverified_purchase_does_not_acquire_lease(monkeypatch):
    """A purchase with invalid mandate chains fails before acquire_purchase_lease is ever called."""
    called = {"count": 0}
    import backend.database as db_mod

    orig_acquire = db_mod.acquire_purchase_lease

    def spy_acquire(*args, **kwargs):
        called["count"] += 1
        return orig_acquire(*args, **kwargs)

    monkeypatch.setattr(db_mod, "acquire_purchase_lease", spy_acquire)

    res = _run(
        seller_agent.purchase_subscription(
            offer_id="offer-bad",
            contractor_email="unverified@example.com",
            checkout_mandate_chain="not.a.valid.jwt~",
            payment_mandate_chain="not.a.valid.jwt~",
        )
    )
    assert res["status"] == "REJECTED"
    assert called["count"] == 0
    assert _lease_rows() == []
