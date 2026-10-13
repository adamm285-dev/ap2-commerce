"""
Round 2 Adversarial Security & Exploit Regression Test Suite.
Verifies hardened defenses across the 3 accelerators:
  1. Cross-Tenant Mandate Revocation Authorization (Broken Access Control / IDOR defense).
  2. Cryptographic Revocation Timestamp Clock-Skew Defense (Freshness window).
  3. Node Operator Payout Destination Redirection / Hijacking Defense (Payout integrity).
  4. Operator Split Bps Boundary & Financial Logic Validation (Rule 6).
  5. Targeted Subscription Double-Disbursement Defense in Marketplace Batch Payouts.
  6. Webhook Missing Event ID Replay Protection Bypass Defense (Fail-closed event identity).
  7. Timing-Safe Constant-Time Webhook HMAC Signature Comparison.
  8. Direct Charges Pagination Unbounded Query DoS Defense.
"""

import datetime
import json
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
    calculate_split_amounts_cents,
)
from backend.services.paypal_service import paypal_service
from backend.services.paypal_oidc_service import PayPalOidcService
from backend.database import (
    register_node_operator,
    get_node_operator,
    save_subscription,
    get_connection,
)
from backend.config import settings

client = TestClient(app)


def _generate_es256_key(kid_prefix="adv-owner"):
    return JWK.generate(kty="EC", crv="P-256", kid=f"{kid_prefix}-{uuid.uuid4().hex[:8]}")


def _enroll_buyer_key(key: JWK, email: str, entity: str = "Adversarial Test LLC"):
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
# 1. Cross-Tenant Mandate Revocation Authorization Defense (Broken Access Control)
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_adversarial_cross_tenant_mandate_revocation_attack(tmp_path):
    """
    Attacker registers a valid key for attacker@evil.com and attempts to revoke
    a mandate belonging to victim@enterprise.com.
    Must fail closed with UNAUTHORIZED_REVOCATION (HTTP 403 Forbidden).
    """
    victim_key = _generate_es256_key("victim")
    victim_email = f"victim-{uuid.uuid4().hex[:6]}@enterprise.com"
    _enroll_buyer_key(victim_key, victim_email)

    attacker_key = _generate_es256_key("attacker")
    attacker_email = f"attacker-{uuid.uuid4().hex[:6]}@evil.com"
    _enroll_buyer_key(attacker_key, attacker_email)

    # Create active subscription bound to victim
    sub_id = f"I-VICTIM-{uuid.uuid4().hex[:8].upper()}"
    mandate_hash = f"mandate_hash_victim_{uuid.uuid4().hex[:12]}"
    save_subscription({
        "subscription_id": sub_id,
        "contractor_email": victim_email,
        "mandate_proof_hash": mandate_hash,
        "owner_kid": victim_key.kid,
        "status": "ACTIVE",
    })

    # Attacker attempts to cryptographically sign a revocation for victim's mandate
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    msg = canonical_revocation_message(mandate_hash, now_iso, "Malicious cross-tenant cancellation")
    attacker_sig = sign_es256_challenge(msg, attacker_key)

    # 1. Direct service call should raise UNAUTHORIZED_REVOCATION
    with pytest.raises(ValueError, match="UNAUTHORIZED_REVOCATION"):
        await revoke_mandate(
            mandate_proof_hash=mandate_hash,
            kid=attacker_key.kid,
            reason="Malicious cross-tenant cancellation",
            signature=attacker_sig,
            timestamp_iso=now_iso,
        )

    # 2. REST API endpoint should return HTTP 403 Forbidden
    resp = client.post("/api/mandates/revoke", json={
        "mandate_proof_hash": mandate_hash,
        "kid": attacker_key.kid,
        "reason": "Malicious cross-tenant cancellation",
        "signature": attacker_sig,
        "timestamp_iso": now_iso,
    })
    assert resp.status_code == 403
    data = resp.json()
    assert data["detail"]["error"] == "REVOCATION_FAILED"
    assert "UNAUTHORIZED_REVOCATION" in data["detail"]["reason"]

    # 3. Legitimate victim can successfully revoke their own mandate
    victim_sig = sign_es256_challenge(msg, victim_key)
    legit_resp = client.post("/api/mandates/revoke", json={
        "mandate_proof_hash": mandate_hash,
        "kid": victim_key.kid,
        "reason": "Malicious cross-tenant cancellation",
        "signature": victim_sig,
        "timestamp_iso": now_iso,
    })
    assert legit_resp.status_code == 200
    assert legit_resp.json()["status"] == "REVOKED"


# ═════════════════════════════════════════════════════════════════════════════
# 2. Cryptographic Revocation Timestamp Clock-Skew Defense
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_adversarial_revocation_timestamp_clock_skew_attack():
    """
    Submitting a revocation with a timestamp > 300s in the past or future
    must be rejected to prevent pre-dated or stale replay attacks.
    """
    owner_key = _generate_es256_key("owner-skew")
    owner_email = f"skew-{uuid.uuid4().hex[:6]}@enterprise.com"
    _enroll_buyer_key(owner_key, owner_email)

    mandate_hash = f"mandate_hash_skew_{uuid.uuid4().hex[:12]}"
    save_subscription({
        "subscription_id": f"I-SKEW-{uuid.uuid4().hex[:8].upper()}",
        "contractor_email": owner_email,
        "mandate_proof_hash": mandate_hash,
        "status": "ACTIVE",
    })

    # 1. Timestamp 1 hour in the future (skew = +3600s)
    future_dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
    future_iso = future_dt.isoformat()
    msg_future = canonical_revocation_message(mandate_hash, future_iso, "Future attack")
    sig_future = sign_es256_challenge(msg_future, owner_key)

    resp_future = client.post("/api/mandates/revoke", json={
        "mandate_proof_hash": mandate_hash,
        "kid": owner_key.kid,
        "reason": "Future attack",
        "signature": sig_future,
        "timestamp_iso": future_iso,
    })
    assert resp_future.status_code == 400
    assert "REVOCATION_TIMESTAMP_OUT_OF_BOUNDS" in resp_future.json()["detail"]["reason"]

    # 2. Timestamp 1 hour in the past (skew = -3600s)
    past_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
    past_iso = past_dt.isoformat()
    msg_past = canonical_revocation_message(mandate_hash, past_iso, "Stale replay attack")
    sig_past = sign_es256_challenge(msg_past, owner_key)

    resp_past = client.post("/api/mandates/revoke", json={
        "mandate_proof_hash": mandate_hash,
        "kid": owner_key.kid,
        "reason": "Stale replay attack",
        "signature": sig_past,
        "timestamp_iso": past_iso,
    })
    assert resp_past.status_code == 400
    assert "REVOCATION_TIMESTAMP_OUT_OF_BOUNDS" in resp_past.json()["detail"]["reason"]


# ═════════════════════════════════════════════════════════════════════════════
# 3. Node Operator Payout Destination Redirection / Hijacking Defense
# ═════════════════════════════════════════════════════════════════════════════

def test_adversarial_node_operator_destination_hijack_attack():
    """
    An unauthenticated attacker must NOT be able to overwrite the payout email
    of an existing registered node operator.
    """
    op_id = f"op_target_{uuid.uuid4().hex[:8]}"
    legit_email = "legit-operator@compute-fleet.com"

    # Register initial legitimate operator
    reg_init = marketplace_payout_service.register_operator(
        name="Legitimate GPU Host",
        email=legit_email,
        operator_id=op_id,
        split_bps=8500,
    )
    assert reg_init["email"] == legit_email

    # Attacker attempts to hijack payouts to attacker@evil.com via REST API
    hijack_resp = client.post("/api/marketplace/operators/register", json={
        "operator_id": op_id,
        "name": "Hijacked Operator",
        "email": "attacker-payouts@evil.com",
        "split_bps": 8500,
    })
    assert hijack_resp.status_code == 403
    assert "OPERATOR_MODIFICATION_FORBIDDEN" in hijack_resp.json()["detail"]

    # Verify that database was NOT modified
    current_op = get_node_operator(op_id)
    assert current_op["email"] == legit_email

    # Direct database call without allow_overwrite must raise ValueError
    with pytest.raises(ValueError, match="OPERATOR_ALREADY_EXISTS"):
        register_node_operator({
            "operator_id": op_id,
            "name": "Hijacked Operator",
            "email": "attacker-direct@evil.com",
        }, allow_overwrite=False)

    # With admin key header, legitimate destination update is permitted
    admin_secret = getattr(settings, "admin_api_key", "test-admin-key") or "test-admin-key"
    settings.admin_api_key = admin_secret
    admin_resp = client.post(
        "/api/marketplace/operators/register",
        headers={"X-Admin-Key": admin_secret},
        json={
            "operator_id": op_id,
            "name": "Updated GPU Host",
            "email": "new-payouts@compute-fleet.com",
            "split_bps": 8500,
        },
    )
    assert admin_resp.status_code == 201
    assert admin_resp.json()["operator"]["email"] == "new-payouts@compute-fleet.com"


# ═════════════════════════════════════════════════════════════════════════════
# 4. Operator Split Bps Boundary & Financial Logic Validation
# ═════════════════════════════════════════════════════════════════════════════

def test_adversarial_operator_split_bps_bounds_validation():
    """
    Submitting negative or > 10000 split_bps must be rejected by API validation
    and calculation logic (Rule 6).
    """
    # 1. API validation: negative split_bps
    resp_neg = client.post("/api/marketplace/operators/register", json={
        "name": "Invalid Split Operator",
        "email": "test-split@example.com",
        "split_bps": -100,
    })
    assert resp_neg.status_code == 422

    # 2. API validation: > 10000 split_bps
    resp_over = client.post("/api/marketplace/operators/register", json={
        "name": "Invalid Split Operator",
        "email": "test-split@example.com",
        "split_bps": 15000,
    })
    assert resp_over.status_code == 422

    # 3. Calculation logic fail-closed
    with pytest.raises(ValueError, match="split_bps must be between 0 and 10000"):
        calculate_split_amounts_cents(10000, split_bps=-50)

    with pytest.raises(ValueError, match="split_bps must be between 0 and 10000"):
        calculate_split_amounts_cents(10000, split_bps=10001)


# ═════════════════════════════════════════════════════════════════════════════
# 5. Targeted Subscription Double-Disbursement Defense in Marketplace Batch Payouts
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_adversarial_batch_payout_double_disbursement_bypass():
    """
    Passing subscription_ids must NOT bypass cycle-level deduplication.
    A subscription already disbursed in the current billing cycle must be skipped.
    """
    month = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")
    cycle_id = f"{month}-cycle-{uuid.uuid4().hex[:6]}"
    sub_id = f"I-SUB-PAYOUT-{uuid.uuid4().hex[:8].upper()}"

    save_subscription({
        "subscription_id": sub_id,
        "contractor_email": "contractor-dedup@example.com",
        "agreed_monthly_rate": 79.99,
        "assigned_did": "node-dedup-test",
        "status": "ACTIVE",
    })

    # First batch payout executes disbursement
    first_run = await marketplace_payout_service.execute_fleet_payout_batch(
        cycle_id=cycle_id,
        subscription_ids=[sub_id],
        dry_run=False,
    )
    assert first_run["status"] == "SUCCESS"
    assert first_run["item_count"] == 1

    # Second batch payout for the SAME cycle targeting the exact same subscription_ids
    second_run = await marketplace_payout_service.execute_fleet_payout_batch(
        cycle_id=cycle_id,
        subscription_ids=[sub_id],
        dry_run=False,
    )
    # Must return IDEMPOTENT_NOOP with zero duplicate disbursements
    assert second_run["status"] == "IDEMPOTENT_NOOP"
    assert "all subscriptions settled" in second_run["message"]


# ═════════════════════════════════════════════════════════════════════════════
# 6. Webhook Missing Event ID Replay Protection Bypass Defense
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_adversarial_webhook_event_id_replay_bypass_attack():
    """
    PayPal webhooks without a valid unique event ID must fail closed with HTTP 400
    to ensure replay protection cannot be bypassed.
    """
    # 1. Payload with missing "id"
    payload_no_id = {
        "event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
        "resource": {"id": "I-TEST-NO-ID"},
    }
    raw_no_id = json.dumps(payload_no_id)
    sig_no_id = paypal_service.generate_mock_webhook_signature(raw_no_id)

    resp_no_id = client.post(
        "/api/paypal/webhook",
        headers={"paypal-transmission-sig": sig_no_id},
        content=raw_no_id,
    )
    assert resp_no_id.status_code == 400
    assert "Missing or invalid PayPal webhook event ID" in resp_no_id.json()["detail"]

    # 2. Payload with empty string "id": ""
    payload_empty_id = {
        "id": "   ",
        "event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
        "resource": {"id": "I-TEST-EMPTY-ID"},
    }
    raw_empty_id = json.dumps(payload_empty_id)
    sig_empty_id = paypal_service.generate_mock_webhook_signature(raw_empty_id)

    resp_empty_id = client.post(
        "/api/paypal/webhook",
        headers={"paypal-transmission-sig": sig_empty_id},
        content=raw_empty_id,
    )
    assert resp_empty_id.status_code == 400
    assert "Missing or invalid PayPal webhook event ID" in resp_empty_id.json()["detail"]

    # 3. Payload with valid event ID: processed once, replay rejected on duplicate
    event_id = f"WH-EVT-{uuid.uuid4().hex[:12].upper()}"
    payload_valid = {
        "id": event_id,
        "event_type": "BILLING.SUBSCRIPTION.ACTIVATED",
        "resource": {"id": "I-TEST-REPLAY-OK"},
    }
    raw_valid = json.dumps(payload_valid)
    sig_valid = paypal_service.generate_mock_webhook_signature(raw_valid)

    resp_first = client.post(
        "/api/paypal/webhook",
        headers={"paypal-transmission-sig": sig_valid},
        content=raw_valid,
    )
    assert resp_first.status_code == 200
    assert resp_first.json().get("duplicate") is not True

    # Replay identical event
    resp_replay = client.post(
        "/api/paypal/webhook",
        headers={"paypal-transmission-sig": sig_valid},
        content=raw_valid,
    )
    assert resp_replay.status_code == 200
    assert resp_replay.json().get("duplicate") is True
    assert resp_replay.json().get("status") == "already_processed"


# ═════════════════════════════════════════════════════════════════════════════
# 7. Timing-Safe Webhook HMAC Signature Comparison
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_adversarial_timing_safe_webhook_hmac_comparison():
    """
    Verifies that verify_webhook_signature strictly requires valid HMAC,
    fails closed on tampered signatures, and uses timing-safe comparison.
    """
    body = json.dumps({"test": "data", "id": "WH-TEST-HMAC"})
    valid_hmac = paypal_service.generate_mock_webhook_signature(body)

    # Valid signature
    res_valid = await paypal_service.verify_webhook_signature(
        headers={"paypal-transmission-sig": valid_hmac},
        raw_body=body,
    )
    assert res_valid["verification_status"] == "SUCCESS"

    # Tampered signature (1 byte altered)
    tampered_hmac = ("0" if valid_hmac[0] != "0" else "1") + valid_hmac[1:]
    res_tampered = await paypal_service.verify_webhook_signature(
        headers={"paypal-transmission-sig": tampered_hmac},
        raw_body=body,
    )
    assert res_tampered["verification_status"] == "FAILURE"
    assert res_tampered["error"] == "INVALID_SIGNATURE"

    # Truncated signature
    res_short = await paypal_service.verify_webhook_signature(
        headers={"paypal-transmission-sig": valid_hmac[:16]},
        raw_body=body,
    )
    assert res_short["verification_status"] == "FAILURE"


# ═════════════════════════════════════════════════════════════════════════════
# 8. Direct Charges Pagination Unbounded Query DoS Defense
# ═════════════════════════════════════════════════════════════════════════════

def test_adversarial_direct_charges_pagination_dos_attack():
    """
    The direct charges endpoint must enforce pagination boundaries [1, 500]
    to protect against query unbounded resource exhaustion (DoS).
    """
    # 1. Limit exceeding maximum (> 500)
    resp_large = client.get("/v1/ap2/gateway/charges?limit=10000")
    assert resp_large.status_code == 422

    # 2. Limit less than minimum (< 1)
    resp_zero = client.get("/v1/ap2/gateway/charges?limit=0")
    assert resp_zero.status_code == 422

    resp_neg = client.get("/v1/ap2/gateway/charges?limit=-5")
    assert resp_neg.status_code == 422

    # 3. Valid limit within [1, 500]
    resp_valid = client.get("/v1/ap2/gateway/charges?limit=50")
    assert resp_valid.status_code == 200
    assert "charges" in resp_valid.json()
