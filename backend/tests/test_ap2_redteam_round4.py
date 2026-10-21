"""
Round 4 independent red-team findings (proof-of-concept regression tests).

Each test asserts the SECURE behaviour. Tests marked xfail(strict=True) document a
vulnerability that is still open: they fail today because the attack succeeds.
When a fix lands the test starts passing, strict xfail turns that into a failure,
and the marker must be removed so the test guards the fix.
"""

import asyncio
import base64
import datetime
import hashlib
import hmac
import json
import uuid

import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from jwcrypto.jwk import JWK

from backend.server import app
from backend.services.crypto_mandate import sign_es256_challenge
from backend.services.mandate_revocation_service import (
    canonical_revocation_message,
    revoke_mandate,
)
from backend.services.marketplace_payout_service import marketplace_payout_service
from backend.services.paypal_service import paypal_service
from backend.services.paypal_oidc_service import PayPalOidcService
from backend.database import save_subscription, get_buyer_identity, get_subscription, record_direct_charge, get_connection
from backend.config import settings
from backend.agents.seller_agent import _COMPLETED_SUBSCRIPTIONS
from backend.tests.ap2_test_utils import build_test_ap2_chains, setup_test_vault
from backend.services.ap2_gateway_service import Ap2GatewayService
from backend.services.ap2_service import create_merchant_checkout

client = TestClient(app)


def _key(prefix: str) -> JWK:
    return JWK.generate(kty="EC", crv="P-256", kid=f"{prefix}-{uuid.uuid4().hex[:8]}")


def _enroll(key: JWK, email: str) -> None:
    challenge = client.get("/api/agent/keys/challenge").json()["challenge"]
    res = client.post("/api/agent/keys/register", json={
        "kid": key.kid,
        "publicKeyJwk": key.export_public(as_dict=True),
        "contractorEmail": email,
        "businessEntity": "Red Team Round 4 LLC",
        "challenge": challenge,
        "challengeSignature": sign_es256_challenge(challenge, key),
    })
    assert res.status_code == 201, res.text


def _victim_sub(email: str, proof_hash: str) -> str:
    from backend.agents.seller_agent import _COMPLETED_SUBSCRIPTIONS

    sub_id = f"I-RT4-{uuid.uuid4().hex[:8].upper()}"
    sub = {
        "subscription_id": sub_id,
        "contractor_email": email,
        "mandate_proof_hash": proof_hash,
        "status": "ACTIVE",
    }
    save_subscription(dict(sub))
    _COMPLETED_SUBSCRIPTIONS[sub_id] = sub
    return sub_id


async def _signed_revoke(key: JWK, target: str):
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    sig = sign_es256_challenge(canonical_revocation_message(target, now_iso, "rt4"), key)
    return await revoke_mandate(
        mandate_proof_hash=target, kid=key.kid, reason="rt4", signature=sig, timestamp_iso=now_iso,
    )


# ─────────────────────────────────────────────────────────────────────────────
# F1. Revocation prefix match + fail-open ownership => mass cancellation
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rt4_prefix_revocation_cannot_cancel_other_tenants():
    victim_email = f"victim-{uuid.uuid4().hex[:6]}@enterprise.com"
    shared = uuid.uuid4().hex[:6]
    victim_subs = [
        _victim_sub(victim_email, f"{shared}{uuid.uuid4().hex}"),
        _victim_sub(victim_email, f"{shared}{uuid.uuid4().hex}"),
    ]

    attacker = _key("rt4-attacker")
    _enroll(attacker, f"attacker-{uuid.uuid4().hex[:6]}@evil.com")

    # Short prefix must be rejected
    try:
        res = await _signed_revoke(attacker, shared)
    except ValueError:
        pass
    else:
        assert not set(victim_subs) & set(res.get("cancelled_subscriptions", []))

    # 16+ char random hash with no registered owner must fail closed (F1: MANDATE_NOT_FOUND)
    random_hash = f"unowned_{uuid.uuid4().hex}"
    with pytest.raises(ValueError, match="MANDATE_NOT_FOUND"):
        await _signed_revoke(attacker, random_hash)


# ─────────────────────────────────────────────────────────────────────────────
# F2. Self-service key enrollment accepts any email unverified => revoke as victim
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rt4_unverified_email_claim_cannot_revoke_victim_mandate():
    victim_email = f"victim-{uuid.uuid4().hex[:6]}@enterprise.com"
    proof = f"victim_hash_{uuid.uuid4().hex}"
    sub_id = _victim_sub(victim_email, proof)

    impostor = _key("rt4-impostor")
    _enroll(impostor, victim_email)  # no OIDC, unverified email claim

    # Impostor attempts to attest without key possession (F5 chain into F2)
    forged_oidc = PayPalOidcService.generate_mock_oidc_token(payer_id=f"PAYER-{uuid.uuid4().hex[:8].upper()}", email=victim_email)
    attest_res = client.post("/api/agent/identity/attest", json={"kid": impostor.kid, "oidc_id_token": forged_oidc})
    assert attest_res.status_code in (401, 403)

    # Impostor attempts to revoke victim's mandate
    try:
        res = await _signed_revoke(impostor, proof)
    except ValueError:
        return
    assert sub_id not in res.get("cancelled_subscriptions", [])


# ─────────────────────────────────────────────────────────────────────────────
# F3. Concurrent payout batches double-disburse (dedupe read -> await PayPal -> write)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rt4_concurrent_payout_batches_pay_once(monkeypatch):
    sub_id = f"I-RT4-PAY-{uuid.uuid4().hex[:8].upper()}"
    save_subscription({
        "subscription_id": sub_id,
        "contractor_email": "payer@example.com",
        "agreed_monthly_rate": 49.99,
        "status": "ACTIVE",
    })

    paid_items = []
    real = paypal_service.create_payout_batch

    async def slow_batch(*args, **kwargs):
        paid_items.extend(i["sender_item_id"] for i in kwargs.get("items", []))
        await asyncio.sleep(0.05)
        return await real(*args, **kwargs)

    monkeypatch.setattr(paypal_service, "create_payout_batch", slow_batch)
    month = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")
    cycle = f"{month}-{uuid.uuid4().hex[:8]}"

    await asyncio.gather(
        marketplace_payout_service.execute_fleet_payout_batch(cycle_id=cycle, subscription_ids=[sub_id]),
        marketplace_payout_service.execute_fleet_payout_batch(cycle_id=cycle, subscription_ids=[sub_id]),
        return_exceptions=True,
    )
    assert len(paid_items) == 1, f"PayPal was asked to pay {len(paid_items)} times: {paid_items}"


@pytest.mark.asyncio
async def test_rt4_relabelled_cycle_does_not_repay():
    sub_id = f"I-RT4-CYC-{uuid.uuid4().hex[:8].upper()}"
    save_subscription({
        "subscription_id": sub_id,
        "contractor_email": "payer@example.com",
        "agreed_monthly_rate": 49.99,
        "status": "ACTIVE",
    })
    month = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")
    first = await marketplace_payout_service.execute_fleet_payout_batch(cycle_id=month, subscription_ids=[sub_id])
    assert first["item_count"] == 1

    # 1. Relabelled cycle with suffix (e.g. 2026-10-again) normalizes to month and skips settled subscription
    second = await marketplace_payout_service.execute_fleet_payout_batch(cycle_id=f"{month}-again", subscription_ids=[sub_id])
    assert second["item_count"] == 0

    # 2. Cycle without month prefix (e.g. relabel01) is strictly rejected
    with pytest.raises(ValueError, match="INVALID_CYCLE_ID"):
        await marketplace_payout_service.execute_fleet_payout_batch(cycle_id="relabel01", subscription_ids=[sub_id])

    # 3. Future cycle (e.g. 2099-12) is strictly rejected
    with pytest.raises(ValueError, match="FUTURE_CYCLE_ID"):
        await marketplace_payout_service.execute_fleet_payout_batch(cycle_id="2099-12", subscription_ids=[sub_id])


# ─────────────────────────────────────────────────────────────────────────────
# F4. Unauthenticated operator registration chooses its own split and claims nodes
# ─────────────────────────────────────────────────────────────────────────────

def test_rt4_unauthenticated_operator_cannot_set_own_split():
    tag = uuid.uuid4().hex[:10]
    res = client.post("/api/marketplace/operators/register", json={
        "name": "Totally Legit Compute",
        "email": f"thief-{tag}@evil.com",
        "assigned_nodes": ["batch"],  # matched as a substring of node IDs
        "split_bps": 10000,           # 100% to operator, 0% platform fee
    })
    assert res.status_code in (401, 403)


# ─────────────────────────────────────────────────────────────────────────────
# F5. OIDC: verifier uses a hard-coded HS256 secret; attest endpoint needs no key proof
# ─────────────────────────────────────────────────────────────────────────────

def _forge_oidc(claims: dict) -> str:
    enc = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
    h = enc(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    p = enc(json.dumps(claims).encode())  # json.dumps emits Infinity for float('inf')
    sig = hmac.new(b"mock-paypal-oidc-secret-key-32bytes", f"{h}.{p}".encode(), hashlib.sha256).digest()
    return f"{h}.{p}.{enc(sig)}"


def test_rt4_identity_attest_requires_key_possession():
    # Use random key name and random payer ID to guarantee no string-matching games
    rand_prefix = f"victim-{uuid.uuid4().hex[:8]}"
    victim = _key(rand_prefix)
    victim_email = f"victim-{uuid.uuid4().hex[:6]}@enterprise.com"
    _enroll(victim, victim_email)

    rand_payer = f"EVIL-PAYER-{uuid.uuid4().hex[:8].upper()}"
    forged = PayPalOidcService.generate_mock_oidc_token(payer_id=rand_payer, email=victim_email)
    res = client.post("/api/agent/identity/attest", json={"kid": victim.kid, "oidc_id_token": forged})
    identity = get_buyer_identity(victim.kid) or {}
    assert res.status_code in (401, 403)
    assert identity.get("payer_id") != rand_payer


def test_rt4_oidc_rejects_non_finite_exp():
    token = _forge_oidc({
        "iss": "https://www.paypal.com",
        "sub": "PAYER-RT4",
        "email": "rt4@example.com",
        "email_verified": True,
        "exp": float("inf"),
    })
    with pytest.raises(ValueError):
        PayPalOidcService.verify_oidc_identity_attestation(token)


# ─────────────────────────────────────────────────────────────────────────────
# F2 & Live OIDC Verification Gates
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rt4_self_attested_impostor_cannot_revoke():
    """
    Gap 1 (F2): In mock mode, impostor enrolls with victim's email, self-attests with a forged
    mock OIDC token (proving key possession + HS256 mock secret), and attempts to revoke victim's
    mandate. Must fail closed with UNAUTHORIZED_REVOCATION (HTTP 403), leaving victim ACTIVE.
    """
    victim_email = f"victim-{uuid.uuid4().hex[:8]}@enterprise.com"
    mandate_hash = f"mandate_proof_{uuid.uuid4().hex}"
    victim_key = _key("victim-orig")
    sub_id = f"I-VIC-{uuid.uuid4().hex[:8].upper()}"

    # Store verified root token in recurring_mandates (authentic production purchase path)
    from backend.database import save_recurring_mandate
    v_hdr = base64.urlsafe_b64encode(json.dumps({"alg": "ES256", "kid": victim_key.kid, "typ": "JWT"}).encode()).rstrip(b"=").decode()
    v_pay = base64.urlsafe_b64encode(json.dumps({"iss": victim_email, "sub": victim_email}).encode()).rstrip(b"=").decode()
    v_token = f"{v_hdr}.{v_pay}.mock_sig"
    save_recurring_mandate(
        subscription_id=sub_id,
        mandate_hash=mandate_hash,
        open_payment_mandate_token=v_token,
        buyer_email=victim_email,
        agreed_amount_cents=4999,
        currency="USD",
    )
    sub = {
        "subscription_id": sub_id,
        "contractor_email": victim_email,
        "mandate_proof_hash": mandate_hash,
        "status": "ACTIVE",
    }
    save_subscription(dict(sub))
    _COMPLETED_SUBSCRIPTIONS[sub_id] = sub

    # Impostor enrolls key with victim email (no OIDC yet)
    impostor = _key("impostor")
    _enroll(impostor, victim_email)

    # Impostor self-attests with key possession & forged mock OIDC token
    challenge = client.get("/api/agent/keys/challenge").json()["challenge"]
    chal_sig = sign_es256_challenge(challenge, impostor)
    payer_id = f"PAYER-{uuid.uuid4().hex[:8].upper()}"
    oidc_token = PayPalOidcService.generate_mock_oidc_token(payer_id=payer_id, email=victim_email, nonce=challenge)
    attest_resp = client.post(
        "/api/agent/identity/attest",
        json={
            "kid": impostor.kid,
            "oidc_id_token": oidc_token,
            "challenge": challenge,
            "challenge_signature": chal_sig,
        },
    )
    assert attest_resp.status_code == 200
    ident = get_buyer_identity(impostor.kid) or {}
    assert ident.get("identity_attested") is True

    # Impostor attempts to revoke victim's mandate via REST API -> must fail 403
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    msg = canonical_revocation_message(mandate_hash, now_iso, "Impostor revocation attempt")
    impostor_sig = sign_es256_challenge(msg, impostor)

    rev_resp = client.post(
        "/api/mandates/revoke",
        json={
            "mandate_proof_hash": mandate_hash,
            "kid": impostor.kid,
            "reason": "Impostor revocation attempt",
            "signature": impostor_sig,
            "timestamp_iso": now_iso,
        },
    )
    assert rev_resp.status_code == 403
    detail = rev_resp.json()["detail"]
    assert detail["error"] == "REVOCATION_FAILED"
    assert "UNAUTHORIZED_REVOCATION" in detail["reason"]

    # Also test direct service call fails closed
    with pytest.raises(ValueError, match="UNAUTHORIZED_REVOCATION"):
        await revoke_mandate(
            mandate_proof_hash=mandate_hash,
            kid=impostor.kid,
            reason="Impostor revocation attempt",
            signature=impostor_sig,
            timestamp_iso=now_iso,
        )

    # Victim subscription must remain ACTIVE
    cur_sub = get_subscription(sub_id)
    assert cur_sub["status"] == "ACTIVE"
    assert _COMPLETED_SUBSCRIPTIONS[sub_id]["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_rt4_signing_key_can_revoke_own_mandate():
    """
    Legitimate owner key that signed the mandate can revoke it directly.
    Verified via authentic recurring_mandates root token rather than hand-injected owner_kid.
    Also verifies that a buyer key containing 'seller' in its ID (e.g. bookseller-key) is NOT
    falsely treated as a seller key.
    """
    from backend.database import save_recurring_mandate

    # 1. Standard owner key
    k1 = _key("owner-k1")
    k1_email = f"owner-{uuid.uuid4().hex[:8]}@example.com"
    _enroll(k1, k1_email)

    sub_id = f"I-K1-{uuid.uuid4().hex[:8].upper()}"
    mandate_hash = f"mandate_proof_k1_{uuid.uuid4().hex}"

    hdr_b64 = base64.urlsafe_b64encode(json.dumps({"alg": "ES256", "kid": k1.kid, "typ": "JWT"}).encode()).rstrip(b"=").decode()
    pay_b64 = base64.urlsafe_b64encode(json.dumps({"iss": k1_email, "sub": k1_email}).encode()).rstrip(b"=").decode()
    mock_token = f"{hdr_b64}.{pay_b64}.mock_sig"

    save_recurring_mandate(
        subscription_id=sub_id,
        mandate_hash=mandate_hash,
        open_payment_mandate_token=mock_token,
        buyer_email=k1_email,
        agreed_amount_cents=4999,
        currency="USD",
    )
    sub = {
        "subscription_id": sub_id,
        "contractor_email": k1_email,
        "mandate_proof_hash": mandate_hash,
        "status": "ACTIVE",
    }
    save_subscription(dict(sub))
    _COMPLETED_SUBSCRIPTIONS[sub_id] = sub

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    msg = canonical_revocation_message(mandate_hash, now_iso, "Owner revocation")
    sig = sign_es256_challenge(msg, k1)

    rev_resp = client.post(
        "/api/mandates/revoke",
        json={
            "mandate_proof_hash": mandate_hash,
            "kid": k1.kid,
            "reason": "Owner revocation",
            "signature": sig,
            "timestamp_iso": now_iso,
        },
    )
    assert rev_resp.status_code == 200
    data = rev_resp.json()
    assert data["status"] == "REVOKED"
    assert sub_id in data["cancelled_subscriptions"]

    cur_sub = get_subscription(sub_id)
    assert cur_sub["status"] == "CANCELLED"
    assert _COMPLETED_SUBSCRIPTIONS[sub_id]["status"] == "CANCELLED"

    # 2. Buyer key with "seller" in its name (e.g. bookseller-agent) is NOT rejected
    bookseller_key = _key("bookseller-agent")
    bookseller_email = f"bookseller-{uuid.uuid4().hex[:8]}@example.com"
    _enroll(bookseller_key, bookseller_email)

    bs_sub_id = f"I-BOOK-{uuid.uuid4().hex[:8].upper()}"
    bs_mandate_hash = f"mandate_proof_bs_{uuid.uuid4().hex}"
    bs_hdr = base64.urlsafe_b64encode(json.dumps({"alg": "ES256", "kid": bookseller_key.kid, "typ": "JWT"}).encode()).rstrip(b"=").decode()
    bs_token = f"{bs_hdr}.{pay_b64}.mock_sig"

    save_recurring_mandate(
        subscription_id=bs_sub_id,
        mandate_hash=bs_mandate_hash,
        open_payment_mandate_token=bs_token,
        buyer_email=bookseller_email,
        agreed_amount_cents=4999,
        currency="USD",
    )
    bs_sub = {
        "subscription_id": bs_sub_id,
        "contractor_email": bookseller_email,
        "mandate_proof_hash": bs_mandate_hash,
        "status": "ACTIVE",
    }
    save_subscription(dict(bs_sub))
    _COMPLETED_SUBSCRIPTIONS[bs_sub_id] = bs_sub

    bs_msg = canonical_revocation_message(bs_mandate_hash, now_iso, "Bookseller legitimate revocation")
    bs_sig = sign_es256_challenge(bs_msg, bookseller_key)

    bs_rev_resp = client.post(
        "/api/mandates/revoke",
        json={
            "mandate_proof_hash": bs_mandate_hash,
            "kid": bookseller_key.kid,
            "reason": "Bookseller legitimate revocation",
            "signature": bs_sig,
            "timestamp_iso": now_iso,
        },
    )
    assert bs_rev_resp.status_code == 200
    assert bs_sub_id in bs_rev_resp.json()["cancelled_subscriptions"]
    assert get_subscription(bs_sub_id)["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_rt4_admin_can_revoke(monkeypatch):
    """
    Mandates with no recorded signing key (legacy seeded subscriptions) fail closed
    against non-admin callers (403), but succeed when signed with an admin key (200).
    """
    legacy_email = f"legacy-{uuid.uuid4().hex[:8]}@example.com"
    sub_id = f"I-LEGACY-{uuid.uuid4().hex[:8].upper()}"
    mandate_hash = f"mandate_proof_legacy_{uuid.uuid4().hex}"
    sub = {
        "subscription_id": sub_id,
        "contractor_email": legacy_email,
        "mandate_proof_hash": mandate_hash,
        "status": "ACTIVE",
    }
    save_subscription(dict(sub))
    _COMPLETED_SUBSCRIPTIONS[sub_id] = sub

    caller_key = _key("caller-key")
    _enroll(caller_key, legacy_email)

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    msg = canonical_revocation_message(mandate_hash, now_iso, "Admin emergency revoke")
    sig = sign_es256_challenge(msg, caller_key)

    # 1. Non-admin request must be rejected (403 UNAUTHORIZED_REVOCATION)
    non_admin_resp = client.post(
        "/api/mandates/revoke",
        json={
            "mandate_proof_hash": mandate_hash,
            "kid": caller_key.kid,
            "reason": "Admin emergency revoke",
            "signature": sig,
            "timestamp_iso": now_iso,
        },
    )
    assert non_admin_resp.status_code == 403
    assert "UNAUTHORIZED_REVOCATION" in non_admin_resp.json()["detail"]["reason"]
    assert get_subscription(sub_id)["status"] == "ACTIVE"

    # 2. Admin request with valid ADMIN_API_KEY must succeed (200)
    admin_secret = f"admin-key-{uuid.uuid4().hex}"
    monkeypatch.setattr(settings, "admin_api_key", admin_secret)

    admin_resp = client.post(
        "/api/mandates/revoke",
        headers={"X-Admin-Key": admin_secret},
        json={
            "mandate_proof_hash": mandate_hash,
            "kid": caller_key.kid,
            "reason": "Admin emergency revoke",
            "signature": sig,
            "timestamp_iso": now_iso,
        },
    )
    assert admin_resp.status_code == 200
    data = admin_resp.json()
    assert data["status"] == "REVOKED"
    assert sub_id in data["cancelled_subscriptions"]

    cur_sub = get_subscription(sub_id)
    assert cur_sub["status"] == "CANCELLED"
    assert _COMPLETED_SUBSCRIPTIONS[sub_id]["status"] == "CANCELLED"


def test_rt4_live_mode_rejects_mock_oidc(monkeypatch):
    """
    Gap 2: When settings.mock_external_apis is False, HS256 mock tokens must be rejected
    with LIVE_OIDC_NOT_CONFIGURED (HTTP 400, never 500), even if env MOCK_EXTERNAL_APIS is 'true'.
    """
    monkeypatch.setattr(settings, "mock_external_apis", False)
    monkeypatch.setenv("MOCK_EXTERNAL_APIS", "true")

    key = _key("live-guard")
    email = f"live-guard-{uuid.uuid4().hex[:8]}@example.com"
    _enroll(key, email)

    challenge = client.get("/api/agent/keys/challenge").json()["challenge"]
    chal_sig = sign_es256_challenge(challenge, key)
    token = PayPalOidcService.generate_mock_oidc_token(payer_id="PAYER-LIVE", email=email, nonce=challenge)

    # 1. POST /api/agent/identity/attest
    attest_resp = client.post(
        "/api/agent/identity/attest",
        json={
            "kid": key.kid,
            "oidc_id_token": token,
            "challenge": challenge,
            "challenge_signature": chal_sig,
        },
    )
    assert attest_resp.status_code == 400
    detail = attest_resp.json()["detail"]
    assert detail["error"] == "LIVE_OIDC_NOT_CONFIGURED"
    assert "LIVE_OIDC_NOT_CONFIGURED" in detail["reason"]

    ident = get_buyer_identity(key.kid) or {}
    assert not ident.get("identity_attested")

    # 2. POST /api/agent/keys/register with oidcIdToken in live mode
    reg_key = _key("live-reg")
    reg_chal = client.get("/api/agent/keys/challenge").json()["challenge"]
    reg_sig = sign_es256_challenge(reg_chal, reg_key)
    reg_token = PayPalOidcService.generate_mock_oidc_token(payer_id="PAYER-LIVE-REG", email=email, nonce=reg_chal)

    reg_resp = client.post(
        "/api/agent/keys/register",
        json={
            "kid": reg_key.kid,
            "publicKeyJwk": reg_key.export_public(as_dict=True),
            "contractorEmail": email,
            "businessEntity": "Live Mode Corp",
            "challenge": reg_chal,
            "challengeSignature": reg_sig,
            "oidcIdToken": reg_token,
        },
    )
    assert reg_resp.status_code == 400
    reg_detail = reg_resp.json()["detail"]
    assert reg_detail["error"] == "LIVE_OIDC_NOT_CONFIGURED"
    assert "LIVE_OIDC_NOT_CONFIGURED" in reg_detail["reason"]


# ─────────────────────────────────────────────────────────────────────────────
# Latent Security Hardening Tests: Concurrency, Payment Source Binding, XSS
# ─────────────────────────────────────────────────────────────────────────────

def test_rt4_direct_charge_unique_mandate_constraint_and_concurrency():
    """
    Direct charges must enforce an absolute UNIQUE constraint on mandate_id at the SQLite level,
    and concurrent / repeated capture requests must fail closed with 409 REPLAY_DETECTED.
    """
    mandate_id = f"ord_uniq_{uuid.uuid4().hex[:10]}"
    # 1. First insert succeeds
    rec1 = record_direct_charge({
        "charge_id": f"chg_{uuid.uuid4().hex[:10]}",
        "mandate_id": mandate_id,
        "buyer_key_id": "test-buyer",
        "amount_cents": 4999,
        "currency": "USD",
        "payee_id": "payee_1",
        "payment_source_id": "vault_paypal_token_default",
        "paypal_capture_id": f"CAP-{uuid.uuid4().hex[:8].upper()}",
        "status": "CAPTURED",
        "merchant_receipt_jwt": f"jwt_{uuid.uuid4().hex[:8]}",
    })
    assert rec1["mandate_id"] == mandate_id

    # 2. Duplicate insert with identical mandate_id fails with REPLAY_DETECTED
    with pytest.raises(ValueError, match="REPLAY_DETECTED"):
        record_direct_charge({
            "charge_id": f"chg_{uuid.uuid4().hex[:10]}",
            "mandate_id": mandate_id,
            "buyer_key_id": "test-buyer-2",
            "amount_cents": 4999,
            "currency": "USD",
            "payee_id": "payee_1",
            "payment_source_id": "vault_paypal_token_default",
            "paypal_capture_id": f"CAP-{uuid.uuid4().hex[:8].upper()}",
            "status": "CAPTURED",
            "merchant_receipt_jwt": f"jwt_{uuid.uuid4().hex[:8]}",
        })

    # 3. HTTP Gateway endpoint rejects replayed charge with 409 REPLAY_DETECTED
    u_replay = uuid.uuid4().hex[:8]
    replay_email = f"buyer-replay-{u_replay}@example.com"
    owner_replay = _key("replay")
    _enroll(owner_replay, replay_email)
    vault_replay = setup_test_vault(client, owner_replay)

    chains = build_test_ap2_chains(
        tier_id="ap2-batch",
        monthly_price=49.99,
        buyer_email=replay_email,
        owner_key=owner_replay,
        vault_id=vault_replay,
    )
    req = {
        "cartMandateJwt": chains["checkout_mandate_chain"],
        "paymentMandateJwt": chains["payment_mandate_chain"],
    }
    resp1 = client.post("/v1/ap2/gateway/charges", json=req)
    assert resp1.status_code == 201

    resp2 = client.post("/v1/ap2/gateway/charges", json=req)
    assert resp2.status_code == 409
    assert resp2.json()["detail"]["error"] == "REPLAY_DETECTED"


def test_rt4_payment_source_authorization_and_mandate_instrument_binding():
    """
    Direct rail payment sources are cryptographically authorized by the verified AP2 payment mandate.
    (a) An attacker with a different registered key naming the victim's registered vault id in their own mandate is rejected with 403 UNAUTHORIZED_PAYMENT_SOURCE.
    (b) An unregistered vault id in a mandate is rejected with 403 UNAUTHORIZED_PAYMENT_SOURCE.
    (c) The owner's mandate naming its own registered vault succeeds with 201 CAPTURED, and records the signed instrument id as payment_source_id.
    """
    # 1. Setup Victim owner key and register victim vault via setup_test_vault
    u_vic = uuid.uuid4().hex[:8]
    vic_email = f"victim-{u_vic}@example.com"
    victim_key = _key("victim")
    _enroll(victim_key, vic_email)
    victim_vault_id = setup_test_vault(client, victim_key)

    # 2. Setup Honest owner key and register honest vault via setup_test_vault
    u_hon = uuid.uuid4().hex[:8]
    hon_email = f"honest-{u_hon}@example.com"
    honest_key = _key("honest")
    _enroll(honest_key, hon_email)
    honest_vault_id = setup_test_vault(client, honest_key)

    # 3. Setup Attacker owner key and register attacker vault via setup_test_vault
    u_att = uuid.uuid4().hex[:8]
    att_email = f"attacker-{u_att}@example.com"
    attacker_key = _key("attacker")
    _enroll(attacker_key, att_email)
    attacker_vault_id = setup_test_vault(client, attacker_key)

    # (c) The owner's mandate naming its own registered vault -> 201 CAPTURED
    honest_chains = build_test_ap2_chains(
        tier_id="ap2-gateway",
        monthly_price=79.99,
        budget_cap=200.0,
        buyer_email=hon_email,
        owner_key=honest_key,
        vault_id=honest_vault_id,
    )
    resp_honest = client.post(
        "/v1/ap2/gateway/charges",
        json={
            "cartMandateJwt": honest_chains["checkout_mandate_chain"],
            "paymentMandateJwt": honest_chains["payment_mandate_chain"],
            "buyerKeyId": honest_key.kid,
            "paymentSourceId": honest_vault_id,
        },
    )
    assert resp_honest.status_code == 201
    honest_data = resp_honest.json()
    assert honest_data["status"] == "CAPTURED"
    assert honest_data["paymentSourceId"] == honest_vault_id
    charge_record = Ap2GatewayService.get_charge(honest_data["chargeId"])
    assert charge_record is not None
    assert charge_record["payment_source_id"] == honest_vault_id

    # Honest charge omitting paymentSourceId also resolves and records signed instrument ID
    u_hon2 = uuid.uuid4().hex[:8]
    hon2_email = f"honest2-{u_hon2}@example.com"
    honest_key_2 = _key("honest2")
    _enroll(honest_key_2, hon2_email)
    honest_vault_id_2 = setup_test_vault(client, honest_key_2)

    honest_chains_2 = build_test_ap2_chains(
        tier_id="ap2-gateway",
        monthly_price=79.99,
        budget_cap=200.0,
        buyer_email=hon2_email,
        owner_key=honest_key_2,
        vault_id=honest_vault_id_2,
    )
    resp_honest_2 = client.post(
        "/v1/ap2/gateway/charges",
        json={
            "cartMandateJwt": honest_chains_2["checkout_mandate_chain"],
            "paymentMandateJwt": honest_chains_2["payment_mandate_chain"],
            "buyerKeyId": honest_key_2.kid,
        },
    )
    assert resp_honest_2.status_code == 201
    honest_data_2 = resp_honest_2.json()
    assert honest_data_2["paymentSourceId"] == honest_vault_id_2
    charge_record_2 = Ap2GatewayService.get_charge(honest_data_2["chargeId"])
    assert charge_record_2 is not None
    assert charge_record_2["payment_source_id"] == honest_vault_id_2

    # (a) Attacker with a different registered key attempts to charge victim's instrument ID via attacker's OWN mandate
    attacker_steals_victim_chains = build_test_ap2_chains(
        tier_id="ap2-gateway",
        monthly_price=79.99,
        budget_cap=200.0,
        buyer_email=att_email,
        owner_key=attacker_key,
        vault_id=victim_vault_id,  # Attacker names victim's registered vault token in attacker's own signed mandate!
    )
    resp_attack_a = client.post(
        "/v1/ap2/gateway/charges",
        json={
            "cartMandateJwt": attacker_steals_victim_chains["checkout_mandate_chain"],
            "paymentMandateJwt": attacker_steals_victim_chains["payment_mandate_chain"],
            "buyerKeyId": attacker_key.kid,
            "paymentSourceId": victim_vault_id,
        },
    )
    assert resp_attack_a.status_code == 403
    assert resp_attack_a.json()["detail"]["error"] == "UNAUTHORIZED_PAYMENT_SOURCE"

    # Attacker's own mandate naming victim's vault, omitting caller paymentSourceId -> still 403
    attacker_steals_victim_chains_2 = build_test_ap2_chains(
        tier_id="ap2-gateway",
        monthly_price=79.99,
        budget_cap=200.0,
        buyer_email=att_email,
        owner_key=attacker_key,
        vault_id=victim_vault_id,
    )
    resp_attack_a_omit = client.post(
        "/v1/ap2/gateway/charges",
        json={
            "cartMandateJwt": attacker_steals_victim_chains_2["checkout_mandate_chain"],
            "paymentMandateJwt": attacker_steals_victim_chains_2["payment_mandate_chain"],
            "buyerKeyId": attacker_key.kid,
        },
    )
    assert resp_attack_a_omit.status_code == 403
    assert resp_attack_a_omit.json()["detail"]["error"] == "UNAUTHORIZED_PAYMENT_SOURCE"

    # (b) Unregistered vault id in mandate -> 403 UNAUTHORIZED_PAYMENT_SOURCE
    unregistered_vault_id = f"vault_unreg_{uuid.uuid4().hex[:12]}"
    unreg_chains = build_test_ap2_chains(
        tier_id="ap2-gateway",
        monthly_price=79.99,
        budget_cap=200.0,
        buyer_email=hon_email,
        owner_key=honest_key,
        vault_id=unregistered_vault_id,
    )
    resp_unreg = client.post(
        "/v1/ap2/gateway/charges",
        json={
            "cartMandateJwt": unreg_chains["checkout_mandate_chain"],
            "paymentMandateJwt": unreg_chains["payment_mandate_chain"],
            "buyerKeyId": honest_key.kid,
            "paymentSourceId": unregistered_vault_id,
        },
    )
    assert resp_unreg.status_code == 403
    assert resp_unreg.json()["detail"]["error"] == "UNAUTHORIZED_PAYMENT_SOURCE"

    # Caller-supplied payment_source_id that differs from the signed instrument is rejected (403)
    mismatch_chains = build_test_ap2_chains(
        tier_id="ap2-gateway",
        monthly_price=79.99,
        budget_cap=200.0,
        buyer_email=hon_email,
        owner_key=honest_key,
        vault_id=honest_vault_id,
    )
    tampered_source = f"vault_tampered_{uuid.uuid4().hex[:12]}"
    resp_mismatch_b = client.post(
        "/v1/ap2/gateway/charges",
        json={
            "cartMandateJwt": mismatch_chains["checkout_mandate_chain"],
            "paymentMandateJwt": mismatch_chains["payment_mandate_chain"],
            "buyerKeyId": honest_key.kid,
            "paymentSourceId": tampered_source,
        },
    )
    assert resp_mismatch_b.status_code == 403
    assert resp_mismatch_b.json()["detail"]["error"] == "UNAUTHORIZED_PAYMENT_SOURCE"


def test_rt4_direct_charge_missing_payment_instrument_rejected(monkeypatch):
    """
    If a closed payment mandate does not contain a valid payment_instrument,
    the gateway must fail closed and reject with 400 MISSING_PAYMENT_INSTRUMENT.
    """
    import backend.services.ap2_gateway_service as gw_module

    chains = build_test_ap2_chains(tier_id="ap2-gateway", monthly_price=79.99)
    real_verify = gw_module.verify_ap2_chains

    def fake_verify(*args, **kwargs):
        res = real_verify(*args, **kwargs)
        if res.get("valid"):
            closed = res["closed_payment_mandate"]
            closed_dict = closed.model_dump()
            closed_dict["payment_instrument"] = None
            res["closed_payment_mandate"] = closed_dict
        return res

    monkeypatch.setattr(gw_module, "verify_ap2_chains", fake_verify)

    resp = client.post(
        "/v1/ap2/gateway/charges",
        json={
            "cartMandateJwt": chains["checkout_mandate_chain"],
            "paymentMandateJwt": chains["payment_mandate_chain"],
            "buyerKeyId": chains["owner_key"].kid,
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error"] == "MISSING_PAYMENT_INSTRUMENT"


def test_rt4_vault_setup_endpoint_security():
    """
    (d) Setup endpoint /v1/ap2/vault/payment-sources rejects:
        - Bad / unissued challenge nonce (400 INVALID_CHALLENGE)
        - Reused challenge nonce (400 INVALID_CHALLENGE)
        - Key caller cannot sign for / signature from wrong key (401 INVALID_CHALLENGE_SIGNATURE)
        - Unregistered owner key ID (401 UNREGISTERED_OWNER_KEY)
    """
    u = uuid.uuid4().hex[:8]
    legit_key = _key("legit")
    _enroll(legit_key, f"legit-{u}@example.com")

    impostor_key = _key("impostor")
    _enroll(impostor_key, f"impostor-{u}@example.com")

    # 1. Bad / unissued challenge nonce -> 400 INVALID_CHALLENGE
    res_bad = client.post(
        "/v1/ap2/vault/payment-sources",
        json={
            "ownerKid": legit_key.kid,
            "challenge": f"unissued-challenge-{uuid.uuid4().hex}",
            "challengeSignature": sign_es256_challenge("fake", legit_key),
        },
    )
    assert res_bad.status_code == 400
    assert res_bad.json()["detail"]["error"] == "INVALID_CHALLENGE"

    # 2. Reused challenge nonce -> first succeeds (201), second fails (400 INVALID_CHALLENGE)
    ch_res = client.get("/api/agent/keys/challenge")
    assert ch_res.status_code == 200
    challenge = ch_res.json()["challenge"]
    sig = sign_es256_challenge(challenge, legit_key)

    res_ok = client.post(
        "/v1/ap2/vault/payment-sources",
        json={
            "ownerKid": legit_key.kid,
            "challenge": challenge,
            "challengeSignature": sig,
        },
    )
    assert res_ok.status_code == 201
    vault_id = res_ok.json()["vaultId"]
    assert vault_id.startswith("vault_")
    assert res_ok.json()["ownerKid"] == legit_key.kid

    # Replay of the exact same challenge
    res_replay = client.post(
        "/v1/ap2/vault/payment-sources",
        json={
            "ownerKid": legit_key.kid,
            "challenge": challenge,
            "challengeSignature": sig,
        },
    )
    assert res_replay.status_code == 400
    assert res_replay.json()["detail"]["error"] == "INVALID_CHALLENGE"

    # 3. Key caller cannot sign for (wrong key signature): impostor signs challenge with impostor_key but claims legit_key
    ch_res2 = client.get("/api/agent/keys/challenge")
    assert ch_res2.status_code == 200
    challenge2 = ch_res2.json()["challenge"]
    wrong_sig = sign_es256_challenge(challenge2, impostor_key)

    res_wrong_key = client.post(
        "/v1/ap2/vault/payment-sources",
        json={
            "ownerKid": legit_key.kid,
            "challenge": challenge2,
            "challengeSignature": wrong_sig,
        },
    )
    assert res_wrong_key.status_code == 401
    assert res_wrong_key.json()["detail"]["error"] == "INVALID_CHALLENGE_SIGNATURE"

    # 4. Unregistered owner key ID
    ch_res3 = client.get("/api/agent/keys/challenge")
    assert ch_res3.status_code == 200
    challenge3 = ch_res3.json()["challenge"]
    unregistered_key = _key("unreg")
    sig3 = sign_es256_challenge(challenge3, unregistered_key)

    res_unreg = client.post(
        "/v1/ap2/vault/payment-sources",
        json={
            "ownerKid": unregistered_key.kid,
            "challenge": challenge3,
            "challengeSignature": sig3,
        },
    )
    assert res_unreg.status_code == 401
    assert res_unreg.json()["detail"]["error"] == "UNREGISTERED_OWNER_KEY"


def test_rt4_bryntum_dispatch_scheduler_template_escaping():
    """
    Verifies that BryntumDispatchScheduler.tsx defines escapeHtml and sanitizes
    all dynamic record and event properties in raw HTML templates.
    """
    scheduler_file = Path("src/components/BryntumDispatchScheduler.tsx")
    assert scheduler_file.is_file()
    content = scheduler_file.read_text(encoding="utf-8")

    # escapeHtml helper must be declared
    assert "function escapeHtml" in content

    # Resource renderer must sanitize dynamic fields
    assert "${safeTitle}" in content
    assert "${safeTrade}" in content
    assert "${safeDid}" in content
    assert "${safeThroughput}" in content
    assert "${safeHealth}" in content

    # Event renderer must sanitize dynamic fields
    assert "${safeTitle}" in content
    assert "${safeBadge}" in content
    assert "${safeRawName}" in content
    assert "${safeRawDepositStatus}" in content
    assert "${safeIconCls}" in content


# =============================================================================
# Round 4 Privacy & PII Protection Tests (Unauthenticated Leaks Defense)
# =============================================================================

def test_rt4_pii_masking_identity_attestation():
    """
    GET /api/agent/identity/attestation/{kid} must never leak raw email or payerId
    to non-admins. Non-admins receive masked email, masked payerId, and claims reduced
    to {iss, email_verified}. Admins receive full unmasked data.
    """
    key = _key("owner-pii")
    raw_email = f"victim-{uuid.uuid4().hex[:8]}@privacy-domain-{uuid.uuid4().hex[:4]}.com"
    raw_payer = f"PAYER-{uuid.uuid4().hex[:10].upper()}"
    _enroll(key, raw_email)

    ch = client.get("/api/agent/keys/challenge").json()["challenge"]
    sig = sign_es256_challenge(ch, key)
    oidc_token = PayPalOidcService.generate_mock_oidc_token(
        payer_id=raw_payer,
        email=raw_email,
        nonce=ch,
    )
    attest_res = client.post("/api/agent/identity/attest", json={
        "kid": key.kid,
        "oidcIdToken": oidc_token,
        "challenge": ch,
        "challengeSignature": sig,
    })
    assert attest_res.status_code == 200

    # 1. Non-admin request
    resp_pub = client.get(f"/api/agent/identity/attestation/{key.kid}")
    assert resp_pub.status_code == 200
    assert raw_email not in resp_pub.text
    assert raw_payer not in resp_pub.text

    pub_data = resp_pub.json()
    assert pub_data["email"] != raw_email
    assert pub_data["payerId"] != raw_payer
    assert set(pub_data["claims"].keys()).issubset({"iss", "email_verified"})

    # 2. Admin request
    resp_adm = client.get(
        f"/api/agent/identity/attestation/{key.kid}",
        headers={"Authorization": f"Bearer {settings.admin_api_key}"},
    )
    assert resp_adm.status_code == 200
    assert raw_email in resp_adm.text
    assert raw_payer in resp_adm.text

    adm_data = resp_adm.json()
    assert adm_data["email"] == raw_email
    assert adm_data["payerId"] == raw_payer
    assert adm_data["claims"].get("sub") == raw_payer
    assert adm_data["claims"].get("email") == raw_email


def test_rt4_pii_masking_direct_charges():
    """
    GET /v1/ap2/gateway/charges and /v1/ap2/gateway/charges/{charge_id} must mask
    payment_source_id and buyer_key_id, and omit metadata, qbo_payload, and
    merchant_receipt_jwt for non-admins. Admins receive all fields in full.
    """
    raw_vault = f"vault_{uuid.uuid4().hex}"
    raw_buyer_kid = f"buyer-key-{uuid.uuid4().hex[:8]}"
    charge_id = f"chg_{uuid.uuid4().hex[:12]}"
    secret_receipt = f"eyJhbGciOiJFUzI1NiJ9.receipt-secret-{uuid.uuid4().hex}"
    secret_meta = f"secret-meta-{uuid.uuid4().hex}"

    record_direct_charge({
        "charge_id": charge_id,
        "mandate_id": f"mandate-{uuid.uuid4().hex[:8]}",
        "buyer_key_id": raw_buyer_kid,
        "amount_cents": 7999,
        "currency": "USD",
        "payee_id": "merchant_ap2_default",
        "payment_source_id": raw_vault,
        "paypal_capture_id": f"CAP-{uuid.uuid4().hex[:8]}",
        "status": "CAPTURED",
        "merchant_receipt_jwt": secret_receipt,
        "qbo_purchase_id": "999",
        "qbo_payload": {"Purchase": {"Id": "999", "Sensitive": "Confidential"}},
        "metadata": {"confidential_tag": secret_meta},
    })

    # 1. Non-admin single charge
    resp_pub = client.get(f"/v1/ap2/gateway/charges/{charge_id}")
    assert resp_pub.status_code == 200
    assert raw_vault not in resp_pub.text
    assert raw_buyer_kid not in resp_pub.text
    assert secret_receipt not in resp_pub.text
    assert secret_meta not in resp_pub.text

    data_pub = resp_pub.json()
    assert data_pub["paymentSourceId"] != raw_vault
    assert data_pub["buyerKeyId"] != raw_buyer_kid
    assert data_pub.get("merchantReceiptJwt") is None
    assert data_pub.get("qboPayload") is None
    assert data_pub.get("metadata") is None

    # 2. Non-admin list charges
    resp_list_pub = client.get("/v1/ap2/gateway/charges?limit=10")
    assert resp_list_pub.status_code == 200
    assert raw_vault not in resp_list_pub.text
    assert raw_buyer_kid not in resp_list_pub.text
    assert secret_receipt not in resp_list_pub.text

    # 3. Admin single charge
    resp_adm = client.get(
        f"/v1/ap2/gateway/charges/{charge_id}",
        headers={"Authorization": f"Bearer {settings.admin_api_key}"},
    )
    assert resp_adm.status_code == 200
    assert raw_vault in resp_adm.text
    assert raw_buyer_kid in resp_adm.text
    assert secret_receipt in resp_adm.text
    assert secret_meta in resp_adm.text

    data_adm = resp_adm.json()
    assert data_adm["paymentSourceId"] == raw_vault
    assert data_adm["buyerKeyId"] == raw_buyer_kid
    assert data_adm["merchantReceiptJwt"] == secret_receipt
    assert data_adm["metadata"]["confidential_tag"] == secret_meta

    # 4. Admin list charges
    resp_list_adm = client.get(
        "/v1/ap2/gateway/charges?limit=10",
        headers={"Authorization": f"Bearer {settings.admin_api_key}"},
    )
    assert resp_list_adm.status_code == 200
    assert raw_vault in resp_list_adm.text
    assert raw_buyer_kid in resp_list_adm.text


def test_rt4_pii_masking_checkout_endpoint():
    """
    GET /api/checkout/{order_id} must never return contractor_email to non-admins.
    The checkout JWT itself is returned, but contractor_email is null/omitted.
    Admins receive the unmasked contractor_email.
    """
    raw_email = f"buyer-{uuid.uuid4().hex[:8]}@checkout-test-{uuid.uuid4().hex[:4]}.com"
    chk = create_merchant_checkout("ap2-batch", 49.99, raw_email)
    order_id = chk["order_id"]

    # 1. Non-admin request
    resp_pub = client.get(f"/api/checkout/{order_id}")
    assert resp_pub.status_code == 200
    assert raw_email not in resp_pub.text
    assert chk["checkout_jwt"] not in resp_pub.text
    pub_data = resp_pub.json()
    assert pub_data["contractor_email"] is None
    assert pub_data.get("checkout_jwt") is None

    # 2. Admin request
    resp_adm = client.get(
        f"/api/checkout/{order_id}",
        headers={"Authorization": f"Bearer {settings.admin_api_key}"},
    )
    assert resp_adm.status_code == 200
    assert raw_email in resp_adm.text
    adm_data = resp_adm.json()
    assert adm_data["contractor_email"] == raw_email
    assert adm_data["checkout_jwt"] is not None


def test_rt4_pii_masking_marketplace_operators_and_payouts():
    """
    GET /api/marketplace/operators, /operators/{id}, /payouts/ledger, /payouts/batches/{id}:
    Non-admins get operator and receiver emails masked.
    Admins get them unmasked in full.
    """
    raw_op_email = f"op-{uuid.uuid4().hex[:8]}@datacenter-{uuid.uuid4().hex[:4]}.io"
    raw_receiver_email = f"payout-{uuid.uuid4().hex[:8]}@recipient-{uuid.uuid4().hex[:4]}.net"
    op_id = f"op_{uuid.uuid4().hex[:8]}"

    reg_res = client.post("/api/marketplace/operators/register", json={
        "operator_id": op_id,
        "name": "Confidential Compute Node",
        "email": raw_op_email,
        "payout_method": "PAYPAL",
        "payout_email": raw_op_email,
        "split_percentage_bps": 8500,
    })
    assert reg_res.status_code == 201

    # Seed a batch and payout item with raw_receiver_email
    batch_id = f"batch_{uuid.uuid4().hex[:8]}"
    item_id = f"item_{uuid.uuid4().hex[:8]}"
    conn = get_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO payout_batches (batch_id, sender_batch_id, batch_status, total_gross_cents, total_payout_cents, total_platform_fee_cents, currency, item_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (batch_id, f"sb-{uuid.uuid4().hex[:6]}", "SUCCESS", 5000, 4250, 750, "USD", 1, "2026-10-13T00:00:00Z", "2026-10-13T00:00:00Z"),
            )
            conn.execute(
                """
                INSERT INTO payout_items (item_id, batch_id, operator_id, subscription_id, receiver_email, gross_amount_cents, platform_fee_cents, net_payout_cents, currency, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (item_id, batch_id, op_id, f"sub-{uuid.uuid4().hex[:6]}", raw_receiver_email, 5000, 750, 4250, "USD", "SUCCESS", "2026-10-13T00:00:00Z"),
            )
    finally:
        conn.close()

    # 1. Operators list: non-admin vs admin
    resp_ops_pub = client.get("/api/marketplace/operators")
    assert resp_ops_pub.status_code == 200
    assert raw_op_email not in resp_ops_pub.text

    resp_ops_adm = client.get("/api/marketplace/operators", headers={"Authorization": f"Bearer {settings.admin_api_key}"})
    assert resp_ops_adm.status_code == 200
    assert raw_op_email in resp_ops_adm.text

    # 2. Operator detail: non-admin vs admin
    resp_op_pub = client.get(f"/api/marketplace/operators/{op_id}")
    assert resp_op_pub.status_code == 200
    assert raw_op_email not in resp_op_pub.text
    assert resp_op_pub.json()["operator"]["email"] != raw_op_email

    resp_op_adm = client.get(f"/api/marketplace/operators/{op_id}", headers={"Authorization": f"Bearer {settings.admin_api_key}"})
    assert resp_op_adm.status_code == 200
    assert raw_op_email in resp_op_adm.text
    assert resp_op_adm.json()["operator"]["email"] == raw_op_email

    # 3. Payout batch detail: non-admin vs admin
    resp_batch_pub = client.get(f"/api/marketplace/payouts/batches/{batch_id}")
    assert resp_batch_pub.status_code == 200
    assert raw_receiver_email not in resp_batch_pub.text

    resp_batch_adm = client.get(f"/api/marketplace/payouts/batches/{batch_id}", headers={"Authorization": f"Bearer {settings.admin_api_key}"})
    assert resp_batch_adm.status_code == 200
    assert raw_receiver_email in resp_batch_adm.text

    # 4. Payout ledger: non-admin vs admin
    resp_ledg_pub = client.get(f"/api/marketplace/payouts/ledger?operator_id={op_id}")
    assert resp_ledg_pub.status_code == 200
    assert raw_receiver_email not in resp_ledg_pub.text

    resp_ledg_adm = client.get(f"/api/marketplace/payouts/ledger?operator_id={op_id}", headers={"Authorization": f"Bearer {settings.admin_api_key}"})
    assert resp_ledg_adm.status_code == 200
    assert raw_receiver_email in resp_ledg_adm.text


def test_rt4_mandates_revocations_contains_no_emails():
    """
    GET /api/mandates/revocations is a public status list and must contain no emails.
    """
    resp = client.get("/api/mandates/revocations")
    assert resp.status_code == 200
    revs = resp.json().get("revocations", [])
    for r in revs:
        # Check all string values in revocation entry for email '@'
        for k, v in r.items():
            if isinstance(v, str):
                assert "@" not in v, f"Found '@' in revocation field {k}: {v}"


def test_rt4_fleet_ledger_pii_masking_without_testing_gate():
    """
    GET /api/fleet/ledger must mask paypal_sub_id and operator_email for non-admins,
    even when TESTING env var is set. Only callers with valid admin authorization
    receive unmasked values.
    """
    resp_pub = client.get("/api/fleet/ledger")
    assert resp_pub.status_code == 200
    txns_pub = resp_pub.json()["transactions"]
    for t in txns_pub:
        if t["status"] in ("ACTIVE", "ACTIVE_STREAMING"):
            assert "***" in t["paypal_sub_id"], f"Expected masked paypal_sub_id, got {t['paypal_sub_id']}"
        assert "***@" in t["operator_email"], f"Expected masked operator_email, got {t['operator_email']}"

    resp_adm = client.get(
        "/api/fleet/ledger",
        headers={"Authorization": f"Bearer {settings.admin_api_key}"},
    )
    assert resp_adm.status_code == 200
    txns_adm = resp_adm.json()["transactions"]
    active_adm = [t for t in txns_adm if t["status"] in ("ACTIVE", "ACTIVE_STREAMING")]
    assert any("***" not in t["paypal_sub_id"] for t in active_adm)
    assert any("***@" not in t["operator_email"] for t in active_adm)



