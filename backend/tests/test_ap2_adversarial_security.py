"""
Adversarial Security & Exploit Regression Test Suite for AP2 Native Rail and PayPal OIDC.
Milestone S3-NATIVE (Sprint 3) / SPEC-001 v1.9.0.

Rigorous automated penetration and attack tests covering:
  1. OIDC Cryptographic Signature & Algorithm Bypass Attacks (CVSS High)
  2. Identity Hijacking via Email Binding Mismatch Attacks (CVSS High)
  3. Buyer Key ID Substitution & Identity Spoofing Attacks (CVSS High)
  4. Multi-Charge Open Mandate Cumulative Budget Exhaustion Bypass (Rule 1 & Rule 6)
  5. Persistent Direct Charge Replay Attacks across cache invalidation (Rule 1)
  6. Cryptographically Revoked Mandate Charge Settlement Attacks (SPEC-001 v1.9.0)
"""

import base64
import hashlib
import hmac
import json
import time
import uuid
import pytest
from fastapi.testclient import TestClient
from jwcrypto.jwk import JWK
from cryptography.hazmat.primitives.asymmetric import ed25519

from backend.server import app
from backend.services.paypal_oidc_service import (
    PayPalOidcService,
    _b64url_encode,
    _b64url_decode,
)
from backend.services.ap2_service import (
    create_merchant_checkout,
    AP2_MERCHANT_ID,
    AP2_MERCHANT_NAME,
    _RECEIPT_STORE,
)
from backend.services.trusted_surface_service import create_trusted_surface_open_mandates
from backend.database import (
    register_buyer_key,
    get_buyer_identity,
    record_mandate_revocation,
)
from backend.tests.ap2_test_utils import build_test_ap2_chains, setup_test_vault
from ap2.sdk.mandate import MandateClient
from ap2.sdk.generated.checkout_mandate import CheckoutMandate
from ap2.sdk.generated.payment_mandate import PaymentMandate
from ap2.sdk.generated.types.amount import Amount
from ap2.sdk.generated.types.merchant import Merchant
from ap2.sdk.generated.types.payment_instrument import PaymentInstrument


@pytest.fixture
def client():
    return TestClient(app)


# ═════════════════════════════════════════════════════════════════════════════
# 1. OIDC Cryptographic Signature & Algorithm Attacks
# ═════════════════════════════════════════════════════════════════════════════

def test_adversarial_oidc_forged_signature_attack():
    """Attacker tampers with claims or produces fake signature -> strictly rejected."""
    token = PayPalOidcService.generate_mock_oidc_token(
        payer_id="PAYER-LEGIT",
        email="legit@enterprise.com",
    )
    parts = token.split(".")
    header_b64, payload_b64, _ = parts

    # Attacker alters payload to impersonate admin/victim
    payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    payload["sub"] = "PAYER-ATTACKER-HIJACK"
    payload["email"] = "victim@enterprise.com"
    tampered_payload_b64 = _b64url_encode(json.dumps(payload).encode("utf-8"))

    # Attacker uses forged signature
    forged_token = f"{header_b64}.{tampered_payload_b64}.forged_signature_bytes"

    with pytest.raises(ValueError, match="INVALID_SIGNATURE"):
        PayPalOidcService.verify_oidc_identity_attestation(forged_token)


def test_adversarial_oidc_alg_none_attack():
    """Attacker attempts JWT algorithm confusion with alg: none -> strictly rejected."""
    now = int(time.time())
    header = {"alg": "none", "typ": "JWT"}
    claims = {
        "iss": "https://api.sandbox.paypal.com",
        "sub": "PAYER-ATTACKER-NONE",
        "email": "attacker@evil.com",
        "email_verified": True,
        "exp": now + 3600,
    }
    h_b64 = _b64url_encode(json.dumps(header).encode("utf-8"))
    c_b64 = _b64url_encode(json.dumps(claims).encode("utf-8"))
    none_token = f"{h_b64}.{c_b64}."

    with pytest.raises(ValueError, match="UNSUPPORTED_ALGORITHM"):
        PayPalOidcService.verify_oidc_identity_attestation(none_token)


def test_adversarial_oidc_unsupported_alg_attack():
    """Attacker presents RS256/ES256 on HS256 secret endpoint -> strictly rejected."""
    now = int(time.time())
    header = {"alg": "RS256", "typ": "JWT"}
    claims = {
        "iss": "https://api.sandbox.paypal.com",
        "sub": "PAYER-ATTACKER",
        "email": "attacker@evil.com",
        "email_verified": True,
        "exp": now + 3600,
    }
    h_b64 = _b64url_encode(json.dumps(header).encode("utf-8"))
    c_b64 = _b64url_encode(json.dumps(claims).encode("utf-8"))
    fake_token = f"{h_b64}.{c_b64}.fake_sig"

    with pytest.raises(ValueError, match="UNSUPPORTED_ALGORITHM"):
        PayPalOidcService.verify_oidc_identity_attestation(fake_token)


# ═════════════════════════════════════════════════════════════════════════════
# 2. Identity Hijacking via Email Binding Mismatch Attacks
# ═════════════════════════════════════════════════════════════════════════════

def test_adversarial_registration_email_hijack_attack(client):
    """
    Attacker tries to register their key for victim@target.com using an OIDC
    attestation belonging to attacker@evil.com. Server must refuse with 400.
    """
    priv_key = ed25519.Ed25519PrivateKey.generate()
    pub_hex = priv_key.public_key().public_bytes_raw().hex()
    kid = f"buyer-hijack-{uuid.uuid4().hex[:8]}"

    ch_resp = client.get("/api/agent/keys/challenge")
    challenge_nonce = ch_resp.json()["challenge"]
    sig_hex = priv_key.sign(challenge_nonce.encode("utf-8")).hex()

    # OIDC token is for attacker@evil.com
    oidc_token = PayPalOidcService.generate_mock_oidc_token(
        payer_id="PAYER-ATTACKER-1",
        email="attacker@evil.com",
        nonce=challenge_nonce,
    )

    resp = client.post(
        "/api/agent/keys/register",
        json={
            "kid": kid,
            "publicKeyHex": pub_hex,
            "contractorEmail": "victim@target.com",
            "businessEntity": "Target Victim Enterprise",
            "challenge": challenge_nonce,
            "challengeSignature": sig_hex,
            "oidcIdToken": oidc_token,
        },
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["error"] == "EMAIL_KEY_BINDING_MISMATCH"
    assert "victim@target.com" in detail["reason"]


def test_adversarial_post_attestation_email_hijack_attack(client):
    """
    Attacker tries to attest an existing key registered for victim@target.com
    using an OIDC token belonging to attacker@evil.com. Server must refuse with 403.
    """
    priv_key = ed25519.Ed25519PrivateKey.generate()
    pub_hex = priv_key.public_key().public_bytes_raw().hex()
    kid = f"buyer-victim-{uuid.uuid4().hex[:8]}"

    ch_resp = client.get("/api/agent/keys/challenge")
    challenge_nonce = ch_resp.json()["challenge"]
    sig_hex = priv_key.sign(challenge_nonce.encode("utf-8")).hex()

    # Legitimately register key for victim
    reg_resp = client.post(
        "/api/agent/keys/register",
        json={
            "kid": kid,
            "publicKeyHex": pub_hex,
            "contractorEmail": "victim@target.com",
            "businessEntity": "Target Victim Enterprise",
            "challenge": challenge_nonce,
            "challengeSignature": sig_hex,
        },
    )
    assert reg_resp.status_code == 201

    # Attacker tries to attest victim's key with attacker's PayPal OIDC token
    attacker_oidc = PayPalOidcService.generate_mock_oidc_token(
        payer_id="PAYER-ATTACKER-2",
        email="attacker@evil.com",
    )

    attest_resp = client.post(
        "/api/agent/identity/attest",
        json={
            "kid": kid,
            "oidcIdToken": attacker_oidc,
        },
    )
    assert attest_resp.status_code == 403
    detail = attest_resp.json()["detail"]
    assert detail["error"] == "EMAIL_KEY_BINDING_MISMATCH"


# ═════════════════════════════════════════════════════════════════════════════
# 3. Buyer Key ID Substitution & Identity Spoofing Attacks
# ═════════════════════════════════════════════════════════════════════════════

def test_adversarial_direct_charge_key_substitution_attack(client):
    """
    Attacker presents a mandate signed by Owner A, but passes buyerKeyId of
    registered Buyer B in the request to disguise origin -> strictly rejected with 401.
    """
    u_a = uuid.uuid4().hex[:8]
    u_b = uuid.uuid4().hex[:8]

    # Register Key B
    owner_b = JWK.generate(kty="EC", crv="P-256", kid=f"owner-b-{u_b}")
    register_buyer_key(
        kid=owner_b.kid,
        public_key_hex=owner_b.export_public(),
        contractor_email=f"owner-b-{u_b}@example.com",
        business_name="Enterprise B",
    )

    # Build mandate chain signed by Owner A
    chains_a = build_test_ap2_chains(tier_id="ap2-batch", monthly_price=49.99)

    # Submit charge claiming to be Buyer B while presenting Owner A's mandate
    resp = client.post(
        "/v1/ap2/gateway/charges",
        json={
            "cartMandateJwt": chains_a["checkout_mandate_chain"],
            "paymentMandateJwt": chains_a["payment_mandate_chain"],
            "buyerKeyId": owner_b.kid,
        },
    )
    assert resp.status_code == 401
    detail = resp.json()["detail"]
    assert detail["error"] == "BUYER_KEY_MISMATCH"


def test_adversarial_direct_charge_unregistered_key_attack(client):
    """Submitting a direct charge specifying an unregistered buyerKeyId -> strictly rejected with 401."""
    chains = build_test_ap2_chains(tier_id="ap2-batch", monthly_price=49.99)
    resp = client.post(
        "/v1/ap2/gateway/charges",
        json={
            "cartMandateJwt": chains["checkout_mandate_chain"],
            "paymentMandateJwt": chains["payment_mandate_chain"],
            "buyerKeyId": "completely-unregistered-key-9999",
        },
    )
    assert resp.status_code == 401
    assert resp.json()["detail"]["error"] == "UNREGISTERED_BUYER_KEY"


# ═════════════════════════════════════════════════════════════════════════════
# 4. Multi-Charge Cumulative Budget Exhaustion Defense (Rule 1 & Rule 6)
# ═════════════════════════════════════════════════════════════════════════════

def test_adversarial_open_mandate_cumulative_budget_exhaustion(client):
    """
    Owner issues an open mandate with a monthly spending cap of $100.00.
    First charge of $60.00 succeeds.
    Second charge of $50.00 under the same open mandate breaches cumulative cap ($110 > $100).
    Second charge must be strictly rejected with 400 INVALID_MANDATE (constraint violation).
    """
    u = uuid.uuid4().hex[:8]
    email = f"buyer-budget-{u}@example.com"
    owner_key = JWK.generate(kty="EC", crv="P-256", kid=f"owner-{u}")
    register_buyer_key(
        kid=owner_key.kid,
        public_key_hex=owner_key.export_public(),
        contractor_email=email,
        business_name="Budget Test Enterprise",
    )
    agent_key = JWK.generate(kty="EC", crv="P-256", kid=f"agent-{u}")
    tiers = ["ap2-batch", "ap2-gateway"]

    limits = create_trusted_surface_open_mandates(
        buyer_email=email,
        monthly_budget_cap=100.0,
        yearly_budget_ceiling=100.0,
        allowed_tiers=tiers,
        agent_key=agent_key,
        user_key=owner_key,
    )
    vault_id = setup_test_vault(client, owner_key)

    mc = MandateClient()

    # 1. First direct charge: $60.00 (6000 cents) -> Allowed
    chk_rec_1 = create_merchant_checkout(
        tier_id="ap2-batch",
        monthly_price=60.0,
        contractor_email=email,
    )
    chk_chain_1 = mc.present(
        holder_key=agent_key,
        mandate_token=limits["open_checkout_mandate_token"],
        payloads=[
            CheckoutMandate(
                vct="mandate.checkout.1",
                checkout_jwt=chk_rec_1["checkout_jwt"],
                checkout_hash=chk_rec_1["checkout_hash"],
            )
        ],
        aud=AP2_MERCHANT_ID,
        nonce=chk_rec_1["nonce"],
    )
    pay_chain_1 = mc.present(
        holder_key=agent_key,
        mandate_token=limits["open_payment_mandate_token"],
        payloads=[
            PaymentMandate(
                vct="mandate.payment.1",
                transaction_id=chk_rec_1["checkout_hash"],
                payment_amount=Amount(amount=6000, currency="USD"),
                payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
                payment_instrument=PaymentInstrument(type="paypal_vault", id=vault_id),
            )
        ],
        aud=AP2_MERCHANT_ID,
        nonce=chk_rec_1["nonce"],
    )

    resp1 = client.post(
        "/v1/ap2/gateway/charges",
        json={
            "cartMandateJwt": chk_chain_1,
            "paymentMandateJwt": pay_chain_1,
        },
    )
    assert resp1.status_code == 201
    assert resp1.json()["status"] == "CAPTURED"
    assert resp1.json()["amountCents"] == 6000

    # 2. Second direct charge under SAME open mandate: $50.00 (5000 cents) -> Cumulative $110.00 > $100.00 limit -> Rejected
    chk_rec_2 = create_merchant_checkout(
        tier_id="ap2-gateway",
        monthly_price=50.0,
        contractor_email=email,
    )
    chk_chain_2 = mc.present(
        holder_key=agent_key,
        mandate_token=limits["open_checkout_mandate_token"],
        payloads=[
            CheckoutMandate(
                vct="mandate.checkout.1",
                checkout_jwt=chk_rec_2["checkout_jwt"],
                checkout_hash=chk_rec_2["checkout_hash"],
            )
        ],
        aud=AP2_MERCHANT_ID,
        nonce=chk_rec_2["nonce"],
    )
    pay_chain_2 = mc.present(
        holder_key=agent_key,
        mandate_token=limits["open_payment_mandate_token"],
        payloads=[
            PaymentMandate(
                vct="mandate.payment.1",
                transaction_id=chk_rec_2["checkout_hash"],
                payment_amount=Amount(amount=5000, currency="USD"),
                payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
                payment_instrument=PaymentInstrument(type="paypal_vault", id=vault_id),
            )
        ],
        aud=AP2_MERCHANT_ID,
        nonce=chk_rec_2["nonce"],
    )

    resp2 = client.post(
        "/v1/ap2/gateway/charges",
        json={
            "cartMandateJwt": chk_chain_2,
            "paymentMandateJwt": pay_chain_2,
        },
    )
    assert resp2.status_code == 400
    detail2 = resp2.json()["detail"]
    assert detail2["error"] == "INVALID_MANDATE"
    assert "exceeds budget" in detail2["reason"].lower() or "budget" in detail2["reason"].lower()


# ═════════════════════════════════════════════════════════════════════════════
# 5. Persistent Direct Charge Replay Attacks
# ═════════════════════════════════════════════════════════════════════════════

def test_adversarial_persistent_direct_charge_replay(client):
    """
    Submitting an identical direct charge after wiping in-memory caches (simulating server restart)
    must be caught by persistent SQLite replay check and rejected with 409 Conflict.
    """
    u = uuid.uuid4().hex[:8]
    email = f"buyer-replay-{u}@example.com"
    owner_key = JWK.generate(kty="EC", crv="P-256", kid=f"owner-{u}")
    register_buyer_key(
        kid=owner_key.kid,
        public_key_hex=owner_key.export_public(),
        contractor_email=email,
        business_name="Replay Test Enterprise",
    )
    vault_id = setup_test_vault(client, owner_key)

    chains = build_test_ap2_chains(
        tier_id="ap2-batch",
        monthly_price=49.99,
        buyer_email=email,
        owner_key=owner_key,
        vault_id=vault_id,
    )
    req_body = {
        "cartMandateJwt": chains["checkout_mandate_chain"],
        "paymentMandateJwt": chains["payment_mandate_chain"],
    }

    # First execution succeeds
    resp1 = client.post("/v1/ap2/gateway/charges", json=req_body)
    assert resp1.status_code == 201

    # Wipe in-memory receipt caches to simulate server restart / multi-node bypass
    _RECEIPT_STORE.clear()

    # Replay identical charge
    resp2 = client.post("/v1/ap2/gateway/charges", json=req_body)
    assert resp2.status_code == 409
    assert resp2.json()["detail"]["error"] == "REPLAY_DETECTED"


# ═════════════════════════════════════════════════════════════════════════════
# 6. Revoked Mandate Direct Charge Attack
# ═════════════════════════════════════════════════════════════════════════════

def test_adversarial_revoked_mandate_direct_charge_refusal(client):
    """
    If owner has cryptographically revoked a mandate, direct charges must be refused with 409 Conflict.
    """
    u = uuid.uuid4().hex[:8]
    email = f"buyer-revoked-{u}@example.com"
    owner_key = JWK.generate(kty="EC", crv="P-256", kid=f"owner-{u}")
    register_buyer_key(
        kid=owner_key.kid,
        public_key_hex=owner_key.export_public(),
        contractor_email=email,
        business_name="Revocation Test Enterprise",
    )
    vault_id = setup_test_vault(client, owner_key)

    chains = build_test_ap2_chains(
        tier_id="ap2-batch",
        monthly_price=49.99,
        buyer_email=email,
        owner_key=owner_key,
        vault_id=vault_id,
    )

    # Owner revokes checkout mandate hash
    record_mandate_revocation(
        mandate_proof_hash=chains["checkout_hash"],
        revoked_by_kid=chains["owner_key"].kid,
        reason="Compromised credentials",
        signature_hex="fake_sig_for_test",
    )

    resp = client.post(
        "/v1/ap2/gateway/charges",
        json={
            "cartMandateJwt": chains["checkout_mandate_chain"],
            "paymentMandateJwt": chains["payment_mandate_chain"],
        },
    )
    assert resp.status_code == 409
    assert resp.json()["detail"]["error"] == "MANDATE_REVOKED"
