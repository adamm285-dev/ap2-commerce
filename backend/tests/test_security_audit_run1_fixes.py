"""
Regression tests for Security Audit Run-1 findings (NV-01 through NV-16).
"""

import datetime
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from jwcrypto.jwk import JWK

import backend.server as server_module
from backend.agents.seller_agent import _COMPLETED_SUBSCRIPTIONS, seller_agent
from backend.api.m2m_audit import record_m2m_artifacts
from backend.config import settings
from backend.database import (
    get_connection,
    get_open_mandate_total_usage,
    get_recurring_charge,
    get_recurring_mandate,
    get_subscription,
    is_mandate_revoked,
    list_dispatch_slots,
    record_dispatch_slot,
    record_open_mandate_settlement,
    record_recurring_charge,
    register_buyer_key,
    register_vault_payment_source,
)
from backend.server import app
from backend.services.ap2_gateway_service import Ap2GatewayService
from backend.services.ap2_keys import get_merchant_public_jwk
from backend.services.ap2_service import (
    compute_open_payment_mandate_hash,
    create_closed_mandate_chains,
    verify_ap2_chains,
)
from backend.services.backoffice.webhook_dispatcher import is_url_permitted
from backend.services.crypto_mandate import sign_es256_challenge
from backend.services.mandate_revocation_service import (
    canonical_revocation_message,
    revoke_mandate,
)
from backend.services.marketplace_payout_service import marketplace_payout_service
from backend.services.paypal_oidc_service import PayPalOidcService
from backend.services.paypal_service import paypal_service
from backend.services.trusted_surface_service import create_trusted_surface_open_mandates
from backend.wallet.wallet import BuyerWallet, init_agent_key

client = TestClient(app)


def _new_p256_key(prefix: str) -> JWK:
    return JWK.generate(kty="EC", crv="P-256", kid=f"{prefix}-{uuid.uuid4().hex[:8]}")


def _enroll_p256_key(key: JWK, email: str) -> None:
    challenge = client.get("/api/agent/keys/challenge").json()["challenge"]
    res = client.post(
        "/api/agent/keys/register",
        json={
            "kid": key.kid,
            "publicKeyJwk": key.export_public(as_dict=True),
            "contractorEmail": email,
            "businessEntity": "Audit Run1 Corp",
            "challenge": challenge,
            "challengeSignature": sign_es256_challenge(challenge, key),
        },
    )
    assert res.status_code == 201, res.text


def _post_signed_webhook(event_type: str, resource: dict, event_id: str | None = None):
    raw = json.dumps(
        {
            "id": event_id or f"WH-{uuid.uuid4().hex}",
            "event_type": event_type,
            "resource": resource,
        }
    )
    sig = paypal_service.generate_mock_webhook_signature(raw)
    res = client.post(
        "/api/paypal/webhook",
        content=raw,
        headers={"Content-Type": "application/json", "PAYPAL-TRANSMISSION-SIG": sig},
    )
    return res.status_code, res.json()


# ── NV-13: Cross-chain root kid and holder cnf binding ───────────────────────


@pytest.mark.asyncio
async def test_nv13_cross_chain_kid_and_cnf_mismatch_rejected():
    email = f"nv13-{uuid.uuid4().hex[:8]}@example.com"
    owner_a = _new_p256_key("owner-a")
    owner_b = _new_p256_key("owner-b")
    agent_a = _new_p256_key("agent-a")
    agent_b = _new_p256_key("agent-b")
    _enroll_p256_key(owner_a, email)
    _enroll_p256_key(owner_b, email)

    nego = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="nv13-agent",
        tier_id="ap2-batch",
        monthly_budget_cap=60.0,
        contractor_email=email,
        buyer_email=email,
    )

    # Case 1: Different root owner keys across checkout vs payment chains
    limits_a = create_trusted_surface_open_mandates(
        buyer_email=email, monthly_budget_cap=60.0, user_key=owner_a, agent_key=agent_a
    )
    limits_b = create_trusted_surface_open_mandates(
        buyer_email=email, monthly_budget_cap=60.0, user_key=owner_b, agent_key=agent_a
    )
    closed_mixed_root = create_closed_mandate_chains(
        open_checkout_token=limits_a["open_checkout_mandate_token"],
        open_payment_token=limits_b["open_payment_mandate_token"],
        checkout_jwt=nego["checkout_jwt"],
        nonce=nego["nonce"],
        agent_key=agent_a,
    )
    res_root = verify_ap2_chains(
        checkout_mandate_token=closed_mixed_root["checkout_mandate_chain"],
        payment_mandate_token=closed_mixed_root["payment_mandate_chain"],
        checkout_jwt=nego["checkout_jwt"],
        buyer_email=email,
    )
    assert res_root["valid"] is False
    assert "CROSS_CHAIN_KEY_MISMATCH" in (res_root.get("error_description") or "")

    # Case 2: Same root owner key, different holder cnf agent keys
    limits_cnf_a = create_trusted_surface_open_mandates(
        buyer_email=email, monthly_budget_cap=60.0, user_key=owner_a, agent_key=agent_a
    )
    limits_cnf_b = create_trusted_surface_open_mandates(
        buyer_email=email, monthly_budget_cap=60.0, user_key=owner_a, agent_key=agent_b
    )
    closed_a = create_closed_mandate_chains(
        open_checkout_token=limits_cnf_a["open_checkout_mandate_token"],
        open_payment_token=limits_cnf_a["open_payment_mandate_token"],
        checkout_jwt=nego["checkout_jwt"],
        nonce=nego["nonce"],
        agent_key=agent_a,
    )
    closed_b = create_closed_mandate_chains(
        open_checkout_token=limits_cnf_b["open_checkout_mandate_token"],
        open_payment_token=limits_cnf_b["open_payment_mandate_token"],
        checkout_jwt=nego["checkout_jwt"],
        nonce=nego["nonce"],
        agent_key=agent_b,
    )
    res_cnf = verify_ap2_chains(
        checkout_mandate_token=closed_a["checkout_mandate_chain"],
        payment_mandate_token=closed_b["payment_mandate_chain"],
        checkout_jwt=nego["checkout_jwt"],
        buyer_email=email,
    )
    assert res_cnf["valid"] is False
    assert "CROSS_CHAIN_CNF_MISMATCH" in (res_cnf.get("error_description") or "")


# ── NV-12: Budget.max dollars vs AmountRange.max cents unit distinction ──────


@pytest.mark.asyncio
async def test_nv12_budget_max_dollars_not_divided_by_100():
    email = f"nv12-{uuid.uuid4().hex[:8]}@example.com"
    owner = _new_p256_key("owner-nv12")
    agent = _new_p256_key("agent-nv12")
    _enroll_p256_key(owner, email)

    # Monthly cap = $80.00 (8000 cents), yearly ceiling = $60.00 (60.0 dollars in Budget.max)
    limits = create_trusted_surface_open_mandates(
        buyer_email=email,
        monthly_budget_cap=80.0,
        yearly_budget_ceiling=60.0,
        user_key=owner,
        agent_key=agent,
    )
    nego = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="nv12-agent",
        tier_id="ap2-batch",
        monthly_budget_cap=80.0,
        contractor_email=email,
        buyer_email=email,
    )
    closed = create_closed_mandate_chains(
        open_checkout_token=limits["open_checkout_mandate_token"],
        open_payment_token=limits["open_payment_mandate_token"],
        checkout_jwt=nego["checkout_jwt"],
        nonce=nego["nonce"],
        agent_key=agent,
    )
    res = verify_ap2_chains(
        checkout_mandate_token=closed["checkout_mandate_chain"],
        payment_mandate_token=closed["payment_mandate_chain"],
        checkout_jwt=nego["checkout_jwt"],
        buyer_email=email,
    )
    assert res["valid"] is True
    # min($80.00 from AmountRange(max=8000), $60.00 from Budget(max=60.0)) == 60.0 (not 0.60!)
    assert res["authoritative_budget_cap"] == 60.0


# ── NV-11: Direct charge gateway includes recurring renewals & lease check ───


@pytest.mark.asyncio
async def test_nv11_direct_charge_includes_recurring_renewals():
    email = f"nv11-{uuid.uuid4().hex[:8]}@example.com"
    owner = _new_p256_key("owner-nv11")
    agent = _new_p256_key("agent-nv11")
    _enroll_p256_key(owner, email)
    register_vault_payment_source("vault_nv11_src", owner.kid)

    # Total budget ceiling = $120.00; monthly cap = $60.00
    limits = create_trusted_surface_open_mandates(
        buyer_email=email,
        monthly_budget_cap=60.0,
        yearly_budget_ceiling=120.0,
        user_key=owner,
        agent_key=agent,
    )
    open_pay_hash = compute_open_payment_mandate_hash(limits["open_payment_mandate_token"])

    # Simulate an existing subscription with 1 initial settlement ($49.99) + 1 renewal ($49.99) = $99.98 used
    sub_id = f"I-NV11-{uuid.uuid4().hex[:8].upper()}"
    record_open_mandate_settlement(open_pay_hash, sub_id, 4999)
    record_recurring_charge(
        sale_id=f"SALE-NV11-{uuid.uuid4().hex[:6]}",
        subscription_id=sub_id,
        mandate_hash=open_pay_hash,
        amount_cents=4999,
        currency="USD",
        status="VERIFIED",
        reason="Month 2 renewal",
        charged_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    )

    # Attempt a direct charge of $49.99 ($99.98 + $49.99 = $149.97 > $120.00 ceiling)
    nego = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="nv11-agent",
        tier_id="ap2-batch",
        monthly_budget_cap=60.0,
        contractor_email=email,
        buyer_email=email,
    )
    closed = create_closed_mandate_chains(
        open_checkout_token=limits["open_checkout_mandate_token"],
        open_payment_token=limits["open_payment_mandate_token"],
        checkout_jwt=nego["checkout_jwt"],
        nonce=nego["nonce"],
        agent_key=agent,
    )
    with pytest.raises(ValueError, match="exceeds budget limit"):
        Ap2GatewayService.process_direct_charge(
            cart_mandate_jwt=closed["checkout_mandate_chain"],
            payment_mandate_jwt=closed["payment_mandate_chain"],
            buyer_key_id=owner.kid,
            payment_source_id="vault_nv11_src",
            metadata={"checkout_jwt": nego["checkout_jwt"]},
        )


# ── NV-01: APPROVAL_PENDING registers recurring mandate & reserves budget ─────


@pytest.mark.asyncio
async def test_nv01_approval_pending_registers_recurring_mandate_and_reserves_budget(tmp_path, monkeypatch):
    wdir = tmp_path / "wallet_nv01"
    agent_pub = init_agent_key(wdir)
    owner = _new_p256_key("owner-nv01")
    email = f"nv01-{uuid.uuid4().hex[:8]}@example.com"
    _enroll_p256_key(owner, email)

    # Ceiling = $60.00 (only 1 subscription of $49.99 fits)
    limits = create_trusted_surface_open_mandates(
        buyer_email=email,
        monthly_budget_cap=60.0,
        yearly_budget_ceiling=60.0,
        user_key=owner,
        agent_key=JWK(**agent_pub),
    )
    (wdir / "merchant_public.jwk").write_text(json.dumps(get_merchant_public_jwk()), encoding="utf-8")
    (wdir / "owner_public.jwk").write_text(owner.export_public(), encoding="utf-8")
    (wdir / "owner_limits.json").write_text(
        json.dumps(
            {
                "buyer_email": email,
                "open_checkout_mandate_token": limits["open_checkout_mandate_token"],
                "open_payment_mandate_token": limits["open_payment_mandate_token"],
            }
        ),
        encoding="utf-8",
    )

    async def pending_create_sub(**kwargs):
        sid = f"I-NV01-PEND-{uuid.uuid4().hex[:8].upper()}"
        return {
            "subscription_id": sid,
            "id": sid,
            "status": "APPROVAL_PENDING",
            "plan_id": kwargs.get("plan_id") or "P-AP2-BATCH-WORKER",
            "approval_url": f"https://www.sandbox.paypal.com/webapps/billing/subscriptions?ba_token={sid}",
            "links": [{"rel": "approve", "href": f"https://www.sandbox.paypal.com/webapps/billing/subscriptions?ba_token={sid}"}],
            "mock_mode": False,
        }

    monkeypatch.setattr(paypal_service, "create_subscription", pending_create_sub)

    nego1 = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="nv01-agent", tier_id="ap2-batch", monthly_budget_cap=60.0, contractor_email=email, buyer_email=email
    )
    signed1 = BuyerWallet(wdir).sign_checkout(nego1["checkout_jwt"])
    purchase1 = await seller_agent.purchase_subscription(
        offer_id=nego1["offer_id"],
        buyer_email=email,
        checkout_mandate_chain=signed1["checkout_mandate_chain"],
        payment_mandate_chain=signed1["payment_mandate_chain"],
    )
    assert purchase1["status"] == "APPROVAL_PENDING"
    sub_id = purchase1["subscription_id"]

    # 1. Recurring mandate is registered with status APPROVAL_PENDING
    rec = get_recurring_mandate(sub_id)
    assert rec is not None
    assert rec["status"] == "APPROVAL_PENDING"
    open_pay_hash = compute_open_payment_mandate_hash(limits["open_payment_mandate_token"])
    assert rec["mandate_hash"] == open_pay_hash

    # 2. Usage is reserved while APPROVAL_PENDING
    used_cents, used_count = get_open_mandate_total_usage(open_pay_hash)
    assert used_cents == 4999
    assert used_count == 1

    # 3. Upon BILLING.SUBSCRIPTION.ACTIVATED webhook, settlement is recorded under open_pay_hash
    code, _ = _post_signed_webhook("BILLING.SUBSCRIPTION.ACTIVATED", {"id": sub_id})
    assert code == 200
    assert get_recurring_mandate(sub_id)["status"] == "ACTIVE"
    used_cents_after, used_count_after = get_open_mandate_total_usage(open_pay_hash)
    assert used_cents_after == 4999
    assert used_count_after == 1


# ── NV-15: Revocation tombstones all linked hashes & cancels by open_pay_hash


@pytest.mark.asyncio
async def test_nv15_revoke_by_checkout_hash_tombstones_open_payment_mandate(tmp_path):
    wdir = tmp_path / "wallet_nv15"
    agent_pub = init_agent_key(wdir)
    owner = _new_p256_key("owner-nv15")
    email = f"nv15-{uuid.uuid4().hex[:8]}@example.com"
    _enroll_p256_key(owner, email)

    limits = create_trusted_surface_open_mandates(
        buyer_email=email, monthly_budget_cap=100.0, user_key=owner, agent_key=JWK(**agent_pub)
    )
    (wdir / "merchant_public.jwk").write_text(json.dumps(get_merchant_public_jwk()), encoding="utf-8")
    (wdir / "owner_public.jwk").write_text(owner.export_public(), encoding="utf-8")
    (wdir / "owner_limits.json").write_text(
        json.dumps(
            {
                "buyer_email": email,
                "open_checkout_mandate_token": limits["open_checkout_mandate_token"],
                "open_payment_mandate_token": limits["open_payment_mandate_token"],
            }
        ),
        encoding="utf-8",
    )

    nego = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="nv15-agent", tier_id="ap2-batch", monthly_budget_cap=100.0, contractor_email=email, buyer_email=email
    )
    signed = BuyerWallet(wdir).sign_checkout(nego["checkout_jwt"])
    purchase = await seller_agent.purchase_subscription(
        offer_id=nego["offer_id"],
        buyer_email=email,
        checkout_mandate_chain=signed["checkout_mandate_chain"],
        payment_mandate_chain=signed["payment_mandate_chain"],
    )
    assert purchase["status"] == "ACTIVE"

    # Owner revokes by checkout_hash
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    reason = "Revoke checkout and linked open mandate"
    msg = canonical_revocation_message(nego["checkout_hash"], ts, reason)
    sig = sign_es256_challenge(msg, owner)
    rev = await revoke_mandate(nego["checkout_hash"], owner.kid, reason, sig, ts)
    assert rev["status"] == "REVOKED"
    assert purchase["subscription_id"] in rev["cancelled_subscriptions"]

    # Root open_payment_mandate_hash must ALSO be tombstoned so agent cannot reuse it on a new offer
    open_pay_hash = compute_open_payment_mandate_hash(limits["open_payment_mandate_token"])
    assert is_mandate_revoked(open_pay_hash) is True


# ── NV-10 & NV-09: Reserved kid whitespace bypass & OIDC audience check ──────


def test_nv10_reserved_kid_and_whitespace_padding_rejected():
    key = _new_p256_key("temp")
    challenge = client.get("/api/agent/keys/challenge").json()["challenge"]
    sig = sign_es256_challenge(challenge, key)

    for bad_kid in ("demo-human-trusted-surface", "  demo-human-trusted-surface  ", "ap2-merchant-key-1"):
        res = client.post(
            "/api/agent/keys/register",
            json={
                "kid": bad_kid,
                "publicKeyJwk": key.export_public(as_dict=True),
                "contractorEmail": "nv10@example.com",
                "businessEntity": "NV10 Corp",
                "challenge": challenge,
                "challengeSignature": sig,
            },
        )
        assert res.status_code == 403
        assert res.json()["detail"]["error"] == "RESERVED_KEY_ID"


def test_nv09_oidc_verify_enforces_audience_claim():
    bad_aud_token = PayPalOidcService.generate_mock_oidc_token(
        payer_id="PAYER-NV09",
        email="nv09@example.com",
        client_id="other-relying-party-client-id",
    )
    with pytest.raises(ValueError, match="AUDIENCE_MISMATCH"):
        PayPalOidcService.verify_oidc_identity_attestation(bad_aud_token)


# ── NV-05, NV-07, NV-08: Webhook stop failure, reactivation guard, refund cap


@pytest.mark.asyncio
async def test_nv05_nv07_nv08_webhook_hardening(tmp_path, monkeypatch):
    wdir = tmp_path / "wallet_wh"
    agent_pub = init_agent_key(wdir)
    owner = _new_p256_key("owner-wh")
    email = f"wh-{uuid.uuid4().hex[:8]}@example.com"
    _enroll_p256_key(owner, email)

    limits = create_trusted_surface_open_mandates(
        buyer_email=email, monthly_budget_cap=60.0, user_key=owner, agent_key=JWK(**agent_pub)
    )
    (wdir / "merchant_public.jwk").write_text(json.dumps(get_merchant_public_jwk()), encoding="utf-8")
    (wdir / "owner_public.jwk").write_text(owner.export_public(), encoding="utf-8")
    (wdir / "owner_limits.json").write_text(
        json.dumps(
            {
                "buyer_email": email,
                "open_checkout_mandate_token": limits["open_checkout_mandate_token"],
                "open_payment_mandate_token": limits["open_payment_mandate_token"],
            }
        ),
        encoding="utf-8",
    )

    nego = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="wh-agent", tier_id="ap2-batch", monthly_budget_cap=60.0, contractor_email=email, buyer_email=email
    )
    signed = BuyerWallet(wdir).sign_checkout(nego["checkout_jwt"])
    purchase = await seller_agent.purchase_subscription(
        offer_id=nego["offer_id"],
        buyer_email=email,
        checkout_mandate_chain=signed["checkout_mandate_chain"],
        payment_mandate_chain=signed["payment_mandate_chain"],
    )
    sub_id = purchase["subscription_id"]
    open_pay_hash = compute_open_payment_mandate_hash(limits["open_payment_mandate_token"])

    # 1. Initial sale + duplicate refunds (NV-08)
    sale1_id = f"SALE-WH1-{uuid.uuid4().hex[:6].upper()}"
    code1, _ = _post_signed_webhook(
        "PAYMENT.SALE.COMPLETED",
        {
            "id": sale1_id,
            "billing_agreement_id": sub_id,
            "amount": {"total": "49.99", "currency": "USD"},
            "create_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        },
    )
    assert code1 == 200

    # Two partial/duplicate refunds of $40.00 each against a $49.99 sale -> total refund capped at $49.99
    ref1 = f"REF-1-{uuid.uuid4().hex[:6].upper()}"
    ref2 = f"REF-2-{uuid.uuid4().hex[:6].upper()}"
    for r_id in (ref1, ref2):
        _post_signed_webhook(
            "PAYMENT.SALE.REFUNDED",
            {
                "id": r_id,
                "sale_id": sale1_id,
                "billing_agreement_id": sub_id,
                "amount": {"total": "40.00", "currency": "USD"},
            },
        )
    assert get_recurring_charge(ref1)["amount_cents"] == -4000
    assert get_recurring_charge(ref2)["amount_cents"] == -999
    used_cents, used_count = get_open_mandate_total_usage(open_pay_hash)
    assert used_cents == 0
    assert used_count == 1  # Refunds do not increment occurrence count

    # 2. Failed PayPal stop halts local state and allows retry of same event/sale (NV-05)
    async def fail_once(s_id, action, reason):
        raise RuntimeError("PayPal network timeout")

    monkeypatch.setattr(paypal_service, "stop_subscription", fail_once)
    sale2_id = f"SALE-OVER-{uuid.uuid4().hex[:6].upper()}"
    evt_over = f"WH-OVER-{uuid.uuid4().hex}"
    code_over, body_over = _post_signed_webhook(
        "PAYMENT.SALE.COMPLETED",
        {
            "id": sale2_id,
            "billing_agreement_id": sub_id,
            "amount": {"total": "99.99", "currency": "USD"},
            "create_time": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)).isoformat(),
        },
        event_id=evt_over,
    )
    assert code_over == 200
    assert body_over["recurring_check"]["action_result"] == "FAILED"
    assert _COMPLETED_SUBSCRIPTIONS[sub_id]["status"] == "CANCELLED"
    assert get_recurring_mandate(sub_id)["status"] == "STOP_FAILED"

    # Now PayPal recovers and the same webhook event is retried
    stopped_calls = []

    async def succeed_stop(s_id, action, reason):
        stopped_calls.append((s_id, action))
        return {"subscription_id": s_id, "action": action, "mock_mode": True}

    monkeypatch.setattr(paypal_service, "stop_subscription", succeed_stop)
    code_retry, body_retry = _post_signed_webhook(
        "PAYMENT.SALE.COMPLETED",
        {
            "id": sale2_id,
            "billing_agreement_id": sub_id,
            "amount": {"total": "99.99", "currency": "USD"},
            "create_time": (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)).isoformat(),
        },
        event_id=evt_over,
    )
    assert code_retry == 200
    assert body_retry["recurring_check"]["action_result"] == "DONE"
    assert stopped_calls == [(sub_id, "cancel")]
    assert get_recurring_mandate(sub_id)["status"] == "CANCELLED"

    # 3. Cancelled subscription cannot be resurrected by RE-ACTIVATED or ACTIVATED webhook (NV-07)
    _post_signed_webhook("BILLING.SUBSCRIPTION.RE-ACTIVATED", {"id": sub_id})
    assert _COMPLETED_SUBSCRIPTIONS[sub_id]["status"] == "CANCELLED"
    _post_signed_webhook("BILLING.SUBSCRIPTION.ACTIVATED", {"id": sub_id})
    assert _COMPLETED_SUBSCRIPTIONS[sub_id]["status"] == "CANCELLED"


# ── NV-03, NV-04, NV-02, NV-14, NV-16, NV-06: Tier 3 Hardening ───────────────


@pytest.mark.asyncio
async def test_nv03_nv04_provision_and_dispatch_do_not_leak_email_and_enforce_live_guard(monkeypatch):
    sub_id = f"I-NV04-{uuid.uuid4().hex[:8].upper()}"
    secret_email = "secret-victim-owner@enterprise.com"
    _COMPLETED_SUBSCRIPTIONS[sub_id] = {
        "subscription_id": sub_id,
        "status": "ACTIVE",
        "buyer_email": secret_email,
        "contractor_email": secret_email,
        "agreed_monthly_rate": 49.99,
        "tier_id": "ap2-batch",
    }

    # 1. provision_compute_node with wrong email must NOT leak secret_email in reason
    mismatch_res = await seller_agent.provision_compute_node(
        subscription_id=sub_id,
        buyer_email="attacker@evil.com",
    )
    assert mismatch_res["status"] == "REJECTED"
    assert mismatch_res["error"] == "IDENTITY_MISMATCH_DETECTED"
    assert secret_email not in json.dumps(mismatch_res)

    # 2. dispatch_zapier_mcp without buyer_email masks contractor_email in returned erpPayload
    disp_res = await seller_agent.dispatch_zapier_mcp(subscription_id=sub_id)
    assert disp_res["status"] == "COMPLETED"
    assert secret_email not in json.dumps(disp_res)

    # 3. dispatch_zapier_mcp in live mode rejects with ADMIN_AUTH_REQUIRED
    monkeypatch.setattr(settings, "mock_external_apis", False)
    live_res = await seller_agent.dispatch_zapier_mcp(subscription_id=sub_id, buyer_email=secret_email)
    assert live_res["status"] == "REJECTED"
    assert live_res["error"] == "ADMIN_AUTH_REQUIRED"


def test_nv02_nv14_m2m_audit_live_auth_and_loopback_ssrf_blocked(monkeypatch):
    # NV-14: Loopback and localhost are blocked even when mock_external_apis=True
    assert not is_url_permitted("http://127.0.0.1:8001/api/paypal/webhook")
    assert not is_url_permitted("http://[::1]:8001/api/paypal/webhook")
    assert not is_url_permitted("http://localhost:8001/api/paypal/webhook")

    # NV-02: M2M payloads endpoint redacts response_body in mock mode and requires admin in live mode
    record_m2m_artifacts(
        mandate_hash="hash-nv02-12345678",
        paypal_sub_id="I-NV02-SUB",
        node_endpoint="mcp+https://gateway.example.com",
        erp_payload={"status": "ROUTED"},
        qbo_payload={"payload": {}},
        webhook_meta={
            "signature": "sha256=sec",
            "response_body": "INTERNAL_SECRET_BANNER",
            "target_url": "https://hooks.zapier.com/hooks/catch/secret",
            "headers": {"X-AP2-Signature": "sha256=sec"},
        },
    )
    pub_res = client.get("/m2m/payloads/latest")
    assert pub_res.status_code == 200
    assert pub_res.json()["webhook_meta"]["response_body"] is None
    assert pub_res.json()["webhook_meta"]["target_url"] is None

    monkeypatch.setattr(settings, "mock_external_apis", False)
    live_unauth = client.get("/m2m/payloads/latest")
    assert live_unauth.status_code == 401


@pytest.mark.asyncio
async def test_nv16_payout_deduplication_beyond_100_rows():
    now_month = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")
    target_sub_id = f"I-NV16-TARGET-{uuid.uuid4().hex[:6].upper()}"
    _COMPLETED_SUBSCRIPTIONS[target_sub_id] = {
        "subscription_id": target_sub_id,
        "status": "ACTIVE",
        "agreed_monthly_rate": 49.99,
        "tier_id": "ap2-batch",
        "contractor_email": "nv16@example.com",
        "created_at": f"{now_month}-01T00:00:00Z",
    }

    # Insert target_sub_id's payout item FIRST, then 105 newer payout items so target_sub_id is at offset > 100
    conn = get_connection()
    with conn:
        conn.execute(
            """
            INSERT INTO payout_items (
                item_id, batch_id, operator_id, subscription_id,
                receiver_email, gross_amount_cents, platform_fee_cents, net_payout_cents,
                currency, status, paypal_transaction_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"item_{now_month}_{target_sub_id.replace('-', '_')}",
                "batch_nv16_0",
                "op_lambda_gpu",
                target_sub_id,
                "payouts-lambda@example.com",
                4999,
                750,
                4249,
                "USD",
                "SUCCESS",
                "TXN-NV16-0",
                f"{now_month}-01T00:00:01Z",
            ),
        )
        for i in range(105):
            conn.execute(
                """
                INSERT INTO payout_items (
                    item_id, batch_id, operator_id, subscription_id,
                    receiver_email, gross_amount_cents, platform_fee_cents, net_payout_cents,
                    currency, status, paypal_transaction_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"item_{now_month}_FILLER_{i:03d}",
                    "batch_nv16_filler",
                    "op_lambda_gpu",
                    f"I-FILLER-{i:03d}",
                    "payouts-lambda@example.com",
                    4999,
                    750,
                    4249,
                    "USD",
                    "SUCCESS",
                    f"TXN-FILL-{i:03d}",
                    f"{now_month}-02T00:{i // 60:02d}:{i % 60:02d}Z",
                ),
            )
    conn.close()

    res = await marketplace_payout_service.execute_fleet_payout_batch(
        cycle_id=now_month,
        subscription_ids=[target_sub_id],
        dry_run=False,
    )
    assert res["status"] == "IDEMPOTENT_NOOP"


def test_nv06_dispatch_slot_deduplicates_by_job_id():
    job_id = f"job_ap2_nv06_{uuid.uuid4().hex[:8]}"
    record_dispatch_slot({"job_id": job_id, "territory_zone": "Zone 1 - US-East", "slot_start_iso": "2026-10-15T10:00:00Z"})
    record_dispatch_slot({"job_id": job_id, "territory_zone": "Zone 2 - US-Central", "slot_start_iso": "2026-10-15T12:00:00Z"})
    slots = [s for s in list_dispatch_slots() if s.get("job_id") == job_id]
    assert len(slots) == 1
    assert slots[0]["territory_zone"] == "Zone 2 - US-Central"
