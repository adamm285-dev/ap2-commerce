"""
Purchase concurrency regression suite, maintained by the owner's independent reviewer.

Do not edit, weaken, skip, or delete these tests without the owner's approval.
If one fails, fix the code, not the test.

Tests marked KNOWN_ISSUE are open findings from review. They are expected to
fail today (strict xfail). When your fix makes one pass, pytest reports
"XPASS(strict)" as a failure: remove only that marker, in the same commit as
the fix.

Why the PayPal call is paused: mock PayPal (M-002) returns without yielding to
the event loop, so two mock purchases can never overlap. Live PayPal is an
awaited HTTP call, and other requests run while it is in flight. `paused_paypal`
holds the first purchase at that call, runs the others to completion, then lets
the first one finish. That is the live-mode interleaving, made deterministic.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
import random
import sys
import uuid

import httpx
import pytest

from ap2.sdk.generated.checkout_mandate import CheckoutMandate
from ap2.sdk.generated.payment_mandate import PaymentMandate
from ap2.sdk.generated.types.amount import Amount
from ap2.sdk.generated.types.merchant import Merchant
from ap2.sdk.generated.types.payment_instrument import PaymentInstrument
from ap2.sdk.mandate import MandateClient
from jwcrypto.jwk import JWK

from backend.agents.seller_agent import _ACTIVE_CONTRACTOR_SUBSCRIPTIONS, _COMPLETED_SUBSCRIPTIONS, seller_agent
from backend.config import ROOT_DIR, get_db_path
from backend.database import get_contractor_committed_spend, get_open_mandate_settlement_totals, register_buyer_key
from backend.services.ap2_keys import get_demo_agent_key, get_merchant_key
from backend.services.ap2_service import (
    AP2_MERCHANT_ID,
    AP2_MERCHANT_NAME,
    compute_open_payment_mandate_hash,
    create_merchant_checkout,
)
from backend.services.paypal_service import paypal_service
from backend.services.trusted_surface_service import create_trusted_surface_open_mandates

SETTLED = ("ACTIVE", "APPROVAL_PENDING")
TIERS = {"ap2-batch": 4999, "ap2-gateway": 7999}
IN_PROGRESS = "PURCHASE_IN_PROGRESS"


def KNOWN_ISSUE(reason: str):
    return pytest.mark.xfail(
        strict=True,
        raises=AssertionError,
        reason=f"Known open issue from review: {reason} Remove this marker in the commit that fixes it.",
    )


# ── Helpers ──────────────────────────────────────────────────────────────


def _email(tag: str) -> str:
    return f"conc-{tag}-{uuid.uuid4().hex[:8]}@example.com"


def _run(coro):
    with contextlib.redirect_stdout(io.StringIO()):
        return asyncio.run(coro)


def _limits(email, ceiling_cents, monthly_cap=500.00):
    """Owner limits signed by an owner key enrolled in the shared registry, so every process trusts it."""
    owner = JWK.generate(kty="EC", crv="P-256", kid=f"conc-owner-{uuid.uuid4().hex[:8]}")
    register_buyer_key(kid=owner.kid, public_key_hex=owner.export_public(), contractor_email=email,
                       business_name="Concurrency Owner LLC")
    ts = create_trusted_surface_open_mandates(
        buyer_email=email,
        monthly_budget_cap=monthly_cap,
        yearly_budget_ceiling=ceiling_cents / 100,
        allowed_tiers=list(TIERS),
        user_key=owner,
    )
    return ts["open_checkout_mandate_token"], ts["open_payment_mandate_token"]


def _signed(limits, email, tier):
    """A merchant checkout for `tier`, closed by the buyer agent under the owner's open mandates."""
    open_chk, open_pay = limits
    cents = TIERS[tier]
    rec = create_merchant_checkout(tier, cents / 100, email)
    key, mc = get_demo_agent_key(), MandateClient()
    chk = mc.present(
        holder_key=key, mandate_token=open_chk, aud=AP2_MERCHANT_ID, nonce=rec["nonce"],
        payloads=[CheckoutMandate(vct="mandate.checkout.1", checkout_jwt=rec["checkout_jwt"], checkout_hash=rec["checkout_hash"])],
    )
    pay = mc.present(
        holder_key=key, mandate_token=open_pay, aud=AP2_MERCHANT_ID, nonce=rec["nonce"],
        payloads=[PaymentMandate(
            vct="mandate.payment.1",
            transaction_id=rec["checkout_hash"],
            payment_amount=Amount(amount=cents, currency="USD"),
            payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
            payment_instrument=PaymentInstrument(type="paypal_vault", id=f"vault_{uuid.uuid4().hex[:8]}"),
        )],
    )
    return {
        "offer_id": f"offer-{uuid.uuid4().hex[:12]}",
        "contractor_email": email,
        "checkout_mandate_chain": chk,
        "payment_mandate_chain": pay,
        "checkout_jwt": rec["checkout_jwt"],
        "cents": cents,
    }


def _buy(purchase):
    args = {k: v for k, v in purchase.items() if k != "cents"}
    return seller_agent.purchase_subscription(**args)


def _settled_cents(limits):
    return get_open_mandate_settlement_totals(compute_open_payment_mandate_hash(limits[1]))


def _active_subs(results, email):
    ids = {r.get("subscription_id") for r in results if r.get("status") in SETTLED and r.get("subscription_id")}
    return sorted(
        sid for sid in ids
        if sid in _COMPLETED_SUBSCRIPTIONS
        and _COMPLETED_SUBSCRIPTIONS[sid].get("status") == "ACTIVE"
        and (_COMPLETED_SUBSCRIPTIONS[sid].get("contractor_email") or "").lower() == email.lower()
    )


class _PausedPayPal:
    """Holds the first create_subscription call until released; later calls get a small random delay."""

    def __init__(self, original):
        self.original = original
        self.calls = 0
        self.entered = None
        self.release = None
        self.on_enter = None

    def arm(self):
        self.calls = 0
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def __call__(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            if self.on_enter:
                self.on_enter()
            self.entered.set()
            await self.release.wait()
        else:
            await asyncio.sleep(random.uniform(0, 0.02))
        return await self.original(**kwargs)


@pytest.fixture
def paused_paypal(monkeypatch):
    pp = _PausedPayPal(paypal_service.create_subscription)
    monkeypatch.setattr(paypal_service, "create_subscription", pp)
    return pp


async def _first_in_flight(pp, first, others):
    """Starts `first`, waits until it is inside the PayPal call, runs `others` to completion, then releases `first`."""
    pp.arm()
    task = asyncio.create_task(first)
    await asyncio.wait_for(pp.entered.wait(), timeout=10)
    rest = await asyncio.gather(*others)
    pp.release.set()
    return [await task, *rest]


# Runs one purchase in a separate Python process against the same database file, the way the
# stdio MCP server (python -m backend.mcp_server) and the HTTP server share one SQLite file.
_CHILD = r"""
import asyncio, contextlib, io, json, sys
args = json.loads(sys.stdin.read())
with contextlib.redirect_stdout(io.StringIO()):
    from backend.services.paypal_service import paypal_service
    from backend.agents.seller_agent import seller_agent
    paypal_service.mock_mode = True
    res = asyncio.run(seller_agent.purchase_subscription(**args))
sys.stdout.write(json.dumps({"status": res.get("status"), "error": res.get("error"),
                             "reason": res.get("reason"), "subscription_id": res.get("subscription_id")}))
"""


async def _purchase_in_other_process(purchase):
    env = dict(os.environ)
    env["A2A_DB_PATH"] = str(get_db_path())
    env["AP2_MERCHANT_PRIVATE_KEY_JWK"] = get_merchant_key().export_private()
    env["MOCK_EXTERNAL_APIS"] = "true"
    env["PYTHONPATH"] = os.pathsep.join([str(ROOT_DIR / "backend" / "vendor"), str(ROOT_DIR)])
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", _CHILD, cwd=str(ROOT_DIR), env=env,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    args = {k: v for k, v in purchase.items() if k != "cents"}
    out, err = await asyncio.wait_for(proc.communicate(json.dumps(args).encode()), timeout=120)
    assert proc.returncode == 0, f"child process failed: {err.decode(errors='replace')[-2000:]}"
    return json.loads(out.decode())


# ── 1. Controls: these pass today and must keep passing ──────────────────


def test_sequential_purchases_respect_owner_ceiling():
    email = _email("seq")
    tier = random.choice(list(TIERS))
    ceiling = TIERS[tier] + random.randint(0, TIERS[tier] - 1)  # room for exactly one
    limits = _limits(email, ceiling)
    first = _run(_buy(_signed(limits, email, tier)))
    second = _run(_buy(_signed(limits, email, tier)))
    assert first["status"] in SETTLED
    assert second["status"] not in SETTLED
    assert _settled_cents(limits) == (TIERS[tier], 1)


def test_unrelated_buyers_are_not_blocked(paused_paypal):
    """A fix must not serialize every purchase on the server: another buyer's purchase still settles."""
    ex, ey = _email("x"), _email("y")
    px = _signed(_limits(ex, 100_000), ex, "ap2-batch")
    py = _signed(_limits(ey, 100_000), ey, "ap2-batch")
    rx, ry = _run(_first_in_flight(paused_paypal, _buy(px), [_buy(py)]))
    assert rx["status"] in SETTLED
    assert ry["status"] in SETTLED, f"unrelated buyer was blocked: {ry.get('error')} {ry.get('reason')}"


def test_failed_paypal_call_does_not_block_or_spend(monkeypatch):
    """After PayPal fails, the next purchase is neither blocked nor charged for the failed one."""
    email = _email("fail")
    tier = random.choice(list(TIERS))
    limits = _limits(email, TIERS[tier] + random.randint(0, TIERS[tier] - 1))
    original = paypal_service.create_subscription
    state = {"n": 0}

    async def flaky(**kwargs):
        state["n"] += 1
        if state["n"] == 1:
            raise httpx.ConnectTimeout("simulated PayPal timeout")
        return await original(**kwargs)

    monkeypatch.setattr(paypal_service, "create_subscription", flaky)
    failed = _run(_buy(_signed(limits, email, tier)))
    assert failed["status"] not in SETTLED
    ok = _run(_buy(_signed(limits, email, tier)))
    assert ok["status"] in SETTLED, f"purchase after a PayPal failure did not settle: {ok.get('error')} {ok.get('reason')}"
    assert _settled_cents(limits) == (TIERS[tier], 1)


def test_other_process_purchase_alone_settles():
    """Proves the two-process harness works, so the two-process KNOWN_ISSUE below fails for the right reason."""
    email = _email("child")
    limits = _limits(email, 100_000)
    res = _run(_purchase_in_other_process(_signed(limits, email, "ap2-batch")))
    assert res["status"] in SETTLED, f"child purchase failed: {res}"


# ── 2. Purchases in flight together (one process) ────────────────────────


@pytest.mark.parametrize("others", [1, 3])
def test_overlapping_purchases_never_exceed_owner_ceiling(paused_paypal, others):
    email = _email("ceiling")
    tier = random.choice(list(TIERS))
    ceiling = TIERS[tier] + random.randint(0, TIERS[tier] - 1)  # room for exactly one
    limits = _limits(email, ceiling)
    purchases = [_signed(limits, email, tier) for _ in range(others + 1)]
    results = _run(_first_in_flight(paused_paypal, _buy(purchases[0]), [_buy(p) for p in purchases[1:]]))

    settled = [p["cents"] for p, r in zip(purchases, results) if r.get("status") in SETTLED]
    assert sum(settled) <= ceiling, f"settled {settled} cents against a {ceiling}-cent owner ceiling"
    total, uses = _settled_cents(limits)
    assert total <= ceiling, f"open-mandate ledger holds {total} cents against a {ceiling}-cent ceiling"
    assert settled, "no purchase settled, although the ceiling has room for one"


def test_overlapping_purchases_leave_one_active_subscription(paused_paypal):
    email = _email("plan")
    limits = _limits(email, 100_000)
    a = _signed(limits, email, random.choice(list(TIERS)))
    b = _signed(limits, email, random.choice(list(TIERS)))
    results = _run(_first_in_flight(paused_paypal, _buy(a), [_buy(b)]))

    active = _active_subs(results, email)
    assert len(active) <= 1, f"buyer has {len(active)} ACTIVE subscriptions: {active}"
    assert active, "no purchase settled"
    assert _ACTIVE_CONTRACTOR_SUBSCRIPTIONS.get(email.lower()) == active[0]
    rate = _COMPLETED_SUBSCRIPTIONS[active[0]].get("agreed_monthly_rate")
    assert round(get_contractor_committed_spend(email.lower()), 2) == round(rate, 2)


def test_overlap_rejection_is_retryable(paused_paypal):
    """Whatever a fix does to an overlapping purchase, the buyer can retry it once the first one is done."""
    email = _email("retry")
    limits = _limits(email, 100_000)
    a = _signed(limits, email, "ap2-batch")
    b = _signed(limits, email, "ap2-gateway")
    ra, rb = _run(_first_in_flight(paused_paypal, _buy(a), [_buy(b)]))
    assert ra["status"] in SETTLED
    if rb.get("status") not in SETTLED:
        assert rb.get("error") == IN_PROGRESS, f"overlap rejected with {rb.get('error')}, expected {IN_PROGRESS}"
        retry = _run(_buy(b))
        assert retry["status"] in SETTLED, f"retry after the first purchase finished failed: {retry.get('error')} {retry.get('reason')}"


# ── 3. Purchases in flight together (two processes, one database) ────────


@pytest.mark.parametrize("variant", ["same_closed_mandate", "other_checkout"])
def test_second_process_cannot_settle_while_first_is_in_flight(paused_paypal, variant):
    email = _email("xproc")
    tier = random.choice(list(TIERS))
    ceiling = TIERS[tier] + random.randint(0, TIERS[tier] - 1)  # room for exactly one
    limits = _limits(email, ceiling)
    a = _signed(limits, email, tier)
    if variant == "same_closed_mandate":
        b = {**a, "offer_id": None}
    else:
        b = _signed(limits, email, tier)

    async def scenario():
        paused_paypal.arm()
        task = asyncio.create_task(_buy(a))
        await asyncio.wait_for(paused_paypal.entered.wait(), timeout=10)
        child = await _purchase_in_other_process(b)
        paused_paypal.release.set()
        return await task, child

    ra, rb = _run(scenario())
    if rb.get("status") not in SETTLED:
        assert rb.get("error") == IN_PROGRESS, f"child rejected for another reason ({rb.get('error')}: {rb.get('reason')}), so this test proves nothing"
    total, uses = _settled_cents(limits)
    assert uses <= 1, f"{uses} settlements recorded for one owner budget that fits one purchase"
    assert total <= ceiling
    subs = {r.get("subscription_id") for r in (ra, rb) if r.get("status") in SETTLED}
    assert len(subs) <= 1, f"two subscriptions created: {subs}"


# ── 4. PayPal-Request-Id on the live subscription call ───────────────────


_CREATED = {
    "status": "APPROVAL_PENDING",
    "create_time": "2026-10-18T12:00:00Z",
    "links": [{"href": "https://www.sandbox.paypal.com/webapps/billing/subscriptions?ba_token=BA-CONC", "rel": "approve", "method": "GET"}],
}


@pytest.fixture
def live_paypal_http(monkeypatch):
    """Live-mode PayPal service with only the HTTP layer replaced. Queue status codes in ["script"]."""
    state = {"sent": [], "script": []}

    async def token(*args, **kwargs):
        return "conc-token"

    async def respond(self, request, *args, **kwargs):
        if request.url.path != "/v1/billing/subscriptions" or request.method != "POST":
            raise RuntimeError(f"unexpected PayPal call in this test: {request.method} {request.url}")
        state["sent"].append(request)
        code = state["script"].pop(0) if state["script"] else 201
        if code == 201:
            body = {**_CREATED, "id": f"I-CONC{uuid.uuid4().hex[:8].upper()}"}
        else:
            body = {"name": "ERROR", "message": f"scripted {code}"}
        return httpx.Response(code, json=body, request=request)

    monkeypatch.setattr(paypal_service, "mock_mode", False)
    monkeypatch.setattr(paypal_service, "client_id", "")  # skip the Agent Toolkit branch, use direct REST
    monkeypatch.setattr(paypal_service, "get_access_token", token)
    monkeypatch.setattr(httpx.AsyncClient, "send", respond)
    return state


def _request_ids(state):
    return [r.headers.get("PayPal-Request-Id") for r in state["sent"]]


@KNOWN_ISSUE("The live subscription POST sends no PayPal-Request-Id, so PayPal cannot de-duplicate a retried purchase.")
def test_live_purchase_sends_paypal_request_id_and_reports_it(live_paypal_http):
    email = _email("rid")
    res = _run(_buy(_signed(_limits(email, 100_000), email, "ap2-batch")))
    ids = _request_ids(live_paypal_http)
    assert len(ids) == 1
    assert ids[0], "no PayPal-Request-Id header on the subscription POST"
    assert res.get("paypal_request_id") == ids[0], "reported paypal_request_id is not the header that was sent"


@KNOWN_ISSUE("Without a PayPal-Request-Id derived from the closed mandate, a retry of one purchase is a new PayPal request.")
def test_paypal_request_id_is_stable_per_closed_mandate(live_paypal_http):
    email = _email("rid-stable")
    limits = _limits(email, 100_000)
    a = _signed(limits, email, "ap2-batch")
    live_paypal_http["script"] = [500]
    failed = _run(_buy(a))
    assert failed.get("status") not in SETTLED
    retried = _run(_buy(a))
    assert retried.get("status") in SETTLED
    b = _signed(limits, email, "ap2-gateway")
    _run(_buy(b))
    first, retry, other = _request_ids(live_paypal_http)
    assert first and first == retry, "retrying the same closed mandate sent a different PayPal-Request-Id"
    assert other and other != first, "two different closed mandates sent the same PayPal-Request-Id"


@KNOWN_ISSUE("The 401 token-refresh retry re-sends the subscription POST without a PayPal-Request-Id.")
def test_paypal_request_id_survives_token_refresh_retry(live_paypal_http):
    email = _email("rid-401")
    live_paypal_http["script"] = [401, 201]
    res = _run(_buy(_signed(_limits(email, 100_000), email, "ap2-batch")))
    ids = _request_ids(live_paypal_http)
    assert len(ids) == 2, f"expected a 401 then one retry, saw {len(ids)} POSTs"
    assert ids[0] and ids[0] == ids[1], "the retry after a 401 sent a different PayPal-Request-Id"
    assert res.get("status") in SETTLED
