"""
Tests for Group C Security Hardening and Follow-up Guarantees.
Validates:
- C1: purchase_subscription rejects with BUDGET_CAP_NOT_FOUND when payment mandate carries no AmountRange
- C2: authorized_mandates rows are strictly bound to tier and email, with claimed budget stored as claimed_budget_cap
- C3: no default buyer keys seeded/trusted when mock mode is off, seller key is never trusted, reserved key IDs cannot be registered
- Item 2: missing subscription tier is rejected with MISSING_TIER, builders require tier_id
- Item 3: reseller-agent is allowed and trusted via challenge flow while ap2-seller-ed25519-v1 is rejected
"""

import json
import asyncio
import io
import contextlib
import time
import uuid
import pytest
from pathlib import Path
from jwcrypto.jwk import JWK
from fastapi.testclient import TestClient

from backend.server import app
from backend.config import settings
from backend.agents.seller_agent import seller_agent
from backend.database import (
    get_connection,
    init_db,
    register_buyer_key,
    get_buyer_key,
    RESERVED_BUYER_KEY_IDS,
)
from backend.services.crypto_mandate import (
    DEFAULT_SELLER_KID,
    DEFAULT_BUYER_KID,
    DEFAULT_BUYER_PUBLIC_KEY_HEX,
    REGISTERED_BUYER_KEYS,
    is_trusted_buyer_key,
    generate_ed25519_keypair,
    sign_ed25519_message,
)
from backend.services.mandate_evaluator import (
    build_ap2_intent_mandate,
    build_buyer_intent_mandate,
    evaluate_spending_mandate,
    ledger,
)
from backend.models import SpendingMandateRequest, RecurrenceType
from backend.services.ap2_service import (
    AP2_MERCHANT_ID,
    AP2_MERCHANT_NAME,
    create_merchant_checkout,
    verify_ap2_chains,
)
from ap2.sdk.mandate import MandateClient
from ap2.sdk.generated.open_checkout_mandate import (
    OpenCheckoutMandate,
    AllowedMerchants,
    LineItems,
    LineItemRequirements,
    Item as CheckoutItem,
)
from ap2.sdk.generated.open_payment_mandate import (
    OpenPaymentMandate,
    AgentRecurrence,
    Frequency,
    Budget,
    AllowedPayees,
)
from ap2.sdk.generated.checkout_mandate import CheckoutMandate
from ap2.sdk.generated.payment_mandate import PaymentMandate
from ap2.sdk.generated.types.amount import Amount
from ap2.sdk.generated.types.merchant import Merchant
from ap2.sdk.generated.types.payment_instrument import PaymentInstrument
from backend.services.ap2_keys import jwk_to_cnf

client = TestClient(app)


def _run(coro):
    with contextlib.redirect_stdout(io.StringIO()):
        return asyncio.run(coro)


def _gen_key(prefix: str) -> JWK:
    return JWK.generate(kty="EC", crv="P-256", kid=f"{prefix}-{uuid.uuid4().hex[:8]}")


# ── C1: Verified Payment Mandate Without AmountRange Rejection ────────────

def test_purchase_rejects_when_payment_mandate_has_no_amount_range():
    """
    C1: purchase_subscription rejects with BUDGET_CAP_NOT_FOUND when the verified payment
    mandate chain carries no owner-signed price limit (no AmountRange).
    It must not fall back to the claimed budget, a contractor record, or 100.0.
    """
    email = f"hardening-c1-{uuid.uuid4().hex[:6]}@example.com"
    owner_key = _gen_key("owner")
    agent_key = _gen_key("agent")

    # Enroll owner key
    register_buyer_key(
        kid=owner_key.kid,
        public_key_hex=owner_key.export_public(),
        contractor_email=email,
        business_name="Hardening C1 Corp",
    )

    # Pre-populate contractor record in ledger to test that purchase does NOT fall back to it
    ledger.set_contractor_cap(email, 100.0, source="signed_mandate")
    assert ledger.get_saved_cap(email) == 100.0

    # Build valid open checkout mandate
    agent_cnf = jwk_to_cnf(agent_key)
    now_ts = int(time.time())
    exp_ts = now_ts + 86400
    mc = MandateClient()

    open_chk = OpenCheckoutMandate(
        vct="mandate.checkout.open.1",
        constraints=[
            AllowedMerchants(allowed=[Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME)]),
            LineItems(
                items=[
                    LineItemRequirements(
                        id="allowed_compute_tiers",
                        acceptable_items=[CheckoutItem(id="ap2-batch", title="AP2 Batch")],
                        quantity=1,
                    )
                ]
            ),
        ],
        cnf=agent_cnf,
        iat=now_ts,
        exp=exp_ts,
    )
    open_chk_tok = mc.create(issuer_key=owner_key, payloads=[open_chk])

    # Build valid open payment mandate WITHOUT AmountRange constraint
    open_pay_no_cap = OpenPaymentMandate(
        vct="mandate.payment.open.1",
        constraints=[
            AllowedPayees(allowed=[Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME)]),
        ],
        cnf=agent_cnf,
        iat=now_ts,
        exp=exp_ts + 86400 * 30,
    )
    open_pay_tok = mc.create(issuer_key=owner_key, payloads=[open_pay_no_cap])

    # Agent presents (closes) both against merchant checkout
    rec = create_merchant_checkout("ap2-batch", 49.99, email)
    chk_chain = mc.present(
        holder_key=agent_key,
        mandate_token=open_chk_tok,
        payloads=[
            CheckoutMandate(
                vct="mandate.checkout.1",
                checkout_jwt=rec["checkout_jwt"],
                checkout_hash=rec["checkout_hash"],
            )
        ],
        aud=AP2_MERCHANT_ID,
        nonce=rec["nonce"],
    )
    pay_chain = mc.present(
        holder_key=agent_key,
        mandate_token=open_pay_tok,
        payloads=[
            PaymentMandate(
                vct="mandate.payment.1",
                transaction_id=rec["checkout_hash"],
                payment_amount=Amount(amount=4999, currency="USD"),
                payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
                payment_instrument=PaymentInstrument(type="paypal_vault", id="vault-hardening-c1"),
            )
        ],
        aud=AP2_MERCHANT_ID,
        nonce=rec["nonce"],
    )


    # Call purchase_subscription - must reject with BUDGET_CAP_NOT_FOUND
    res = _run(seller_agent.purchase_subscription(
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        checkout_mandate_chain=chk_chain,
        payment_mandate_chain=pay_chain,
        checkout_jwt=rec["checkout_jwt"],
        buyer_email=email,
        nonce=rec["nonce"],
    ))
    assert res.get("status") == "REJECTED"
    assert res.get("error") == "BUDGET_CAP_NOT_FOUND"
    assert "BUDGET_CAP_NOT_FOUND" in res.get("reason", "")


# ── C2: Bounded Authorized Mandates Persistence ───────────────────────────

def test_negotiate_writes_scoped_mandates_with_claimed_cap(tmp_path):
    """
    C2: after negotiate_tier_terms, every authorized_mandates row written is bound to a
    concrete tier and buyer email: no tier_id '*', no empty contractor_email.
    The claimed budget is stored as claimed_budget_cap, not as an authorized cap.
    """
    email = f"hardening-c2-{uuid.uuid4().hex[:6]}@example.com"
    res = _run(seller_agent.negotiate_tier_terms(
        buyer_agent_id="buyer-c2",
        buyer_email=email,
        tier_id="ap2-gateway",
        monthly_budget_cap=60.0,
    ))
    assert res["status"] == "COUNTER_OFFER"
    assert res["tier_id"] == "ap2-batch"
    assert res["price"] == 49.99

    offer_id = res["offer_id"]
    proof_hash = res["mandate_proof_hash"]

    # Verify rows in database
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT lookup_key, tier_id, contractor_email, amount, monthly_budget_cap, details_json "
            "FROM authorized_mandates WHERE offer_id = ? OR lookup_key IN (?, ?)",
            (offer_id, offer_id, proof_hash),
        )
        rows = cur.fetchall()
        assert len(rows) > 0, "Expected authorized_mandates rows for negotiation"
        for row in rows:
            assert row["tier_id"] == "ap2-batch", f"Invalid tier_id: {row['tier_id']}"
            assert row["tier_id"] != "*", "Tier ID must not be wildcard '*'"
            assert row["contractor_email"] == email, f"Invalid contractor_email: {row['contractor_email']}"
            assert row["contractor_email"] is not None and row["contractor_email"] != ""
            # The stored monthly_budget_cap in DB must equal the offer price, NOT the claimed $60.00
            assert row["monthly_budget_cap"] == 49.99
            import json
            details = json.loads(row["details_json"])
            assert details.get("claimed_budget_cap") == 60.0
            assert details.get("monthly_budget_cap") == 49.99
            assert details.get("is_offer") is True
            assert details.get("status") == "PENDING_CHECKOUT"
    finally:
        conn.close()


def test_evaluate_spending_mandate_does_not_write_wildcard_or_unscoped_rows():
    """
    C2: evaluate_spending_mandate does not write rows with tier_id '*' or empty contractor_email.
    """
    req_no_email = SpendingMandateRequest(
        buyerAgentId="eval-c2-no-email",
        amount=79.99,
        monthlyBudgetCap=100.0,
        recurrence=RecurrenceType.MONTHLY,
        category="autonomous-node-service",
    )
    res_no_email = evaluate_spending_mandate(req_no_email)
    assert res_no_email.approved is True

    # Without email, no rows should be written into authorized_mandates
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM authorized_mandates WHERE buyer_agent_id = 'eval-c2-no-email'")
        assert len(cur.fetchall()) == 0

        # With email, row must have concrete tier and email
        email = "eval-c2@example.com"
        req_email = SpendingMandateRequest(
            buyerAgentId="eval-c2-with-email",
            amount=49.99,
            monthlyBudgetCap=80.0,
            recurrence=RecurrenceType.MONTHLY,
            category="autonomous-node-service",
            contractorEmail=email,
        )
        res_email = evaluate_spending_mandate(req_email)
        assert res_email.approved is True

        cur.execute("SELECT * FROM authorized_mandates WHERE buyer_agent_id = 'eval-c2-with-email'")
        rows = cur.fetchall()
        for r in rows:
            assert r["tier_id"] == "ap2-batch"
            assert r["tier_id"] != "*"
            assert r["contractor_email"] == email
    finally:
        conn.close()


# ── C3: Mock Mode Key Isolation and Reserved Key IDs ──────────────────────

def test_mock_mode_off_does_not_seed_or_trust_default_buyer_keys(tmp_path, monkeypatch):
    """
    C3: With mock mode off, no default buyer keys are seeded or trusted:
    database.py init_db and crypto_mandate.REGISTERED_BUYER_KEYS.
    """
    monkeypatch.setattr(settings, "mock_external_apis", False)

    test_db = tmp_path / "nomock_keys.db"
    init_db(test_db)

    conn = get_connection(test_db)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as cnt FROM buyer_keys")
        assert cur.fetchone()["cnt"] == 0, "Default buyer keys must not be seeded when mock mode is off"
    finally:
        conn.close()

    # is_trusted_buyer_key returns False when key is not in registered store
    assert not is_trusted_buyer_key("unseeded-agent", "some_hex_key")


def test_seller_kid_is_never_trusted_as_buyer_key():
    """
    C3: 'ap2-seller-ed25519-v1' is never trusted as a buyer key, in any mode.
    """
    assert is_trusted_buyer_key(DEFAULT_SELLER_KID, "a0" * 32) is False
    assert is_trusted_buyer_key("ap2-seller-ed25519-v1", DEFAULT_BUYER_PUBLIC_KEY_HEX) is False

    # Even if forcefully inserted into the keys map, it must still never be trusted
    REGISTERED_BUYER_KEYS[DEFAULT_SELLER_KID] = "a0" * 32
    try:
        assert is_trusted_buyer_key(DEFAULT_SELLER_KID, "a0" * 32) is False
    finally:
        REGISTERED_BUYER_KEYS.pop(DEFAULT_SELLER_KID, None)


def test_registering_reserved_kid_is_refused():
    """
    C3: Registering a reserved kid through POST /api/agent/keys/register is refused with 403.
    """
    priv, pub = generate_ed25519_keypair()
    chal_res = client.get("/api/agent/keys/challenge")
    challenge = chal_res.json()["challenge"]
    sig = sign_ed25519_message(challenge, priv)

    for reserved_kid in RESERVED_BUYER_KEY_IDS:
        res = client.post(
            "/api/agent/keys/register",
            json={
                "kid": reserved_kid,
                "publicKeyHex": pub,
                "contractorEmail": "test@example.com",
                "businessEntity": "Reserved Test LLC",
                "challenge": challenge,
                "challengeSignature": sig,
            },
        )
        assert res.status_code == 403
        assert res.json()["detail"]["error"] == "RESERVED_KEY_ID"


# ── Item 2: Missing Tier Must Fail ────────────────────────────────────────

def test_missing_tier_rejected_in_purchase_and_builders():
    """
    Item 2: A missing tier must fail rather than guessing ap2-batch.
    - Builders require tier_id with no default.
    - purchase_subscription rejects with MISSING_TIER if no tier can be determined.
    """
    # Builders raise TypeError when tier_id is missing
    with pytest.raises(TypeError):
        build_ap2_intent_mandate(
            buyer_agent_id="b1",
            amount=49.99,
            recurrence="monthly",
            category="test",
            # tier_id omitted
        )

    with pytest.raises(TypeError):
        build_buyer_intent_mandate(
            buyer_agent_id="b2",
            amount=49.99,
            recurrence="monthly",
            category="test",
            # tier_id omitted
        )

    # purchase_subscription rejection when tier cannot be determined
    email = f"notier-{uuid.uuid4().hex[:6]}@example.com"
    owner_key = _gen_key("owner")
    agent_key = _gen_key("agent")
    register_buyer_key(
        kid=owner_key.kid,
        public_key_hex=owner_key.export_public(),
        contractor_email=email,
    )

    from backend.services.trusted_surface_service import create_trusted_surface_open_mandates
    limits = create_trusted_surface_open_mandates(
        buyer_email=email,
        monthly_budget_cap=60.0,
        agent_key=agent_key,
        user_key=owner_key,
    )
    # Issue checkout without tier
    rec = create_merchant_checkout("ap2-batch", 49.99, email)
    mc = MandateClient()
    chk_chain = mc.present(
        holder_key=agent_key,
        mandate_token=limits["open_checkout_mandate_token"],
        payloads=[CheckoutMandate(vct="mandate.checkout.1", checkout_jwt=rec["checkout_jwt"], checkout_hash=rec["checkout_hash"])],
        aud=AP2_MERCHANT_ID,
        nonce=rec["nonce"],
    )
    pay_chain = mc.present(
        holder_key=agent_key,
        mandate_token=limits["open_payment_mandate_token"],
        payloads=[PaymentMandate(
            vct="mandate.payment.1",
            transaction_id=rec["checkout_hash"],
            payment_amount=Amount(amount=4999, currency="USD"),
            payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
            payment_instrument=PaymentInstrument(type="paypal_vault", id="vault-notier"),
        )],
        aud=AP2_MERCHANT_ID,
        nonce=rec["nonce"],
    )

    # 1. Calling purchase_subscription with tier_id="" resolves tier from verified checkout
    res_resolved = _run(seller_agent.purchase_subscription(
        tier_id="",  # Empty tier -> taken from verified checkout
        agreed_monthly_rate=49.99,
        checkout_mandate_chain=chk_chain,
        payment_mandate_chain=pay_chain,
        checkout_jwt=rec["checkout_jwt"],
        buyer_email=email,
        nonce=rec["nonce"],
    ))
    assert res_resolved.get("status") == "ACTIVE"
    assert res_resolved.get("tier_id") == "ap2-batch"

    # 2. When tier is missing from both explicit arg and verified checkout, reject with MISSING_TIER
    email2 = f"notier2-{uuid.uuid4().hex[:6]}@example.com"
    owner_key2 = _gen_key("owner2")
    agent_key2 = _gen_key("agent2")
    register_buyer_key(
        kid=owner_key2.kid,
        public_key_hex=owner_key2.export_public(),
        contractor_email=email2,
    )
    limits2 = create_trusted_surface_open_mandates(
        buyer_email=email2,
        monthly_budget_cap=60.0,
        agent_key=agent_key2,
        user_key=owner_key2,
    )
    rec2 = create_merchant_checkout("ap2-batch", 49.99, email2)
    chk_chain2 = mc.present(
        holder_key=agent_key2,
        mandate_token=limits2["open_checkout_mandate_token"],
        payloads=[CheckoutMandate(vct="mandate.checkout.1", checkout_jwt=rec2["checkout_jwt"], checkout_hash=rec2["checkout_hash"])],
        aud=AP2_MERCHANT_ID,
        nonce=rec2["nonce"],
    )
    pay_chain2 = mc.present(
        holder_key=agent_key2,
        mandate_token=limits2["open_payment_mandate_token"],
        payloads=[PaymentMandate(
            vct="mandate.payment.1",
            transaction_id=rec2["checkout_hash"],
            payment_amount=Amount(amount=4999, currency="USD"),
            payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
            payment_instrument=PaymentInstrument(type="paypal_vault", id="vault-notier2"),
        )],
        aud=AP2_MERCHANT_ID,
        nonce=rec2["nonce"],
    )
    from unittest.mock import patch
    with patch("backend.agents.seller_agent.verify_ap2_chains", return_value={
        "valid": True,
        "authoritative_budget_cap": 60.0,
        "monthly_price": 49.99,
        "tier_id": "",
    }):
        res_no_tier = _run(seller_agent.purchase_subscription(
            tier_id="",
            agreed_monthly_rate=49.99,
            checkout_mandate_chain=chk_chain2,
            payment_mandate_chain=pay_chain2,
            checkout_jwt=rec2["checkout_jwt"],
            buyer_email=email2,
            nonce=rec2["nonce"],
        ))
        assert res_no_tier.get("status") == "REJECTED"
        assert res_no_tier.get("error") == "MISSING_TIER"


# ── Item 3: Exact Reserved Key Check & Reseller Agent ─────────────────────

def test_reseller_agent_challenge_enrollment_and_trust():
    """
    Item 3: Only exact reserved IDs are blocked.
    A kid like 'reseller-agent' registered through challenge flow is trusted,
    while 'ap2-seller-ed25519-v1' is rejected.
    """
    priv_hex, pub_hex = generate_ed25519_keypair()
    reseller_kid = "reseller-agent"
    email = "reseller@example.com"

    # 1. Challenge issuance
    chal_res = client.get("/api/agent/keys/challenge")
    assert chal_res.status_code == 200
    challenge = chal_res.json()["challenge"]

    # 2. Challenge signature
    sig_hex = sign_ed25519_message(challenge, priv_hex)

    # 3. Registration succeeds because 'reseller-agent' is not in RESERVED_BUYER_KEY_IDS
    reg_res = client.post(
        "/api/agent/keys/register",
        json={
            "kid": reseller_kid,
            "publicKeyHex": pub_hex,
            "contractorEmail": email,
            "businessEntity": "Reseller Solutions Inc",
            "challenge": challenge,
            "challengeSignature": sig_hex,
        },
    )
    assert reg_res.status_code == 201
    assert reg_res.json()["status"] == "REGISTERED"

    # 4. 'reseller-agent' is now trusted as a buyer key
    assert is_trusted_buyer_key(reseller_kid, pub_hex) is True

    # 5. Exact reserved seller kid remains untrusted
    assert is_trusted_buyer_key(DEFAULT_SELLER_KID, pub_hex) is False


# ── Round 2 Adversarial Live-Test Regressions ─────────────────────────────

def test_tamper_rejection_does_not_burn_mandate_and_retry_succeeds():
    """
    Finding 1 & Finding 4:
    A rejected purchase (e.g. rate tampering or tier mismatch) must roll back
    the premature success receipt so that the mandate chain is not burned.
    The honest retry with the untampered parameters must succeed without REPLAY_DETECTED.
    Subsequent replay of the settled subscription returns idempotent_replay=True.
    """
    from backend.services.trusted_surface_service import create_trusted_surface_open_mandates
    email = f"tamper-retry-{uuid.uuid4().hex[:6]}@example.com"
    owner_key = _gen_key("owner-t")
    agent_key = _gen_key("agent-t")

    register_buyer_key(
        kid=owner_key.kid,
        public_key_hex=owner_key.export_public(),
        contractor_email=email,
        business_name="Adversarial Tamper Test Corp",
    )
    limits = create_trusted_surface_open_mandates(
        buyer_email=email,
        monthly_budget_cap=60.0,
        agent_key=agent_key,
        user_key=owner_key,
    )
    rec = create_merchant_checkout("ap2-batch", 49.99, email)
    mc = MandateClient()
    chk_chain = mc.present(
        holder_key=agent_key,
        mandate_token=limits["open_checkout_mandate_token"],
        payloads=[CheckoutMandate(vct="mandate.checkout.1", checkout_jwt=rec["checkout_jwt"], checkout_hash=rec["checkout_hash"])],
        aud=AP2_MERCHANT_ID,
        nonce=rec["nonce"],
    )
    pay_chain = mc.present(
        holder_key=agent_key,
        mandate_token=limits["open_payment_mandate_token"],
        payloads=[PaymentMandate(
            vct="mandate.payment.1",
            transaction_id=rec["checkout_hash"],
            payment_amount=Amount(amount=4999, currency="USD"),
            payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
            payment_instrument=PaymentInstrument(type="paypal_vault", id="vault-tamper1"),
        )],
        aud=AP2_MERCHANT_ID,
        nonce=rec["nonce"],
    )

    # 1. Tamper A: attempt to purchase with rate $0.01 instead of $49.99
    tamper_rate_res = _run(seller_agent.purchase_subscription(
        tier_id="ap2-batch",
        agreed_monthly_rate=0.01,
        checkout_mandate_chain=chk_chain,
        payment_mandate_chain=pay_chain,
        checkout_jwt=rec["checkout_jwt"],
        buyer_email=email,
        nonce=rec["nonce"],
    ))
    assert tamper_rate_res.get("status") == "REJECTED"
    assert tamper_rate_res.get("error") == "RATE_TAMPERING_DETECTED"
    assert "checkout_receipt" in tamper_rate_res
    assert tamper_rate_res["checkout_receipt"] is not None

    # 2. Honest retry with untampered rate ($49.99) using the SAME mandate
    # Must NOT fail with REPLAY_DETECTED
    honest_res = _run(seller_agent.purchase_subscription(
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        checkout_mandate_chain=chk_chain,
        payment_mandate_chain=pay_chain,
        checkout_jwt=rec["checkout_jwt"],
        buyer_email=email,
        nonce=rec["nonce"],
    ))
    assert honest_res.get("status") == "ACTIVE"
    assert honest_res.get("agreed_monthly_rate") == 49.99
    sub_id = honest_res["subscription_id"]

    # 3. Idempotent replay of already-settled subscription returns idempotent_replay=True
    replay_res = _run(seller_agent.purchase_subscription(
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        checkout_mandate_chain=chk_chain,
        payment_mandate_chain=pay_chain,
        checkout_jwt=rec["checkout_jwt"],
        buyer_email=email,
        nonce=rec["nonce"],
    ))
    assert replay_res.get("status") == "ACTIVE"
    assert replay_res.get("subscription_id") == sub_id
    assert replay_res.get("idempotent_replay") is True


def test_tier_mismatch_rejection_does_not_burn_mandate_and_retry_succeeds():
    """
    Tamper B: Mismatched tier rejection rolls back receipt so retry with matching tier succeeds.
    """
    from backend.services.trusted_surface_service import create_trusted_surface_open_mandates
    email = f"tamper-tier-{uuid.uuid4().hex[:6]}@example.com"
    owner_key = _gen_key("owner-b")
    agent_key = _gen_key("agent-b")

    register_buyer_key(
        kid=owner_key.kid,
        public_key_hex=owner_key.export_public(),
        contractor_email=email,
    )
    limits = create_trusted_surface_open_mandates(
        buyer_email=email,
        monthly_budget_cap=60.0,
        agent_key=agent_key,
        user_key=owner_key,
    )
    rec = create_merchant_checkout("ap2-batch", 49.99, email)
    mc = MandateClient()
    chk_chain = mc.present(
        holder_key=agent_key,
        mandate_token=limits["open_checkout_mandate_token"],
        payloads=[CheckoutMandate(vct="mandate.checkout.1", checkout_jwt=rec["checkout_jwt"], checkout_hash=rec["checkout_hash"])],
        aud=AP2_MERCHANT_ID,
        nonce=rec["nonce"],
    )
    pay_chain = mc.present(
        holder_key=agent_key,
        mandate_token=limits["open_payment_mandate_token"],
        payloads=[PaymentMandate(
            vct="mandate.payment.1",
            transaction_id=rec["checkout_hash"],
            payment_amount=Amount(amount=4999, currency="USD"),
            payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
            payment_instrument=PaymentInstrument(type="paypal_vault", id="vault-tamper2"),
        )],
        aud=AP2_MERCHANT_ID,
        nonce=rec["nonce"],
    )

    # Tamper B: Request tier ap2-gateway while mandate is for ap2-batch
    tamper_res = _run(seller_agent.purchase_subscription(
        tier_id="ap2-gateway",
        agreed_monthly_rate=49.99,
        checkout_mandate_chain=chk_chain,
        payment_mandate_chain=pay_chain,
        checkout_jwt=rec["checkout_jwt"],
        buyer_email=email,
        nonce=rec["nonce"],
    ))
    assert tamper_res.get("status") == "REJECTED"
    assert tamper_res.get("error") == "TIER_MISMATCH_DETECTED"

    # Retry with correct tier succeeds
    retry_res = _run(seller_agent.purchase_subscription(
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        checkout_mandate_chain=chk_chain,
        payment_mandate_chain=pay_chain,
        checkout_jwt=rec["checkout_jwt"],
        buyer_email=email,
        nonce=rec["nonce"],
    ))
    assert retry_res.get("status") == "ACTIVE"


def test_provision_node_and_dispatch_zapier_uses_subscription_record():
    """
    Finding 3 & Finding 4:
    - provision_compute_node next_action passes clean mandate_proof_hash (not full traceable_proof).
    - dispatch_zapier_mcp resolves subscription details (rate $49.99, batch endpoint) when called
      with only subscription_id, instead of falling back to $79.99 and Gateway.
    - MCP server layer _handle_mcp_request_internal also resolves subscription details properly.
    """
    from backend.services.trusted_surface_service import create_trusted_surface_open_mandates
    from backend.mcp_server import _handle_mcp_request_internal

    email = f"dispatch-test-{uuid.uuid4().hex[:6]}@example.com"
    owner_key = _gen_key("owner-d")
    agent_key = _gen_key("agent-d")

    register_buyer_key(
        kid=owner_key.kid,
        public_key_hex=owner_key.export_public(),
        contractor_email=email,
    )
    limits = create_trusted_surface_open_mandates(
        buyer_email=email,
        monthly_budget_cap=60.0,
        agent_key=agent_key,
        user_key=owner_key,
    )
    rec = create_merchant_checkout("ap2-batch", 49.99, email)
    mc = MandateClient()
    chk_chain = mc.present(
        holder_key=agent_key,
        mandate_token=limits["open_checkout_mandate_token"],
        payloads=[CheckoutMandate(vct="mandate.checkout.1", checkout_jwt=rec["checkout_jwt"], checkout_hash=rec["checkout_hash"])],
        aud=AP2_MERCHANT_ID,
        nonce=rec["nonce"],
    )
    pay_chain = mc.present(
        holder_key=agent_key,
        mandate_token=limits["open_payment_mandate_token"],
        payloads=[PaymentMandate(
            vct="mandate.payment.1",
            transaction_id=rec["checkout_hash"],
            payment_amount=Amount(amount=4999, currency="USD"),
            payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
            payment_instrument=PaymentInstrument(type="paypal_vault", id="vault-disp1"),
        )],
        aud=AP2_MERCHANT_ID,
        nonce=rec["nonce"],
    )

    purchase_res = _run(seller_agent.purchase_subscription(
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        checkout_mandate_chain=chk_chain,
        payment_mandate_chain=pay_chain,
        checkout_jwt=rec["checkout_jwt"],
        buyer_email=email,
        nonce=rec["nonce"],
    ))
    assert purchase_res["status"] == "ACTIVE"
    sub_id = purchase_res["subscription_id"]
    proof_hash = purchase_res["mandate_proof_hash"]

    # Test provision_compute_node
    prov_res = _run(seller_agent.provision_compute_node(
        subscription_id=sub_id,
        buyer_email=email,
        node_type="batch",
    ))
    assert prov_res["status"] == "PROVISIONED"
    assert "batch" in prov_res["endpoint"]

    # Verify next_action proof hash is clean (not "mandate:...|cart:...|hash:...")
    next_action_params = prov_res["next_action"]["parameters"]
    assert not next_action_params["mandate_proof_hash"].startswith("mandate:")
    assert next_action_params["mandate_proof_hash"] == proof_hash

    # Test dispatch_zapier_mcp on seller_agent with ONLY subscription_id
    disp_res = _run(seller_agent.dispatch_zapier_mcp(
        subscription_id=sub_id,
    ))
    purchase_data = disp_res["qboPayload"]["payload"]["Purchase"]
    assert purchase_data["TotalAmt"] == 49.99
    assert purchase_data["Line"][0]["Amount"] == 49.99
    assert "batch" in purchase_data["PrivateNote"]
    assert sub_id in purchase_data["PrivateNote"]
    assert proof_hash in purchase_data["PrivateNote"]

    # Test dispatch_zapier_mcp via MCP server JSON-RPC with ONLY subscription_id
    mcp_call = {
        "jsonrpc": "2.0",
        "id": 999,
        "method": "tools/call",
        "params": {
            "name": "dispatch_zapier_mcp",
            "arguments": {
                "subscription_id": sub_id,
            },
        },
    }
    mcp_resp = _run(_handle_mcp_request_internal(mcp_call))
    assert "error" not in mcp_resp
    result_data = json.loads(mcp_resp["result"]["content"][0]["text"])
    mcp_purchase = result_data["qboPayload"]["payload"]["Purchase"]
    assert mcp_purchase["TotalAmt"] == 49.99
    assert mcp_purchase["Line"][0]["Amount"] == 49.99
    assert "batch" in mcp_purchase["PrivateNote"]
    assert sub_id in mcp_purchase["PrivateNote"]
    assert proof_hash in mcp_purchase["PrivateNote"]


def test_dispatch_zapier_mcp_rejects_unknown_subscription_id():
    """
    Finding 3 hardening: Calling dispatch_zapier_mcp with an unknown subscription_id
    must reject with SUBSCRIPTION_NOT_FOUND rather than falling back to $79.99 gateway.
    """
    from backend.mcp_server import _handle_mcp_request_internal

    # 1. Direct call on seller_agent
    res = _run(seller_agent.dispatch_zapier_mcp(
        subscription_id="I-NONEXISTENT-SUB-1234",
    ))
    assert res.get("status") == "REJECTED"
    assert res.get("error") == "SUBSCRIPTION_NOT_FOUND"

    # 2. Over MCP JSON-RPC
    mcp_call = {
        "jsonrpc": "2.0",
        "id": 998,
        "method": "tools/call",
        "params": {
            "name": "dispatch_zapier_mcp",
            "arguments": {
                "subscription_id": "I-NONEXISTENT-SUB-5678",
            },
        },
    }
    mcp_resp = _run(_handle_mcp_request_internal(mcp_call))
    result_data = json.loads(mcp_resp["result"]["content"][0]["text"])
    assert result_data.get("status") == "REJECTED"
    assert result_data.get("error") == "SUBSCRIPTION_NOT_FOUND"


def test_bind_mandate_email_does_not_run_on_budget_exhaustion():
    """
    Item 5: If a purchase is rejected for BUDGET_EXHAUSTED, bind_mandate_email
    must not have executed, leaving no side effect on the mandate.
    """
    from backend.database import get_mandate, save_mandate
    from backend.services.trusted_surface_service import create_trusted_surface_open_mandates

    email_unbound = f"unbound-{uuid.uuid4().hex[:6]}@example.com"
    owner_key = _gen_key("owner-unbound")
    agent_key = _gen_key("agent-unbound")

    register_buyer_key(
        kid=owner_key.kid,
        public_key_hex=owner_key.export_public(),
        contractor_email=email_unbound,
    )
    from backend.services.mandate_evaluator import ledger
    # Owner cap is $60.0, but $25.0 was already spent -> $35.0 remaining, less than $49.99 rate
    limits = create_trusted_surface_open_mandates(
        buyer_email=email_unbound,
        monthly_budget_cap=60.0,
        agent_key=agent_key,
        user_key=owner_key,
    )
    rec = create_merchant_checkout("ap2-batch", 49.99, email_unbound)
    mc = MandateClient()
    chk_chain = mc.present(
        holder_key=agent_key,
        mandate_token=limits["open_checkout_mandate_token"],
        payloads=[CheckoutMandate(vct="mandate.checkout.1", checkout_jwt=rec["checkout_jwt"], checkout_hash=rec["checkout_hash"])],
        aud=AP2_MERCHANT_ID,
        nonce=rec["nonce"],
    )
    pay_chain = mc.present(
        holder_key=agent_key,
        mandate_token=limits["open_payment_mandate_token"],
        payloads=[PaymentMandate(
            vct="mandate.payment.1",
            transaction_id=rec["checkout_hash"],
            payment_amount=Amount(amount=4999, currency="USD"),
            payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
            payment_instrument=PaymentInstrument(type="paypal_vault", id="vault-unbound"),
        )],
        aud=AP2_MERCHANT_ID,
        nonce=rec["nonce"],
    )

    offer_id = f"off_unbound_{uuid.uuid4().hex[:8]}"
    save_mandate(offer_id, {
        "offer_id": offer_id,
        "mandate_proof_hash": rec["checkout_hash"],
        "tier_id": "ap2-batch",
        "amount": 49.99,
        "authoritative_budget_cap": 60.0,
        "contractor_email": None,
    })

    # Record $25 prior spend so available budget is only $35
    ledger.record_spend(25.0, {"contractor_email": email_unbound, "agent_id": "buyer-agent-01"})

    # Purchase attempt fails on budget
    res = _run(seller_agent.purchase_subscription(
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        checkout_mandate_chain=chk_chain,
        payment_mandate_chain=pay_chain,
        checkout_jwt=rec["checkout_jwt"],
        buyer_email=email_unbound,
        contractor_email=email_unbound,
        offer_id=offer_id,
        nonce=rec["nonce"],
    ))
    assert res.get("status") == "REJECTED"
    assert res.get("error") == "BUDGET_EXHAUSTED"

    # Verify authorized_mandates record did not get bound to email_unbound
    auth_mandate = get_mandate(offer_id)
    assert auth_mandate.get("contractor_email") is None


def test_wallet_void_rejected_checkout_releases_budget(tmp_path):
    """
    Finding 2: The wallet provides void_rejected_checkout to release reserved budget
    and purchase slots when presented with a valid merchant-signed Error receipt.
    """
    from backend.wallet.wallet import BuyerWallet, init_agent_key
    from backend.services.ap2_keys import get_merchant_public_jwk
    from backend.services.trusted_surface_service import create_trusted_surface_open_mandates
    from backend.wallet import mcp_server as wallet_mcp

    wdir = tmp_path / "test_wallet_release"
    agent_pub = init_agent_key(wdir)
    owner = _gen_key("owner-wallet")
    email = f"wallet-release-{uuid.uuid4().hex[:8]}@example.com"
    register_buyer_key(
        kid=owner.kid,
        public_key_hex=owner.export_public(),
        contractor_email=email,
    )
    (wdir / "merchant_public.jwk").write_text(json.dumps(get_merchant_public_jwk()), encoding="utf-8")
    (wdir / "owner_public.jwk").write_text(owner.export_public(), encoding="utf-8")

    limits = create_trusted_surface_open_mandates(
        buyer_email=email,
        monthly_budget_cap=60.0,
        yearly_budget_ceiling=60.0,
        agent_key=JWK(**agent_pub),
        user_key=owner,
        validity_seconds=3600,
    )
    (wdir / "owner_limits.json").write_text(json.dumps({
        "buyer_email": email,
        "open_checkout_mandate_token": limits["open_checkout_mandate_token"],
        "open_payment_mandate_token": limits["open_payment_mandate_token"],
    }), encoding="utf-8")

    wallet = BuyerWallet(wdir)

    # 1. Sign a checkout for $49.99
    rec = create_merchant_checkout("ap2-batch", 49.99, email)
    signed = wallet.sign_checkout(rec["checkout_jwt"])
    assert signed["status"] == "SIGNED"
    chk_hash = signed["checkout_hash"]

    # Budget is now 6000 - 4999 = 1001 cents remaining, 1 purchase signed
    limits_after_sign = wallet.describe_limits()
    assert limits_after_sign["signed_so_far_cents"] == 4999
    assert limits_after_sign["remaining_budget_cents"] == 1001
    assert limits_after_sign["purchases_signed"] == 1

    # 2. Seller rejects (e.g. rate tampering) and issues an Error receipt
    tamper_res = _run(seller_agent.purchase_subscription(
        tier_id="ap2-batch",
        agreed_monthly_rate=48.99,  # Tamper rate
        checkout_mandate_chain=signed["checkout_mandate_chain"],
        payment_mandate_chain=signed["payment_mandate_chain"],
        checkout_jwt=rec["checkout_jwt"],
        buyer_email=email,
        nonce=rec["nonce"],
    ))
    assert tamper_res["status"] == "REJECTED"
    err_receipt = tamper_res["checkout_receipt"]

    # 3. Release budget using the error receipt on BuyerWallet
    release_data = wallet.void_rejected_checkout(err_receipt)
    assert release_data["status"] == "RELEASED"
    assert release_data["released_checkout_hash"] == chk_hash
    assert release_data["released_amount_cents"] == 4999
    assert release_data["remaining_budget_cents"] == 6000
    assert release_data["purchases_signed"] == 0

    # 4. Limits in wallet are fully restored
    limits_restored = wallet.describe_limits()
    assert limits_restored["signed_so_far_cents"] == 0
    assert limits_restored["remaining_budget_cents"] == 6000
    assert limits_restored["purchases_signed"] == 0


