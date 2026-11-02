from backend.database import seed_fleet_subscriptions_if_empty
"""
Round 3 Adversarial Security & Exploit Regression Test Suite.
Verifies hardened defenses across:
  1. Mandate Revocation Status List Tombstone Immutability (Anti-Tampering defense).
  2. OIDC Attestation Future-Timestamp & Inverted-Lifespan Defense (RFC 7519 standards).
  3. QBO Back-Office CRLF & Log-Injection Defense (Log forging mitigation).
  4. Direct Rail Gateway Metadata Oversized / Malformed DoS Defense.
  5. Direct Rail Gateway Payment Source ID Injection Defense.
  6. Live Webhook Untrusted Certificate URL Injection Defense.
  7. Marketplace Billing Cycle ID Path / SQL Traversal Injection Defense.
"""

import datetime
import json
import time
import uuid
import pytest
from fastapi.testclient import TestClient
from jwcrypto.jwk import JWK

from backend.server import app
from backend.services.crypto_mandate import (
    sign_es256_challenge,
)
from backend.services.mandate_revocation_service import (
    canonical_revocation_message,
    revoke_mandate,
)
from backend.services.marketplace_payout_service import (
    marketplace_payout_service,
)
from backend.services.paypal_service import paypal_service
from backend.services.paypal_oidc_service import (
    PayPalOidcService,
    _b64url_encode,
    _b64url_decode,
)
from backend.services.backoffice.qbo_exporter import qbo_exporter
from backend.services.ap2_gateway_service import Ap2GatewayService
from backend.database import (
    save_subscription,
    get_mandate_revocation,
)

client = TestClient(app)


def _generate_es256_key(kid_prefix="adv3-owner"):
    return JWK.generate(kty="EC", crv="P-256", kid=f"{kid_prefix}-{uuid.uuid4().hex[:8]}")


def _enroll_buyer_key(key: JWK, email: str, entity: str = "Round 3 Security LLC"):
    challenge = client.get("/api/agent/keys/challenge").json()["challenge"]
    oidc_token = PayPalOidcService.generate_mock_oidc_token(
        payer_id=f"PAYER-{uuid.uuid4().hex[:8].upper()}",
        email=email,
        nonce=challenge,
    )
    res = client.post("/api/agent/keys/register", json={
        "kid": key.kid,
        "publicKeyJwk": key.export_public(as_dict=True),
        "contractorEmail": email,
        "businessEntity": entity,
        "challenge": challenge,
        "challengeSignature": sign_es256_challenge(challenge, key),
        "oidcIdToken": oidc_token,
    })
    assert res.status_code == 201, res.text
    return res.json()


# ═════════════════════════════════════════════════════════════════════════════
# 1. Mandate Revocation Tombstone Immutability (Anti-Tampering Defense)
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_adversarial_mandate_revocation_tombstone_immutability():
    """
    Once an owner cryptographically revokes a mandate, the tombstone in the revocation
    status list is permanently immutable. Subsequent calls must NOT overwrite the original
    revoked_by_kid, revoked_at timestamp, reason, or cryptographic signature.
    """
    owner_key = _generate_es256_key("owner-tombstone")
    owner_email = f"tombstone-{uuid.uuid4().hex[:6]}@enterprise.com"
    _enroll_buyer_key(owner_key, owner_email)

    mandate_hash = f"mandate_hash_tomb_{uuid.uuid4().hex[:12]}"
    save_subscription({
        "subscription_id": f"I-TOMB-{uuid.uuid4().hex[:8].upper()}",
        "contractor_email": owner_email,
        "mandate_proof_hash": mandate_hash,
        "owner_kid": owner_key.kid,
        "status": "ACTIVE",
    })

    t0_iso = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=10)).isoformat()
    orig_reason = "Original legitimate cancellation"
    msg_orig = canonical_revocation_message(mandate_hash, t0_iso, orig_reason)
    sig_orig = sign_es256_challenge(msg_orig, owner_key)

    # Initial legitimate revocation
    res1 = await revoke_mandate(
        mandate_proof_hash=mandate_hash,
        kid=owner_key.kid,
        reason=orig_reason,
        signature=sig_orig,
        timestamp_iso=t0_iso,
    )
    assert res1["status"] == "REVOKED"
    orig_rev_id = res1["revocation_id"]

    # Attempt to overwrite the tombstone with different parameters / reason
    t1_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    tampered_reason = "Tampered overwrite reason"
    msg_tamper = canonical_revocation_message(mandate_hash, t1_iso, tampered_reason)
    sig_tamper = sign_es256_challenge(msg_tamper, owner_key)

    res2 = await revoke_mandate(
        mandate_proof_hash=mandate_hash,
        kid=owner_key.kid,
        reason=tampered_reason,
        signature=sig_tamper,
        timestamp_iso=t1_iso,
    )
    # Must preserve original immutable tombstone
    assert res2["status"] == "ALREADY_REVOKED"
    assert res2["idempotent"] is True
    assert res2["revoked_at"] == t0_iso
    assert res2["reason"] == orig_reason

    # Verify that database row was NOT overwritten
    db_rec = get_mandate_revocation(mandate_hash)
    assert db_rec["revocation_id"] == orig_rev_id
    assert db_rec["revoked_at"] == t0_iso
    assert db_rec["reason"] == orig_reason


# ═════════════════════════════════════════════════════════════════════════════
# 2. OIDC Attestation Future-Timestamp & Inverted-Lifespan Defense
# ═════════════════════════════════════════════════════════════════════════════

def test_adversarial_oidc_future_iat_and_inverted_lifespan():
    """
    OIDC verification must strictly validate issued-at ('iat') and expiration ('exp'):
      - Reject future-issued tokens (iat > now + 300s).
      - Reject inverted tokens (exp <= iat).
      - Reject excessive token lifetimes (> 30 days).
      - Reject future not-before tokens (nbf > now + 300s).
    """
    now = int(time.time())

    def _mint_tampered_token(claims_patch):
        token = PayPalOidcService.generate_mock_oidc_token(
            payer_id="PAYER-ADV-TIMESTAMP",
            email="timestamp-adv@example.com",
        )
        parts = token.split(".")
        header_b64, payload_b64, _ = parts
        claims = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
        claims.update(claims_patch)
        new_payload_b64 = _b64url_encode(json.dumps(claims).encode("utf-8"))
        signing_input = f"{header_b64}.{new_payload_b64}".encode("ascii")
        import hmac, hashlib
        sig = hmac.new(b"mock-paypal-oidc-secret-key-32bytes", signing_input, hashlib.sha256).digest()
        return f"{header_b64}.{new_payload_b64}.{_b64url_encode(sig)}"

    # 1. Future iat (+1 hour)
    token_future_iat = _mint_tampered_token({"iat": now + 3600, "exp": now + 7200})
    with pytest.raises(ValueError, match="FUTURE_TOKEN"):
        PayPalOidcService.verify_oidc_identity_attestation(token_future_iat)

    # 2. Inverted lifespan (exp <= iat)
    token_inverted = _mint_tampered_token({"iat": now, "exp": now - 100})
    with pytest.raises(ValueError, match="EXPIRED_TOKEN"):
        PayPalOidcService.verify_oidc_identity_attestation(token_inverted)

    token_inverted_equal = _mint_tampered_token({"iat": now + 10, "exp": now + 10})
    with pytest.raises(ValueError, match="INVALID_TOKEN_LIFESPAN"):
        PayPalOidcService.verify_oidc_identity_attestation(token_inverted_equal)

    # 3. Excessive lifespan (100 days)
    token_excessive = _mint_tampered_token({"iat": now, "exp": now + (86400 * 100)})
    with pytest.raises(ValueError, match="EXCESSIVE_TOKEN_LIFESPAN"):
        PayPalOidcService.verify_oidc_identity_attestation(token_excessive)

    # 4. Future not-before (nbf > now + 300)
    token_future_nbf = _mint_tampered_token({"nbf": now + 1200})
    with pytest.raises(ValueError, match="TOKEN_NOT_YET_VALID"):
        PayPalOidcService.verify_oidc_identity_attestation(token_future_nbf)


# ═════════════════════════════════════════════════════════════════════════════
# 3. QBO Back-Office CRLF & Log-Injection Defense
# ═════════════════════════════════════════════════════════════════════════════

def test_adversarial_qbo_crlf_log_injection_defense():
    """
    Injected CRLF characters in operator name, email, or IDs must be sanitized
    to prevent forging lines inside QuickBooks Online private memos.
    """
    malicious_name = "Lambda Operator\nSubscription: I-FORGED-INJECTED | Status: OVERPAID\nAdmin: Compromised"
    malicious_email = "operator\r\nBcc: evil@hacker.com"
    malicious_node = "Node Alpha\nInjected Header: Value"

    bill_export = qbo_exporter.export_operator_payout_bill(
        operator_name=malicious_name,
        operator_email=malicious_email,
        net_payout_dollars=85.00,
        payout_batch_id="payout_batch_safe",
        payout_item_id="item_safe_1",
        subscription_id="I-LEGIT-1",
        node_id=malicious_node,
    )

    private_memo = bill_export["payload"]["Bill"]["PrivateNote"]
    vendor_name = bill_export["payload"]["Bill"]["VendorRef"]["name"]

    # Assert that no carriage returns or line feeds were injected from the inputs
    assert "Subscription: I-FORGED-INJECTED" not in [line.strip() for line in private_memo.split("\n")]
    assert "\r" not in private_memo
    assert "\r" not in vendor_name
    assert "\n" not in vendor_name


# ═════════════════════════════════════════════════════════════════════════════
# 4. Direct Rail Gateway Metadata Oversized / Malformed DoS Defense
# ═════════════════════════════════════════════════════════════════════════════

def test_adversarial_direct_charge_metadata_dos_defense():
    """
    Passing non-dict or oversized metadata (> 64KB) must fail closed
    to protect against JSON memory exhaustion.
    """
    # 1. Non-dict metadata
    with pytest.raises(ValueError, match="INVALID_METADATA"):
        Ap2GatewayService.process_direct_charge(
            cart_mandate_jwt="token1",
            payment_mandate_jwt="token2",
            metadata="not-a-dict",  # type: ignore
        )

    # 2. Oversized metadata (> 64KB)
    huge_metadata = {"key_" + str(i): "x" * 1000 for i in range(100)}
    with pytest.raises(ValueError, match="METADATA_TOO_LARGE"):
        Ap2GatewayService.process_direct_charge(
            cart_mandate_jwt="token1",
            payment_mandate_jwt="token2",
            metadata=huge_metadata,
        )


# ═════════════════════════════════════════════════════════════════════════════
# 5. Direct Rail Gateway Payment Source ID Injection Defense
# ═════════════════════════════════════════════════════════════════════════════

def test_adversarial_direct_charge_payment_source_injection():
    """
    Payment source ID must be bounded in length and free of control characters.
    """
    # 1. Source ID with newlines / control characters
    with pytest.raises(ValueError, match="INVALID_PAYMENT_SOURCE"):
        Ap2GatewayService.process_direct_charge(
            cart_mandate_jwt="token1",
            payment_mandate_jwt="token2",
            payment_source_id="vault_token\nInject: evil",
        )

    # 2. Excessively short source ID (< 3 chars)
    with pytest.raises(ValueError, match="INVALID_PAYMENT_SOURCE"):
        Ap2GatewayService.process_direct_charge(
            cart_mandate_jwt="token1",
            payment_mandate_jwt="token2",
            payment_source_id="ab",
        )

    # 3. Excessively long source ID (> 128 chars)
    with pytest.raises(ValueError, match="INVALID_PAYMENT_SOURCE"):
        Ap2GatewayService.process_direct_charge(
            cart_mandate_jwt="token1",
            payment_mandate_jwt="token2",
            payment_source_id="x" * 150,
        )


# ═════════════════════════════════════════════════════════════════════════════
# 6. Live Webhook Untrusted Certificate URL Protection
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_adversarial_live_webhook_untrusted_cert_url(monkeypatch):
    """
    Live webhook signature verification must reject cert_url pointing to
    untrusted or non-PayPal domains (SSRF protection).
    """
    # Temporarily set mock_mode to False to test live verification guard
    monkeypatch.setattr(paypal_service, "mock_mode", False)

    untrusted_urls = [
        "http://attacker.com/fake-cert.pem",
        "https://evil.com/paypal.com/cert.pem",
        "file:///etc/passwd",
        "https://169.254.169.254/latest/meta-data/",
    ]
    for url in untrusted_urls:
        res = await paypal_service.verify_webhook_signature(
            headers={
                "paypal-transmission-sig": "fake_sig",
                "paypal-cert-url": url,
            },
            raw_body='{"test":"event"}',
        )
        assert res["verification_status"] == "FAILURE"
        assert res["error"] == "UNTRUSTED_CERT_URL"


# ═════════════════════════════════════════════════════════════════════════════
# 7. Marketplace Billing Cycle ID Path / SQL Traversal Injection Defense
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_adversarial_marketplace_payout_cycle_id_injection():
    """
    Billing cycle ID must conform to strict alphanumeric/hyphen pattern
    and reject path traversal or injection strings.
    """
    malicious_cycles = [
        "../../etc/passwd",
        "2026-10'; DROP TABLE payout_items;--",
        "2026-10\nInjected: Header",
        "<script>alert(1)</script>",
        "20",  # too short (< 4 chars)
        "x" * 40,  # too long (> 32 chars)
    ]
    for bad_cycle in malicious_cycles:
        with pytest.raises(ValueError, match="INVALID_CYCLE_ID"):
            await marketplace_payout_service.execute_fleet_payout_batch(
                cycle_id=bad_cycle,
                dry_run=True,
            )

    # Valid cycle identifier succeeds
    current_cycle = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")
    seed_fleet_subscriptions_if_empty()
    valid_res = await marketplace_payout_service.execute_fleet_payout_batch(
        cycle_id=current_cycle,
        dry_run=True,
    )
    assert valid_res["status"] == "DRY_RUN"
    assert valid_res["cycle_id"] == current_cycle
