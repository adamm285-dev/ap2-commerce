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
from backend.database import save_subscription, get_buyer_identity

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

@pytest.mark.xfail(strict=True, reason="RT4-F1: short-prefix revocation by any key cancels other tenants' subscriptions")
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

    # The prefix matches no row exactly, so resolve_mandate_owner finds no owner and
    # the authorization check is skipped; startswith() then matches every victim sub.
    try:
        res = await _signed_revoke(attacker, shared)
    except ValueError:
        return  # secure: rejected
    assert not set(victim_subs) & set(res.get("cancelled_subscriptions", []))


# ─────────────────────────────────────────────────────────────────────────────
# F2. Self-service key enrollment accepts any email unverified => revoke as victim
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.xfail(strict=True, reason="RT4-F2: key enrollment binds an unverified email, bypassing revocation ownership")
@pytest.mark.asyncio
async def test_rt4_unverified_email_claim_cannot_revoke_victim_mandate():
    victim_email = f"victim-{uuid.uuid4().hex[:6]}@enterprise.com"
    proof = f"victim_hash_{uuid.uuid4().hex}"
    sub_id = _victim_sub(victim_email, proof)

    impostor = _key("rt4-impostor")
    _enroll(impostor, victim_email)  # no OIDC, no email verification

    try:
        res = await _signed_revoke(impostor, proof)
    except ValueError:
        return
    assert sub_id not in res.get("cancelled_subscriptions", [])


# ─────────────────────────────────────────────────────────────────────────────
# F3. Concurrent payout batches double-disburse (dedupe read -> await PayPal -> write)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.xfail(strict=True, reason="RT4-F3: concurrent execute_fleet_payout_batch pays the same subscription twice")
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
    cycle = f"rt4c{uuid.uuid4().hex[:8]}"

    await asyncio.gather(
        marketplace_payout_service.execute_fleet_payout_batch(cycle_id=cycle, subscription_ids=[sub_id]),
        marketplace_payout_service.execute_fleet_payout_batch(cycle_id=cycle, subscription_ids=[sub_id]),
        return_exceptions=True,
    )
    assert len(paid_items) == 1, f"PayPal was asked to pay {len(paid_items)} times: {paid_items}"


@pytest.mark.xfail(strict=True, reason="RT4-F3b: dedupe is keyed on caller-chosen cycle_id, so a new label pays again")
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
    second = await marketplace_payout_service.execute_fleet_payout_batch(cycle_id=f"{month}-again", subscription_ids=[sub_id])
    assert first["item_count"] == 1
    assert second["item_count"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# F4. Unauthenticated operator registration chooses its own split and claims nodes
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.xfail(strict=True, reason="RT4-F4: anyone can register an operator with split_bps=10000 and claim node patterns")
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


@pytest.mark.xfail(strict=True, reason="RT4-F5: anyone can re-attest another tenant's key with a forged OIDC token")
def test_rt4_identity_attest_requires_key_possession():
    victim = _key("rt4-attest-victim")
    victim_email = f"victim-{uuid.uuid4().hex[:6]}@enterprise.com"
    _enroll(victim, victim_email)

    forged = PayPalOidcService.generate_mock_oidc_token(payer_id="ATTACKER-PAYER", email=victim_email)
    res = client.post("/api/agent/identity/attest", json={"kid": victim.kid, "oidc_id_token": forged})
    identity = get_buyer_identity(victim.kid) or {}
    assert res.status_code >= 400 and identity.get("payer_id") != "ATTACKER-PAYER"


@pytest.mark.xfail(strict=True, reason="RT4-F5b: exp=Infinity (no iat) yields a never-expiring OIDC token")
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
