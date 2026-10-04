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
        business_name="Miller Custom Flooring",
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
        business_name="Miller Custom Flooring",
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
        business_name="Miller Custom Flooring",
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
        business_name="Miller Custom Flooring",
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
        business_name="Miller Custom Flooring",
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
        business_name="Miller Custom Flooring",
        monthly_cap_usd=100.00,
        agreed_price_usd=79.99,
        nonce="nonce_a1b2c3",
        buyer_private_key_hex=buyer_priv,
    )
    
    # Attacker tries to forge signature on an altered $150 transaction using attacker's private key
    forged_proof = generate_dynamic_mandate_proof(
        contractor_id="usr_883",
        business_name="Miller Custom Flooring",
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
    """Attempting to bind a $49.99 authorized proof for a $179.99 purchase must be rejected."""
    from backend.agents.seller_agent import seller_agent
    from backend.services.mandate_evaluator import register_authorized_mandate

    token = "test_authorized_token_49_99"
    register_authorized_mandate(
        token,
        {"tier_id": "solo-starter", "amount": 49.99, "buyer_agent_id": "buyer-test"},
    )

    # Attempt to purchase at $179.99 with $49.99 token
    res = await seller_agent.purchase_subscription(
        tier_id="solo-starter",
        agreed_monthly_rate=179.99,
        mandate_proof_hash=token,
        contractor_email="test@contractor.com",
    )
    assert res["status"] == "REJECTED"
    assert "RATE_TAMPERING_DETECTED" in res["reason"]


@pytest.mark.asyncio
async def test_purchase_subscription_rejects_tier_mismatch():
    """Attempting to bind a solo-starter proof for pro-dispatch must be rejected."""
    from backend.agents.seller_agent import seller_agent
    from backend.services.mandate_evaluator import register_authorized_mandate

    token = "test_authorized_solo_starter_token"
    register_authorized_mandate(
        token,
        {"tier_id": "solo-starter", "amount": 49.99, "buyer_agent_id": "buyer-test"},
    )

    # Attempt to purchase pro-dispatch with solo-starter token
    res = await seller_agent.purchase_subscription(
        tier_id="pro-dispatch",
        agreed_monthly_rate=49.99,
        mandate_proof_hash=token,
        contractor_email="test@contractor.com",
    )
    assert res["status"] == "REJECTED"
    assert "TIER_MISMATCH_DETECTED" in res["reason"]


@pytest.mark.asyncio
async def test_purchase_subscription_deterministic_id():
    """Subscription IDs must be mathematically deterministic and stable across calls."""
    from backend.agents.seller_agent import seller_agent
    from backend.services.mandate_evaluator import register_authorized_mandate

    token = "test_stable_token_12345"
    register_authorized_mandate(
        token,
        {"tier_id": "solo-starter", "amount": 49.99, "buyer_agent_id": "buyer-test"},
    )

    res1 = await seller_agent.purchase_subscription(
        tier_id="solo-starter",
        agreed_monthly_rate=49.99,
        mandate_proof_hash=token,
        contractor_email="marcus@millerflooring.com",
    )
    res2 = await seller_agent.purchase_subscription(
        tier_id="solo-starter",
        agreed_monthly_rate=49.99,
        mandate_proof_hash=token,
        contractor_email="marcus@millerflooring.com",
    )
    assert res1["status"] == "ACTIVE"
    assert res1["subscription_id"] == res2["subscription_id"]
    assert res1["subscription_id"].startswith("I-A2A-VAULT-")
    assert res1["paypal_environment"] == "sandbox"


@pytest.mark.asyncio
async def test_purchase_subscription_rejects_identity_mismatch():
    """A mandate negotiated for one contractor email cannot be redeemed, or hijacked, by another."""
    from backend.agents.seller_agent import seller_agent

    neg = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="buyer-identity-test",
        tier_id="flooring-tile",
        monthly_budget_cap=60.00,
        contractor_email="marcus@millercustomfloors.com",
    )
    token = neg["mandate_proof_hash"]

    stolen = await seller_agent.purchase_subscription(
        tier_id="solo-starter",
        agreed_monthly_rate=49.99,
        mandate_proof_hash=token,
        contractor_email="attacker@example.com",
    )
    assert stolen["status"] == "REJECTED"
    assert "IDENTITY_MISMATCH_DETECTED" in stolen["reason"]

    legit = await seller_agent.purchase_subscription(
        tier_id="solo-starter",
        agreed_monthly_rate=49.99,
        mandate_proof_hash=token,
        contractor_email="Marcus@MillerCustomFloors.com",
    )
    assert legit["status"] == "ACTIVE"
    assert legit["contractor_email"] == "Marcus@MillerCustomFloors.com"

    # Replays after a completed purchase are still identity-checked
    replay = await seller_agent.purchase_subscription(
        tier_id="solo-starter",
        agreed_monthly_rate=49.99,
        mandate_proof_hash=token,
        contractor_email="attacker@example.com",
    )
    assert replay["status"] == "REJECTED"


@pytest.mark.asyncio
async def test_unbound_mandate_locks_to_first_redeemer():
    """A mandate issued without an email is locked to the first contractor who redeems it."""
    from backend.agents.seller_agent import seller_agent
    from backend.services.mandate_evaluator import register_authorized_mandate

    token = "test_unbound_token_lock"
    register_authorized_mandate(
        token,
        {"tier_id": "solo-starter", "amount": 49.99, "buyer_agent_id": "buyer-test"},
    )
    first = await seller_agent.purchase_subscription(
        tier_id="solo-starter", agreed_monthly_rate=49.99,
        mandate_proof_hash=token, contractor_email="first@contractor.com",
    )
    second = await seller_agent.purchase_subscription(
        tier_id="solo-starter", agreed_monthly_rate=49.99,
        mandate_proof_hash=token, contractor_email="second@contractor.com",
    )
    assert first["status"] == "ACTIVE"
    assert second["status"] == "REJECTED"


@pytest.mark.asyncio
async def test_purchase_rejects_unissued_mandate_hash():
    """A well-formed but never-issued 64-hex hash must not be accepted."""
    from backend.agents.seller_agent import seller_agent

    res = await seller_agent.purchase_subscription(
        tier_id="solo-starter",
        agreed_monthly_rate=49.99,
        mandate_proof_hash="a" * 64,
        contractor_email="marcus@millercustomfloors.com",
    )
    assert res["status"] == "REJECTED"
    assert "UNKNOWN_MANDATE" in res["reason"]


@pytest.mark.asyncio
async def test_ap2_mandate_identical_across_negotiate_and_purchase():
    """purchase_subscription returns the exact signed AP2 mandate issued by negotiate_tier_terms."""
    from backend.agents.seller_agent import seller_agent
    from backend.services.crypto_mandate import verify_ap2_intent_mandate

    neg = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="buyer-consistency-test",
        tier_id="solo-starter",
        monthly_budget_cap=60.00,
        contractor_email="consistency@contractor.com",
    )
    assert neg["status"] == "APPROVED"
    mandate = neg["ap2_intent_mandate"]
    assert verify_ap2_intent_mandate(mandate)
    assert mandate["payer"]["email"] == "consistency@contractor.com"
    assert mandate["amount"] == {"value": "49.99", "currency_code": "USD"}
    assert mandate["negotiation_id"] == neg["negotiation_id"]

    purchase = await seller_agent.purchase_subscription(
        tier_id="solo-starter",
        agreed_monthly_rate=49.99,
        mandate_proof_hash=neg["mandate_proof_hash"],
        contractor_email="consistency@contractor.com",
    )
    assert purchase["status"] == "ACTIVE"
    assert purchase["ap2_intent_mandate"] == mandate

    tampered = {**mandate, "amount": {"value": "179.99", "currency_code": "USD"}}
    assert not verify_ap2_intent_mandate(tampered)


@pytest.mark.asyncio
async def test_negotiate_requires_contractor_email():
    from backend.agents.seller_agent import seller_agent

    res = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="buyer-no-email", tier_id="solo-starter", monthly_budget_cap=60.00,
    )
    assert res["status"] == "REJECTED"
    assert res["error"] == "CONTRACTOR_EMAIL_REQUIRED"
