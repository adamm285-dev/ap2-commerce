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
