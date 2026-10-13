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
from backend.database import save_subscription, get_buyer_identity, get_subscription
from backend.config import settings
from backend.agents.seller_agent import _COMPLETED_SUBSCRIPTIONS

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

