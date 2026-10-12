"""
Unit & Integration Tests for Cryptographic Mandate Revocation Status List.
Conforms to SPEC-001 v1.9.0 / Milestone S1-RESI.

Tests:
1. Cryptographic signature verification over canonical REVOKE messages (Ed25519 & ES256).
2. Anti-tamper security: Forged signatures, wrong key, altered reason, altered timestamp are rejected.
3. Automated subscription cancellation and ledger reconciliation on revocation.
4. Purchase path enforcement: verify_ap2_chains and purchase_subscription fail closed with error receipts.
5. REST API endpoints: POST /api/mandates/revoke, GET /api/mandates/revocations.
"""

import datetime
import json
import uuid
from typing import Dict, Any

import pytest
from fastapi.testclient import TestClient
from jwcrypto.jwk import JWK

from backend.agents.seller_agent import _COMPLETED_SUBSCRIPTIONS, seller_agent
from backend.database import (
    get_connection,
    get_mandate_revocation,
    is_mandate_revoked,
    list_revoked_mandates,
    register_buyer_key,
)
from backend.server import app
from backend.services.ap2_keys import get_merchant_public_jwk
from backend.services.ap2_service import (
    compute_open_payment_mandate_hash,
    verify_ap2_chains,
)
from backend.services.crypto_mandate import (
    sign_ed25519_message,
    sign_es256_challenge,
)
from backend.services.mandate_evaluator import ledger
from backend.services.mandate_revocation_service import (
    canonical_revocation_message,
    revoke_mandate,
    verify_revocation_signature,
)
from backend.services.paypal_service import paypal_service
from backend.services.trusted_surface_service import (
    create_trusted_surface_open_mandates,
)
from backend.wallet.wallet import BuyerWallet, init_agent_key

client = TestClient(app)


def _generate_ed25519_keypair():
    from cryptography.hazmat.primitives.asymmetric import ed25519
    priv = ed25519.Ed25519PrivateKey.generate()
    pub = priv.public_key()
    return priv.private_bytes_raw().hex(), pub.public_bytes_raw().hex()


def _generate_es256_key(kid_prefix="owner-es256"):
    return JWK.generate(kty="EC", crv="P-256", kid=f"{kid_prefix}-{uuid.uuid4().hex[:8]}")


@pytest.fixture
def fake_paypal_stops(monkeypatch):
    calls = []

    async def fake_stop(subscription_id, action, reason):
        calls.append((subscription_id, action, reason))
        return {"subscription_id": subscription_id, "action": action, "mock_mode": True}

    monkeypatch.setattr(paypal_service, "stop_subscription", fake_stop)
    return calls


async def _setup_active_subscription(tmp_path, cap=60.0):
    """Enrolls owner, signs limits, and completes purchase to obtain an active subscription."""
    wdir = tmp_path / "wallet"
    agent_pub = init_agent_key(wdir)
    owner = _generate_es256_key("rev-owner")
    email = f"rev-owner-{uuid.uuid4().hex[:8]}@example.com"

    # Enforce challenge enrollment
    challenge = client.get("/api/agent/keys/challenge").json()["challenge"]
    enrolled = client.post("/api/agent/keys/register", json={
        "kid": owner.kid,
        "publicKeyJwk": owner.export_public(as_dict=True),
        "contractorEmail": email,
        "businessEntity": "Revocation Testing LLC",
        "challenge": challenge,
        "challengeSignature": sign_es256_challenge(challenge, owner),
    })
    assert enrolled.status_code == 201, enrolled.text

    limits = create_trusted_surface_open_mandates(
        buyer_email=email,
        monthly_budget_cap=cap,
        agent_key=JWK(**agent_pub),
        user_key=owner,
    )
    (wdir / "merchant_public.jwk").write_text(json.dumps(get_merchant_public_jwk()), encoding="utf-8")
    (wdir / "owner_public.jwk").write_text(owner.export_public(), encoding="utf-8")
    (wdir / "owner_limits.json").write_text(json.dumps({
        "buyer_email": email,
        "open_checkout_mandate_token": limits["open_checkout_mandate_token"],
        "open_payment_mandate_token": limits["open_payment_mandate_token"],
    }), encoding="utf-8")

    nego = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="rev-test-agent",
        tier_id="ap2-gateway",
        monthly_budget_cap=cap,
        contractor_email=email,
        buyer_email=email,
    )
    signed = BuyerWallet(wdir).sign_checkout(nego["checkout_jwt"])
    purchase = await seller_agent.purchase_subscription(
        offer_id=nego["offer_id"],
        buyer_email=email,
        checkout_mandate_chain=signed["checkout_mandate_chain"],
        payment_mandate_chain=signed["payment_mandate_chain"],
    )
    assert purchase["status"] == "ACTIVE", purchase

    m_hash = compute_open_payment_mandate_hash(limits["open_payment_mandate_token"])
    return {
        "sub_id": purchase["subscription_id"],
        "email": email,
        "owner": owner,
        "limits": limits,
        "nego": nego,
        "signed": signed,
        "mandate_hash": m_hash,
        "checkout_hash": nego["checkout_hash"],
        "offer_id": nego["offer_id"],
    }


# ── 1. Cryptographic Signature Verification & Anti-Tamper ──────────────────


def test_ed25519_revocation_signature_verification():
    priv_hex, pub_hex = _generate_ed25519_keypair()
    kid = f"ed25519-owner-{uuid.uuid4().hex[:8]}"
    register_buyer_key(kid, pub_hex, contractor_email="ed25519@example.com", allow_overwrite=True)

    m_hash = "abc123hash" * 6
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    reason = "Compromised agent private key"

    msg = canonical_revocation_message(m_hash, ts, reason)
    sig = sign_ed25519_message(msg, priv_hex)

    # 1. Valid signature
    valid, res = verify_revocation_signature(m_hash, kid, ts, reason, sig)
    assert valid is True
    assert res == "VERIFIED"

    # 2. Tampered signature
    bad_sig = ("00" if sig[:2] != "00" else "11") + sig[2:]
    valid, res = verify_revocation_signature(m_hash, kid, ts, reason, bad_sig)
    assert valid is False
    assert "SIGNATURE_VERIFICATION_FAILED" in res

    # 3. Tampered reason
    valid, res = verify_revocation_signature(m_hash, kid, ts, "Tampered reason", sig)
    assert valid is False
    assert "SIGNATURE_VERIFICATION_FAILED" in res

    # 4. Tampered timestamp
    valid, res = verify_revocation_signature(m_hash, kid, "2026-01-01T00:00:00Z", reason, sig)
    assert valid is False
    assert "SIGNATURE_VERIFICATION_FAILED" in res

    # 5. Unknown kid
    valid, res = verify_revocation_signature(m_hash, "unknown-kid", ts, reason, sig)
    assert valid is False
    assert "KEY_NOT_FOUND" in res


def test_es256_revocation_signature_verification():
    owner = _generate_es256_key("owner-p256")
    register_buyer_key(owner.kid, json.dumps(owner.export_public(as_dict=True)), contractor_email="es256@example.com", allow_overwrite=True)

    m_hash = "fedcba9876" * 6
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    reason = "Manual contract termination"

    msg = canonical_revocation_message(m_hash, ts, reason)
    sig = sign_es256_challenge(msg, owner)

    # 1. Valid signature
    valid, res = verify_revocation_signature(m_hash, owner.kid, ts, reason, sig)
    assert valid is True
    assert res == "VERIFIED"

    # 2. Tampered signature
    valid, res = verify_revocation_signature(m_hash, owner.kid, ts, reason, "deadbeef" * 8)
    assert valid is False
    assert "SIGNATURE_VERIFICATION_FAILED" in res or "MALFORMED" in res


# ── 2. Revoke Mandate Service Execution & Auto-Cancellation ─────────────────


@pytest.mark.asyncio
async def test_revoke_mandate_auto_cancels_subscription_and_reconciles_ledger(tmp_path, fake_paypal_stops):
    setup = await _setup_active_subscription(tmp_path, cap=60.0)
    sub_id = setup["sub_id"]
    email = setup["email"]
    owner = setup["owner"]
    m_hash = setup["mandate_hash"]
    checkout_hash = setup["checkout_hash"]

    # Verify initially active
    assert _COMPLETED_SUBSCRIPTIONS[sub_id]["status"] == "ACTIVE"
    cap = ledger.get_saved_cap(email) or 60.0
    rem = ledger.get_remaining_budget(agent_id="rev-test-agent", cap=cap, contractor_email=email)
    assert round(rem, 2) == round(cap - 49.99, 2)

    # Owner signs revocation
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    reason = "Emergency revocation: credential leaked"
    msg = canonical_revocation_message(checkout_hash, ts, reason)
    sig = sign_es256_challenge(msg, owner)

    rev_res = await revoke_mandate(
        mandate_proof_hash=checkout_hash,
        kid=owner.kid,
        reason=reason,
        signature=sig,
        timestamp_iso=ts,
    )
    assert rev_res["status"] == "REVOKED"
    assert rev_res["mandate_proof_hash"] == checkout_hash
    assert sub_id in rev_res["cancelled_subscriptions"]

    # Verify status in database
    assert is_mandate_revoked(checkout_hash) is True
    rec = get_mandate_revocation(checkout_hash)
    assert rec is not None
    assert rec["reason"] == reason
    assert rec["revoked_by_kid"] == owner.kid

    # Verify subscription auto-cancelled locally and PayPal stop called
    assert _COMPLETED_SUBSCRIPTIONS[sub_id]["status"] == "CANCELLED"
    assert _COMPLETED_SUBSCRIPTIONS[sub_id]["node_status"] == "CANCELLED"
    assert len(fake_paypal_stops) == 1
    assert fake_paypal_stops[0][0] == sub_id
    assert fake_paypal_stops[0][1] == "cancel"

    # Verify ledger commitment released back to full budget
    rem_after = ledger.get_remaining_budget(agent_id="rev-test-agent", cap=cap, contractor_email=email)
    assert round(rem_after, 2) == round(cap, 2)


# ── 3. Purchase Path Enforcement (Fail-Closed Against Revoked Mandates) ─────


@pytest.mark.asyncio
async def test_verify_ap2_chains_fails_closed_when_mandate_is_revoked(tmp_path):
    setup = await _setup_active_subscription(tmp_path)
    signed = setup["signed"]
    chk_jwt = setup["nego"]["checkout_jwt"]
    checkout_hash = setup["checkout_hash"]
    owner = setup["owner"]

    # Revoke checkout_hash
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    msg = canonical_revocation_message(checkout_hash, ts, "Revoked for audit")
    sig = sign_es256_challenge(msg, owner)
    await revoke_mandate(checkout_hash, owner.kid, "Revoked for audit", sig, ts)

    # Calling verify_ap2_chains should fail closed immediately
    res = verify_ap2_chains(
        checkout_mandate_token=signed["checkout_mandate_chain"],
        payment_mandate_token=signed["payment_mandate_chain"],
        checkout_jwt=chk_jwt,
        buyer_email=setup["email"],
    )
    assert res["valid"] is False
    assert res["error"] == "MANDATE_REVOKED"
    assert "revoked" in res["error_description"].lower()
    assert res["checkout_receipt"] is not None
    assert res["payment_receipt"] is not None


@pytest.mark.asyncio
async def test_seller_agent_purchase_rejected_on_revoked_mandate(tmp_path):
    setup = await _setup_active_subscription(tmp_path)
    signed = setup["signed"]
    nego = setup["nego"]
    offer_id = setup["offer_id"]
    owner = setup["owner"]

    # Revoke the offer_id
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    msg = canonical_revocation_message(offer_id, ts, "Revoking offer")
    sig = sign_es256_challenge(msg, owner)
    await revoke_mandate(offer_id, owner.kid, "Revoking offer", sig, ts)

    purchase_res = await seller_agent.purchase_subscription(
        offer_id=offer_id,
        buyer_email=setup["email"],
        checkout_mandate_chain=signed["checkout_mandate_chain"],
        payment_mandate_chain=signed["payment_mandate_chain"],
    )
    assert purchase_res["status"] == "REJECTED"
    assert purchase_res["error"] == "MANDATE_REVOKED"
    assert "MANDATE_REVOKED" in purchase_res["reason"]


# ── 4. REST API Endpoint Tests ──────────────────────────────────────────────


def test_mandate_revocation_endpoints():
    priv_hex, pub_hex = _generate_ed25519_keypair()
    kid = f"api-rev-owner-{uuid.uuid4().hex[:8]}"
    register_buyer_key(kid, pub_hex, contractor_email="api-rev@example.com", allow_overwrite=True)

    m_hash = f"hash-{uuid.uuid4().hex}"
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    reason = "API Revocation Test"
    msg = canonical_revocation_message(m_hash, ts, reason)
    sig = sign_ed25519_message(msg, priv_hex)

    # 1. Invalid signature -> 401
    bad_res = client.post("/api/mandates/revoke", json={
        "mandate_proof_hash": m_hash,
        "kid": kid,
        "reason": reason,
        "timestamp_iso": ts,
        "signature": "00" * 64,
    })
    assert bad_res.status_code == 401
    assert bad_res.json()["detail"]["error"] == "REVOCATION_FAILED"

    # 2. Unknown key -> 401
    unk_res = client.post("/api/mandates/revoke", json={
        "mandate_proof_hash": m_hash,
        "kid": "non-existent-kid",
        "reason": reason,
        "timestamp_iso": ts,
        "signature": sig,
    })
    assert unk_res.status_code == 401

    # 3. Valid revocation -> 200 OK
    ok_res = client.post("/api/mandates/revoke", json={
        "mandate_proof_hash": m_hash,
        "kid": kid,
        "reason": reason,
        "timestamp_iso": ts,
        "signature": sig,
    })
    assert ok_res.status_code == 200
    data = ok_res.json()
    assert data["status"] == "REVOKED"
    assert data["mandate_proof_hash"] == m_hash
    assert data["revoked_by_kid"] == kid

    # 4. GET /api/mandates/revocations
    list_res = client.get("/api/mandates/revocations")
    assert list_res.status_code == 200
    revs = list_res.json()["revocations"]
    assert any(r["mandate_proof_hash"] == m_hash for r in revs)

    # 5. GET /api/mandates/revocations/{hash}
    get_res = client.get(f"/api/mandates/revocations/{m_hash}")
    assert get_res.status_code == 200
    assert get_res.json()["revoked"] is True
    assert get_res.json()["revocation"]["reason"] == reason

    # 6. GET /api/mandates/revocations/{unrevoked} -> 404
    not_found_res = client.get("/api/mandates/revocations/non-existent-hash")
    assert not_found_res.status_code == 404
