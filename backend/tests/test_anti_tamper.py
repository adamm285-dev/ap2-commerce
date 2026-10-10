"""
Automated Anti-Tamper Verification Test Suite.
Verifies that malicious or accidental modifications to mandate prices, budget caps,
entity names, or timestamps are cryptographically detected and rejected with explicit error codes.
"""

import time
import pytest
from backend.services.crypto_mandate import (
    generate_dynamic_mandate_proof,
    verify_mandate_proof,
)


def test_tamper_detection_price_inflation():
    """Modifying agreed price by even $0.01 must immediately invalidate HMAC signature."""
    proof = generate_dynamic_mandate_proof(
        contractor_id="usr_883",
        business_name="Nexus Autonomous Systems",
        monthly_cap_usd=100.00,
        agreed_price_usd=79.99,
        nonce="nonce_a1b2c3",
    )
    tampered_payload = dict(proof["canonical_payload"])
    tampered_payload["agreed_price_usd"] = 80.00  # Altered 1 cent

    valid, reason = verify_mandate_proof(tampered_payload, proof["signature"])
    assert valid is False
    assert reason == "SIGNATURE_MISMATCH"


def test_tamper_detection_budget_cap_violation():
    """Even if an HMAC was generated, if agreed price exceeds spending cap, reject with BUDGET_CAP_BREACH."""
    proof = generate_dynamic_mandate_proof(
        contractor_id="usr_883",
        business_name="Nexus Autonomous Systems",
        monthly_cap_usd=75.00,
        agreed_price_usd=79.99,
        nonce="nonce_a1b2c3",
    )
    # Even if signature is mathematically valid for this payload, budget cap check fails
    valid, reason = verify_mandate_proof(proof["canonical_payload"], proof["signature"])
    assert valid is False
    assert reason == "BUDGET_CAP_BREACH"


def test_tamper_detection_timestamp_expiration():
    """Stale mandate proofs (>300 seconds drift) must be rejected with TIMESTAMP_EXPIRED."""
    proof = generate_dynamic_mandate_proof(
        contractor_id="usr_883",
        business_name="Nexus Autonomous Systems",
        monthly_cap_usd=100.00,
        agreed_price_usd=79.99,
        nonce="nonce_a1b2c3",
    )
    expired_payload = dict(proof["canonical_payload"])
    expired_payload["timestamp"] = int(time.time()) - 350  # 350 seconds ago

    valid, reason = verify_mandate_proof(expired_payload, proof["signature"])
    assert valid is False
    assert reason == "TIMESTAMP_EXPIRED"


def test_tamper_detection_business_name_alteration():
    """Altering the contractor business entity name must fail HMAC verification."""
    proof = generate_dynamic_mandate_proof(
        contractor_id="usr_883",
        business_name="Nexus Autonomous Systems",
        monthly_cap_usd=100.00,
        agreed_price_usd=79.99,
        nonce="nonce_a1b2c3",
    )
    tampered_payload = dict(proof["canonical_payload"])
    tampered_payload["business_name"] = "Illegitimate Contractor Corp"

    valid, reason = verify_mandate_proof(tampered_payload, proof["signature"])
    assert valid is False
    assert reason == "SIGNATURE_MISMATCH"


def test_valid_proof_verification():
    """An unaltered canonical payload within valid time window must pass with VERIFIED."""
    proof = generate_dynamic_mandate_proof(
        contractor_id="usr_883",
        business_name="Nexus Autonomous Systems",
        monthly_cap_usd=100.00,
        agreed_price_usd=79.99,
        nonce="nonce_a1b2c3",
    )
    valid, reason = verify_mandate_proof(proof["canonical_payload"], proof["signature"])
    assert valid is True
    assert reason == "VERIFIED"


def test_asymmetric_ed25519_non_repudiation():
    """A third party or merchant cannot forge an authorization without the buyer's private key."""
    from backend.services.crypto_mandate import generate_ed25519_keypair
    
    # Legitimate buyer generates keypair
    buyer_priv, buyer_pub = generate_ed25519_keypair()
    
    # Attacker / rogue merchant generates their own keypair
    attacker_priv, attacker_pub = generate_ed25519_keypair()
    
    # Buyer signs mandate
    proof = generate_dynamic_mandate_proof(
        contractor_id="usr_883",
        business_name="Nexus Autonomous Systems",
        monthly_cap_usd=100.00,
        agreed_price_usd=79.99,
        nonce="nonce_a1b2c3",
        buyer_private_key_hex=buyer_priv,
    )
    
    # Attacker tries to forge signature on an altered $150 transaction using attacker's private key
    forged_proof = generate_dynamic_mandate_proof(
        contractor_id="usr_883",
        business_name="Nexus Autonomous Systems",
        monthly_cap_usd=100.00,
        agreed_price_usd=79.99,
        nonce="nonce_a1b2c3",
        buyer_private_key_hex=attacker_priv,
    )
    
    # Verification against buyer's legitimate public key MUST reject forged signature
    valid, reason = verify_mandate_proof(
        forged_proof["canonical_payload"],
        forged_proof["signature"],
        public_key_hex=buyer_pub,
    )
    assert valid is False
    assert reason == "SIGNATURE_MISMATCH"


@pytest.mark.asyncio
async def test_purchase_subscription_rejects_rate_tampering():
    """Attempting to purchase at $179.99 with a $49.99 checkout JWT or rate tampering must be rejected."""
    from backend.agents.seller_agent import seller_agent
    from backend.tests.ap2_test_utils import build_test_ap2_chains

    chains = build_test_ap2_chains(tier_id="ap2-batch", monthly_price=49.99, budget_cap=60.0)
    res = await seller_agent.purchase_subscription(
        tier_id="ap2-batch",
        agreed_monthly_rate=179.99,
        checkout_mandate_chain=chains["checkout_mandate_chain"],
        payment_mandate_chain=chains["payment_mandate_chain"],
        checkout_jwt=chains["checkout_jwt"],
        buyer_email=chains["buyer_email"],
        nonce=chains["nonce"],
    )
    assert res["status"] == "REJECTED"


@pytest.mark.asyncio
async def test_purchase_subscription_rejects_tier_mismatch():
    """Attempting to bind an ap2-batch chain for ap2-cluster must be rejected."""
    from backend.agents.seller_agent import seller_agent
    from backend.tests.ap2_test_utils import build_test_ap2_chains

    chains = build_test_ap2_chains(tier_id="ap2-batch", monthly_price=49.99, allowed_tiers=["ap2-batch"])
    res = await seller_agent.purchase_subscription(
        tier_id="ap2-cluster",
        agreed_monthly_rate=49.99,
        checkout_mandate_chain=chains["checkout_mandate_chain"],
        payment_mandate_chain=chains["payment_mandate_chain"],
        checkout_jwt=chains["checkout_jwt"],
        buyer_email=chains["buyer_email"],
        nonce=chains["nonce"],
    )
    assert res["status"] == "REJECTED"


@pytest.mark.asyncio
async def test_purchase_subscription_deterministic_id():
    """Subscription IDs must be mathematically deterministic and stable across calls."""
    from backend.agents.seller_agent import seller_agent
    from backend.tests.ap2_test_utils import build_test_ap2_chains

    chains = build_test_ap2_chains(tier_id="ap2-batch", monthly_price=49.99)
    res1 = await seller_agent.purchase_subscription(
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        checkout_mandate_chain=chains["checkout_mandate_chain"],
        payment_mandate_chain=chains["payment_mandate_chain"],
        checkout_jwt=chains["checkout_jwt"],
        buyer_email=chains["buyer_email"],
        nonce=chains["nonce"],
    )
    res2 = await seller_agent.purchase_subscription(
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        checkout_mandate_chain=chains["checkout_mandate_chain"],
        payment_mandate_chain=chains["payment_mandate_chain"],
        checkout_jwt=chains["checkout_jwt"],
        buyer_email=chains["buyer_email"],
        nonce=chains["nonce"],
    )
    assert res1["status"] == "ACTIVE"
    assert res1["subscription_id"] == res2["subscription_id"]
    assert res1["subscription_id"].startswith("I-A2A-VAULT-")
    assert res1["paypal_environment"] == "sandbox"


@pytest.mark.asyncio
async def test_purchase_subscription_rejects_identity_mismatch():
    """A mandate chain negotiated for one contractor email cannot be redeemed, or hijacked, by another."""
    from backend.agents.seller_agent import seller_agent
    from backend.tests.ap2_test_utils import build_test_ap2_chains

    chains = build_test_ap2_chains(tier_id="ap2-batch", monthly_price=49.99, buyer_email="agent-alpha@example.com")
    stolen = await seller_agent.purchase_subscription(
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        checkout_mandate_chain=chains["checkout_mandate_chain"],
        payment_mandate_chain=chains["payment_mandate_chain"],
        checkout_jwt=chains["checkout_jwt"],
        buyer_email="attacker@example.com",
        contractor_email="attacker@example.com",
        nonce=chains["nonce"],
    )
    assert stolen["status"] == "REJECTED"
    assert "IDENTITY_MISMATCH" in stolen.get("reason", "") or stolen.get("error") is not None

    legit = await seller_agent.purchase_subscription(
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        checkout_mandate_chain=chains["checkout_mandate_chain"],
        payment_mandate_chain=chains["payment_mandate_chain"],
        checkout_jwt=chains["checkout_jwt"],
        buyer_email="agent-alpha@example.com",
        contractor_email="agent-alpha@example.com",
        nonce=chains["nonce"],
    )
    assert legit["status"] == "ACTIVE"
    assert legit["contractor_email"] == "agent-alpha@example.com"

    # Replays after a completed purchase are still identity-checked
    replay = await seller_agent.purchase_subscription(
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        checkout_mandate_chain=chains["checkout_mandate_chain"],
        payment_mandate_chain=chains["payment_mandate_chain"],
        checkout_jwt=chains["checkout_jwt"],
        buyer_email="attacker@example.com",
        contractor_email="attacker@example.com",
        nonce=chains["nonce"],
    )
    assert replay["status"] == "REJECTED"


@pytest.mark.asyncio
async def test_unbound_mandate_locks_to_first_redeemer():
    """A mandate chain is locked to the legitimate purchaser and cannot be hijacked by a second redeemer."""
    from backend.agents.seller_agent import seller_agent
    from backend.tests.ap2_test_utils import build_test_ap2_chains

    chains = build_test_ap2_chains(tier_id="ap2-batch", monthly_price=49.99, buyer_email="first@example.com")
    first = await seller_agent.purchase_subscription(
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        checkout_mandate_chain=chains["checkout_mandate_chain"],
        payment_mandate_chain=chains["payment_mandate_chain"],
        checkout_jwt=chains["checkout_jwt"],
        buyer_email="first@example.com",
        nonce=chains["nonce"],
    )
    second = await seller_agent.purchase_subscription(
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        checkout_mandate_chain=chains["checkout_mandate_chain"],
        payment_mandate_chain=chains["payment_mandate_chain"],
        checkout_jwt=chains["checkout_jwt"],
        buyer_email="second@example.com",
        contractor_email="second@example.com",
        nonce=chains["nonce"],
    )
    assert first["status"] == "ACTIVE"
    assert second["status"] == "REJECTED"


@pytest.mark.asyncio
async def test_purchase_rejects_unissued_mandate_hash():
    """A call without valid AP2 v0.2 mandate chains must be rejected with signed error receipts."""
    from backend.agents.seller_agent import seller_agent

    res = await seller_agent.purchase_subscription(
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        mandate_proof_hash="a" * 64,
        contractor_email="agent-alpha@example.com",
    )
    assert res["status"] == "REJECTED"
    assert res.get("checkout_receipt") is not None
    assert res.get("payment_receipt") is not None


@pytest.mark.asyncio
async def test_ap2_mandate_identical_across_negotiate_and_purchase():
    """purchase_subscription returns signed checkout and payment receipts matching negotiation."""
    from backend.agents.seller_agent import seller_agent
    from backend.tests.ap2_test_utils import build_test_ap2_chains
    from backend.services.ap2_service import verify_receipt_jwt

    neg = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="buyer-consistency-test",
        tier_id="ap2-batch",
        monthly_budget_cap=60.00,
        contractor_email="consistency@example.com",
    )
    assert neg["status"] == "APPROVED"
    assert "checkout_jwt" in neg
    chk_jwt = neg["checkout_jwt"]

    chains = build_test_ap2_chains(
        tier_id="ap2-batch",
        monthly_price=49.99,
        buyer_email="consistency@example.com",
        budget_cap=60.0,
        checkout_record={
            "checkout_jwt": chk_jwt,
            "checkout_hash": neg["checkout_hash"],
            "nonce": neg["nonce"],
            "order_id": neg["offer_id"],
        },
    )

    purchase = await seller_agent.purchase_subscription(
        tier_id="ap2-batch",
        agreed_monthly_rate=49.99,
        checkout_mandate_chain=chains["checkout_mandate_chain"],
        payment_mandate_chain=chains["payment_mandate_chain"],
        checkout_jwt=chk_jwt,
        contractor_email="consistency@example.com",
        buyer_email="consistency@example.com",
        nonce=neg["nonce"],
        offer_id=neg["offer_id"],
    )
    assert purchase["status"] == "ACTIVE"
    assert "checkout_receipt" in purchase
    assert "payment_receipt" in purchase
    rec = verify_receipt_jwt(purchase["checkout_receipt"])
    assert rec["status"] == "Success"


@pytest.mark.asyncio
async def test_negotiate_requires_contractor_email():
    from backend.agents.seller_agent import seller_agent

    res = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="buyer-no-email", tier_id="ap2-batch", monthly_budget_cap=60.00,
    )
    assert res["status"] == "REJECTED"
    assert res["error"] in ("BUYER_EMAIL_REQUIRED", "CONTRACTOR_EMAIL_REQUIRED")
