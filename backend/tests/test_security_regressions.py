"""
Security regression suite, maintained by the owner's independent reviewer.

Do not edit, weaken, skip, or delete these tests without the owner's approval.
If one fails, fix the code, not the test.

Tests marked KNOWN_ISSUE are open findings from review. They are expected to
fail today (strict xfail). When your fix makes one pass, pytest reports
"XPASS(strict)" as a failure: remove only that marker, in the same commit as
the fix.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import io
import json
import uuid

import pytest
from fastapi.testclient import TestClient
from jwcrypto.jwk import JWK

from ap2.sdk.generated.checkout_mandate import CheckoutMandate
from ap2.sdk.generated.payment_mandate import PaymentMandate
from ap2.sdk.generated.types.amount import Amount
from ap2.sdk.generated.types.merchant import Merchant
from ap2.sdk.generated.types.payment_instrument import PaymentInstrument
from ap2.sdk.jwt_helper import create_jwt
from ap2.sdk.mandate import MandateClient

from backend.agents import llm_buyer_agent
from backend.agents.llm_buyer_agent import BaseModelRunner, LLMBuyerAgent
from backend.agents.seller_agent import seller_agent
from backend.config import ROOT_DIR, get_db_path, settings
from backend.database import register_buyer_key
from backend.server import app
from backend.services import trusted_surface_service
from backend.services.ap2_service import (
    AP2_MERCHANT_ID,
    AP2_MERCHANT_NAME,
    create_merchant_checkout,
    verify_ap2_chains,
)
from backend.services.crypto_mandate import sign_es256_challenge
from backend.services.mandate_evaluator import ledger
from backend.services.trusted_surface_service import create_trusted_surface_open_mandates

client = TestClient(app)
SETTLED = ("ACTIVE", "APPROVAL_PENDING")


def KNOWN_ISSUE(reason: str):
    return pytest.mark.xfail(
        strict=True,
        raises=AssertionError,
        reason=f"Known open issue from review: {reason} Remove this marker in the commit that fixes it.",
    )


# ── Helpers ──────────────────────────────────────────────────────────────


def _key(prefix: str) -> JWK:
    return JWK.generate(kty="EC", crv="P-256", kid=f"{prefix}-{uuid.uuid4().hex[:8]}")


def _email(tag: str) -> str:
    return f"secreg-{tag}-{uuid.uuid4().hex[:6]}@example.com"


def _enrolled_owner(email: str) -> JWK:
    owner = _key("owner")
    register_buyer_key(
        kid=owner.kid,
        public_key_hex=owner.export_public(),
        contractor_email=email,
        business_name="Regression Owner LLC",
    )
    return owner


def _limits(email, owner, agent, monthly_cap, yearly=None, tiers=None):
    return create_trusted_surface_open_mandates(
        buyer_email=email,
        monthly_budget_cap=monthly_cap,
        yearly_budget_ceiling=yearly,
        allowed_tiers=tiers,
        agent_key=agent,
        user_key=owner,
    )


def _close(limits, agent, tier, price, email):
    """Merchant issues a checkout; the agent closes both mandates against it."""
    rec = create_merchant_checkout(tier, price, email)
    mc = MandateClient()
    chk = mc.present(
        holder_key=agent,
        mandate_token=limits["open_checkout_mandate_token"],
        payloads=[CheckoutMandate(vct="mandate.checkout.1", checkout_jwt=rec["checkout_jwt"], checkout_hash=rec["checkout_hash"])],
        aud=AP2_MERCHANT_ID,
        nonce=rec["nonce"],
    )
    pay = mc.present(
        holder_key=agent,
        mandate_token=limits["open_payment_mandate_token"],
        payloads=[
            PaymentMandate(
                vct="mandate.payment.1",
                transaction_id=rec["checkout_hash"],
                payment_amount=Amount(amount=int(round(price * 100)), currency="USD"),
                payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
                payment_instrument=PaymentInstrument(type="paypal_vault", id="vault-regression"),
            )
        ],
        aud=AP2_MERCHANT_ID,
        nonce=rec["nonce"],
    )
    return rec, chk, pay


def _verify(rec, chk, pay, email):
    return verify_ap2_chains(
        chk, pay, rec["checkout_jwt"],
        expected_aud=AP2_MERCHANT_ID, expected_nonce=rec["nonce"], buyer_email=email,
    )


def _run(coro):
    with contextlib.redirect_stdout(io.StringIO()):
        return asyncio.run(coro)


def _purchase(rec, chk, pay, tier, price, email):
    return _run(seller_agent.purchase_subscription(
        tier_id=tier, agreed_monthly_rate=price,
        checkout_mandate_chain=chk, payment_mandate_chain=pay,
        checkout_jwt=rec["checkout_jwt"], buyer_email=email, nonce=rec["nonce"],
    ))


def _buy(limits, agent, tier, price, email):
    rec, chk, pay = _close(limits, agent, tier, price, email)
    return _purchase(rec, chk, pay, tier, price, email)


def _issuer_jwt_only(token: str) -> str:
    """The open mandate with its disclosures removed, so its limits can't be read."""
    return token.split("~")[0] + "~"


class _ScriptedRunner(BaseModelRunner):
    """Stands in for a model: returns the given decisions in order, then finishes."""

    def __init__(self, decisions):
        self._decisions = list(decisions)

    async def decide_next_action(self, system_prompt, messages, tools):
        if self._decisions:
            return self._decisions.pop(0)
        return {"action": "finish", "content": "done"}


@pytest.fixture
def signature_counter(monkeypatch):
    """Counts every closed-mandate signature the buyer agent produces."""
    calls = []
    original = MandateClient.present

    def counting_present(self, *args, **kwargs):
        calls.append(1)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(MandateClient, "present", counting_present)
    return calls


@pytest.fixture(params=["mock", "live"])
def mode(request, monkeypatch):
    """Runs verification-only tests with MOCK_EXTERNAL_APIS on and off. No network calls."""
    monkeypatch.setattr(settings, "mock_external_apis", request.param == "mock")
    return request.param


# ── 1. Owner keys and the limits screen ──────────────────────────────────


@pytest.mark.parametrize("path", [
    "/api/trusted-surface/enroll",
    "/api/agent/trusted-surface/enroll",
    "/api/agent/trusted-surface/sign-limits",
])
def test_unauthenticated_owner_routes_stay_removed(path):
    assert client.post(path, json={}).status_code in (404, 405)


def test_unregistered_owner_key_is_rejected(mode):
    email, agent = _email("unreg"), _key("agent")
    limits = _limits(email, _key("unregistered"), agent, 1_000_000)
    res = _verify(*_close(limits, agent, "ap2-cluster", 179.99, email), email)
    assert res["valid"] is False
    assert res["error"] == "invalid_credential"


def test_registered_owner_key_cannot_be_replaced(mode):
    email, agent = _email("owner"), _key("agent")
    owner = _enrolled_owner(email)
    other = JWK.generate(kty="EC", crv="P-256", kid=owner.kid)
    challenge = client.get("/api/agent/keys/challenge").json()["challenge"]
    resp = client.post("/api/agent/keys/register", json={
        "kid": owner.kid,
        "publicKeyJwk": other.export_public(as_dict=True),
        "contractorEmail": email,
        "businessEntity": "Other Party LLC",
        "challenge": challenge,
        "challengeSignature": sign_es256_challenge(challenge, other),
    })
    assert resp.status_code == 409
    limits = _limits(email, owner, agent, 100)
    assert _verify(*_close(limits, agent, "ap2-batch", 49.99, email), email)["valid"] is True


def test_limits_screen_requires_explicit_confirmation():
    resp = client.post("/api/trusted-surface/sign-limits", json={"buyer_email": _email("ts"), "monthly_budget_cap": 60})
    assert resp.status_code == 422


def test_limits_screen_disabled_outside_mock_mode(monkeypatch):
    monkeypatch.setattr(settings, "mock_external_apis", False)
    resp = client.post("/api/trusted-surface/sign-limits", json={
        "buyer_email": _email("ts"), "monthly_budget_cap": 60, "human_confirmed": True,
    })
    assert resp.status_code == 404


def test_limits_screen_never_changes_saved_cap():
    email = _email("cap")
    ledger.set_contractor_cap(email, 60.0, source="key_registration")
    client.post("/api/trusted-surface/sign-limits", json={
        "buyer_email": email, "monthly_budget_cap": 5000, "human_confirmed": True,
    })
    assert ledger.get_saved_cap(email) == 60.0


# ── 2. The merchant enforces the owner's signed limits ───────────────────


def test_merchant_accepts_purchase_within_limits(mode):
    email, agent = _email("ok"), _key("agent")
    limits = _limits(email, _enrolled_owner(email), agent, 100, tiers=["ap2-batch"])
    assert _verify(*_close(limits, agent, "ap2-batch", 49.99, email), email)["valid"] is True


def test_merchant_rejects_amount_over_monthly_limit(mode):
    email, agent = _email("amt"), _key("agent")
    limits = _limits(email, _enrolled_owner(email), agent, 60)
    res = _verify(*_close(limits, agent, "ap2-cluster", 179.99, email), email)
    assert res["valid"] is False
    assert res["error"] == "invalid_mandate"


def test_merchant_rejects_tier_the_owner_did_not_allow(mode):
    email, agent = _email("tier"), _key("agent")
    limits = _limits(email, _enrolled_owner(email), agent, 100, tiers=["ap2-batch"])
    res = _verify(*_close(limits, agent, "ap2-gateway", 79.99, email), email)
    assert res["valid"] is False
    assert res["error"] == "invalid_mandate"


# ── 3. Budget and the 12-payment limit (full purchase flow, mock mode) ───


def test_thirteenth_monthly_payment_is_rejected():
    email, agent = _email("recur"), _key("agent")
    limits = _limits(email, _enrolled_owner(email), agent, 60)  # yearly budget 720 > 13 x 49.99
    results = [_buy(limits, agent, "ap2-batch", 49.99, email) for _ in range(13)]
    assert [r.get("status") in SETTLED for r in results[:12]] == [True] * 12
    assert results[12].get("status") not in SETTLED


def test_yearly_budget_is_enforced():
    email, agent = _email("budget"), _key("agent")
    limits = _limits(email, _enrolled_owner(email), agent, 60, yearly=100)
    results = [_buy(limits, agent, "ap2-batch", 49.99, email) for _ in range(3)]
    assert [r.get("status") in SETTLED for r in results] == [True, True, False]


@pytest.mark.parametrize("tier,price", [
    ("ap2-batch", 49.99),
    ("ap2-gateway", 79.99),
    ("ap2-cluster", 179.99),
])
def test_default_yearly_budget_fits_exactly_twelve_payments(tier, price):
    email, agent = _email("twelve"), _key("agent")
    limits = _limits(email, _enrolled_owner(email), agent, price)
    results = [_buy(limits, agent, tier, price, email) for _ in range(13)]
    assert [r.get("status") in SETTLED for r in results] == [True] * 12 + [False]


# ── 4. Repeat purchases ──────────────────────────────────────────────────


def test_repeat_purchase_never_buys_twice_or_uses_budget():
    """A replayed purchase may return the original subscription or be rejected,
    but must never create a second subscription or count against the budget."""
    email, agent = _email("replay"), _key("agent")
    limits = _limits(email, _enrolled_owner(email), agent, 60, yearly=100)  # room for exactly 2 payments
    rec, chk, pay = _close(limits, agent, "ap2-batch", 49.99, email)
    first = _purchase(rec, chk, pay, "ap2-batch", 49.99, email)
    assert first.get("status") in SETTLED
    for _ in range(3):
        again = _purchase(rec, chk, pay, "ap2-batch", 49.99, email)
        if again.get("status") in SETTLED:
            assert again.get("subscription_id") == first.get("subscription_id")
    second = _buy(limits, agent, "ap2-batch", 49.99, email)
    assert second.get("status") in SETTLED, "repeats were counted against the budget"


def test_repeat_purchase_requires_a_valid_mandate():
    email, agent = _email("bare"), _key("agent")
    limits = _limits(email, _enrolled_owner(email), agent, 60)
    rec, chk, pay = _close(limits, agent, "ap2-batch", 49.99, email)
    assert _purchase(rec, chk, pay, "ap2-batch", 49.99, email).get("status") in SETTLED
    res = _run(seller_agent.purchase_subscription(mandate_proof_hash=rec["checkout_hash"]))
    assert res.get("status") not in SETTLED
    for field in ("subscription_id", "payment_token", "vault_id", "payer_id", "buyer_email"):
        assert field not in res


@KNOWN_ISSUE(
    "purchase_subscription still accepts the pre-AP2 path (offer_id + server-issued "
    "mandate_proof_hash) with no owner-signed mandate, so the owner's signed limits are optional."
)
def test_purchase_requires_owner_signed_ap2_mandates():
    email = _email("legacy")
    neg = _run(seller_agent.negotiate_tier_terms(
        buyer_agent_id="regression-legacy", buyer_email=email, tier_id="ap2-gateway", monthly_budget_cap=100.0,
    ))
    res = _run(seller_agent.purchase_subscription(
        tier_id="ap2-gateway", agreed_monthly_rate=79.99,
        mandate_proof_hash=neg.get("mandate_proof_hash"), contractor_email=email, offer_id=neg.get("offer_id"),
    ))
    assert res.get("status") not in SETTLED


# ── 5. The buyer agent ───────────────────────────────────────────────────


def test_buyer_agent_refuses_purchase_over_limit(signature_counter):
    email, agent = _email("over"), _key("agent")
    limits = _limits(email, _enrolled_owner(email), agent, 60)
    rec = create_merchant_checkout("ap2-cluster", 179.99, email)
    runner = _ScriptedRunner([{
        "action": "call_tool", "tool_name": "sign_and_purchase",
        "parameters": {"tier_id": "ap2-cluster", "monthly_price": 179.99, "checkout_jwt": rec["checkout_jwt"],
                       "checkout_hash": rec["checkout_hash"], "nonce": rec["nonce"]},
    }])
    buyer = LLMBuyerAgent(monthly_budget_cap=60, buyer_email=email, agent_key=agent, model_runner=runner)
    res = _run(buyer.run_autonomous_procurement(
        "buy", target_tier="ap2-cluster",
        open_checkout_mandate_token=limits["open_checkout_mandate_token"],
        open_payment_mandate_token=limits["open_payment_mandate_token"],
    ))
    assert len(signature_counter) == 0
    assert res.get("status") != "COMPLETED"


def test_buyer_agent_refuses_when_limits_cannot_be_read(signature_counter):
    email, agent = _email("unread"), _key("agent")
    limits = _limits(email, _enrolled_owner(email), agent, 60, tiers=["ap2-batch"])
    rec = create_merchant_checkout("ap2-cluster", 179.99, email)
    runner = _ScriptedRunner([{
        "action": "call_tool", "tool_name": "sign_and_purchase",
        "parameters": {"tier_id": "ap2-cluster", "monthly_price": 179.99, "checkout_jwt": rec["checkout_jwt"],
                       "checkout_hash": rec["checkout_hash"], "nonce": rec["nonce"]},
    }])
    buyer = LLMBuyerAgent(monthly_budget_cap=60, buyer_email=email, agent_key=agent, model_runner=runner)
    _run(buyer.run_autonomous_procurement(
        "buy", target_tier="ap2-cluster",
        open_checkout_mandate_token=_issuer_jwt_only(limits["open_checkout_mandate_token"]),
        open_payment_mandate_token=_issuer_jwt_only(limits["open_payment_mandate_token"]),
    ))
    assert len(signature_counter) == 0


def test_buyer_agent_checks_seller_signature_on_checkout(signature_counter):
    email, agent = _email("sig"), _key("agent")
    limits = _limits(email, _enrolled_owner(email), agent, 60)
    rec = create_merchant_checkout("ap2-batch", 49.99, email)
    header_b64, payload_b64, _ = rec["checkout_jwt"].split(".")
    pad = lambda s: s + "=" * (-len(s) % 4)
    header = json.loads(base64.urlsafe_b64decode(pad(header_b64)))
    payload = json.loads(base64.urlsafe_b64decode(pad(payload_b64)))
    wrong_signer = create_jwt(header, payload, _key("not-the-seller"))
    runner = _ScriptedRunner([{
        "action": "call_tool", "tool_name": "sign_and_purchase",
        "parameters": {"tier_id": "ap2-batch", "monthly_price": 49.99, "checkout_jwt": wrong_signer,
                       "checkout_hash": rec["checkout_hash"], "nonce": rec["nonce"]},
    }])
    buyer = LLMBuyerAgent(monthly_budget_cap=60, buyer_email=email, agent_key=agent, model_runner=runner)
    _run(buyer.run_autonomous_procurement(
        "buy", target_tier="ap2-batch",
        open_checkout_mandate_token=limits["open_checkout_mandate_token"],
        open_payment_mandate_token=limits["open_payment_mandate_token"],
    ))
    assert len(signature_counter) == 0


def test_buyer_agent_only_calls_allowed_tools():
    email, agent = _email("tool"), _key("agent")
    limits = _limits(email, _enrolled_owner(email), agent, 60)
    runner = _ScriptedRunner([{"action": "call_tool", "tool_name": "_issue_mandate", "parameters": {}}])
    buyer = LLMBuyerAgent(monthly_budget_cap=60, buyer_email=email, agent_key=agent, model_runner=runner)
    res = _run(buyer.run_autonomous_procurement(
        "buy", open_checkout_mandate_token=limits["open_checkout_mandate_token"],
        open_payment_mandate_token=limits["open_payment_mandate_token"],
    ))
    assert res.get("status") == "REJECTED"


def test_buyer_agent_completes_without_access_to_owner_signing(monkeypatch):
    email, agent = _email("nokey"), _key("agent")
    limits = _limits(email, _enrolled_owner(email), agent, 100)

    def owner_signing_unavailable(*args, **kwargs):
        raise AssertionError("the buyer agent tried to sign the owner's limits")

    monkeypatch.setattr(trusted_surface_service, "create_trusted_surface_open_mandates", owner_signing_unavailable)
    monkeypatch.setattr(trusted_surface_service, "get_demo_user_key", owner_signing_unavailable)
    if hasattr(llm_buyer_agent, "create_trusted_surface_open_mandates"):
        monkeypatch.setattr(llm_buyer_agent, "create_trusted_surface_open_mandates", owner_signing_unavailable)
    buyer = LLMBuyerAgent(monthly_budget_cap=100, buyer_email=email, agent_key=agent)
    res = _run(buyer.run_autonomous_procurement(
        "buy", target_tier="ap2-gateway",
        open_checkout_mandate_token=limits["open_checkout_mandate_token"],
        open_payment_mandate_token=limits["open_payment_mandate_token"],
    ))
    assert res.get("status") == "COMPLETED"


# ── 6. Test isolation ────────────────────────────────────────────────────


def test_tests_never_use_the_dev_database():
    dev_db = (ROOT_DIR / "backend" / "data" / "a2a_commerce.db").resolve()
    assert get_db_path().resolve() != dev_db
