"""
Adversarial red-team regression suite for the AP2 seller node (Claude audit, 2026-10-08).

Each test asserts the SECURE behavior. Findings that are still open are listed in
OPEN_FINDINGS and run as strict xfails, so the suite stays green while they are open
and turns red the moment one is fixed without removing its ID here.

In-process (default, mock mode, isolated DB via conftest). Point A2A_DB_PATH at a temp
file so the run does not reset backend/data/a2a_commerce.db:

    A2A_DB_PATH=/tmp/audit.db python -m pytest backend/tests/test_ap2_adversarial_audit.py -v

Read-only live probes against a running node (GETs and non-mutating POSTs only):

    AP2_AUDIT_BASE_URL=http://127.0.0.1:8001 python -m pytest backend/tests/test_ap2_adversarial_audit.py -v -k Live
"""

import json
import math
import os
import time

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519
from fastapi.testclient import TestClient

from ..config import settings
from ..server import app
import backend.server as server_module
from ..services.crypto_mandate import (
    DEFAULT_BUYER_PUBLIC_KEY_HEX,
    canonicalize_mandate_payload,
    generate_ed25519_keypair,
    sign_ap2_intent_mandate,
    sign_ed25519_message,
    verify_ap2_cart_mandate,
)
from ..services.mandate_evaluator import ledger, validate_buyer_intent_mandate, build_buyer_intent_mandate

client = TestClient(app, raise_server_exceptions=False)


def admin_headers():
    return {"X-Admin-Key": settings.admin_api_key}


# Findings still open in the code under test. Remove an ID when its fix lands.
OPEN_FINDINGS = {}


def finding(fid):
    if fid in OPEN_FINDINGS:
        return pytest.mark.xfail(strict=True, reason=f"{fid} open: {OPEN_FINDINGS[fid]}")
    return lambda f: f


def mcp_raw(body, path="/mcp"):
    if isinstance(body, (dict, list)):
        return client.post(path, content=json.dumps(body), headers={"content-type": "application/json"})
    return client.post(path, content=body, headers={"content-type": "application/json"})


def tool(name, arguments, rid=1):
    res = mcp_raw({"jsonrpc": "2.0", "id": rid, "method": "tools/call", "params": {"name": name, "arguments": arguments}})
    assert res.status_code == 200, res.text
    body = res.json()
    if "result" in body:
        return json.loads(body["result"]["content"][0]["text"])
    return body


def negotiate(tier, email, cap, agent="audit-buyer"):
    return tool("negotiate_tier_terms", {
        "tier_id": tier, "buyer_agent_id": agent,
        "contractor_email": email, "monthly_budget_cap": cap,
    })


def is_rejected(result):
    return result.get("status") == "REJECTED" or "error" in result


# ---------------------------------------------------------------------------
# Threat Vector 2: mandates, pricing, signatures
# ---------------------------------------------------------------------------

@finding("AUD-01")
@pytest.mark.parametrize("rate", [0.01, 179.98, 0.0])
def test_purchase_rejects_rate_below_signed_offer(rate):
    neg = negotiate("ap2-cluster", "aud01@example.com", 200)
    assert neg["status"] == "APPROVED"
    res = tool("purchase_subscription", {
        "offer_id": neg["offer_id"], "tier_id": "ap2-cluster",
        "agreed_monthly_rate": rate, "mandate_proof_hash": neg["mandate_proof_hash"],
        "contractor_email": "aud01@example.com",
    })
    assert is_rejected(res), res


def test_purchase_rejects_rate_above_signed_offer():
    neg = negotiate("ap2-gateway", "aud01b@example.com", 100)
    res = tool("purchase_subscription", {
        "offer_id": neg["offer_id"], "tier_id": "ap2-gateway",
        "agreed_monthly_rate": 80.00, "mandate_proof_hash": neg["mandate_proof_hash"],
        "contractor_email": "aud01b@example.com",
    })
    assert is_rejected(res)


def test_purchase_rejects_tier_upgrade_on_down_tier_offer():
    neg = negotiate("ap2-cluster", "aud01c@example.com", 60)
    assert neg["status"] == "COUNTER_OFFER"
    res = tool("purchase_subscription", {
        "offer_id": neg["offer_id"], "tier_id": "ap2-cluster",
        "agreed_monthly_rate": 49.99, "mandate_proof_hash": neg["mandate_proof_hash"],
        "contractor_email": "aud01c@example.com",
    })
    assert is_rejected(res)


def test_legitimate_counter_offer_purchase_still_works():
    neg = negotiate("ap2-cluster", "aud01d@example.com", 60)
    res = tool("purchase_subscription", {
        "offer_id": neg["offer_id"], "contractor_email": "aud01d@example.com",
    })
    assert res.get("status") in ("ACTIVE", "APPROVAL_PENDING"), res
    assert res["agreed_monthly_rate"] == 49.99


@finding("AUD-02")
@pytest.mark.parametrize("amount", [0.01, -25.0])
def test_wildcard_spending_mandate_cannot_buy_below_catalog(amount):
    ev = tool("evaluate_spending_mandate", {
        "buyer_agent_id": "aud02", "amount": amount, "monthly_budget_cap": 100,
        "category": "autonomous-node-service",
    })
    proof = ev.get("mandateProofHash") or ""
    res = tool("purchase_subscription", {
        "tier_id": "ap2-cluster", "agreed_monthly_rate": amount,
        "mandate_proof_hash": proof, "contractor_email": "aud02@example.com",
    })
    assert is_rejected(res), res


def test_cart_mandate_one_cent_tamper_breaks_signature():
    neg = negotiate("ap2-gateway", "aud17@example.com", 100)
    cart = dict(neg["ap2_cart_mandate"])
    assert verify_ap2_cart_mandate(cart)
    cart["amount"] = {"value": "80.00", "currency_code": "USD"}
    assert not verify_ap2_cart_mandate(cart)
    cart = dict(neg["ap2_cart_mandate"])
    cart["payer"] = {"email": "someone-else@example.com"}
    assert not verify_ap2_cart_mandate(cart)


def test_offer_bound_to_email_cannot_be_redeemed_by_other_email():
    neg = negotiate("ap2-gateway", "owner18@example.com", 100)
    res = tool("purchase_subscription", {"offer_id": neg["offer_id"], "contractor_email": "thief@example.com"})
    assert is_rejected(res)


def test_unknown_mandate_hash_rejected():
    res = tool("purchase_subscription", {
        "tier_id": "ap2-batch", "agreed_monthly_rate": 49.99,
        "mandate_proof_hash": "f" * 64, "contractor_email": "nobody@example.com",
    })
    assert is_rejected(res)


@finding("AUD-03")
def test_seller_attested_mandate_is_not_accepted_as_buyer_signed():
    neg = negotiate("ap2-cluster", "victim03@example.com", 900)
    issued = neg["ap2_intent_mandate"]
    assert issued.get("public_key") != DEFAULT_BUYER_PUBLIC_KEY_HEX
    ok, code, _ = validate_buyer_intent_mandate(issued, contractor_email="victim03@example.com")
    assert not ok and code in ("UNTRUSTED_BUYER_KEY", "SELLER_ATTESTED_NOT_BUYER_SIGNED")


@finding("AUD-03")
def test_demo_proof_endpoint_does_not_sign_with_trusted_buyer_key():
    proof = client.post("/api/crypto/generate-proof", json={"agreed_price_usd": 1.0}).json()
    assert proof["public_key"] != DEFAULT_BUYER_PUBLIC_KEY_HEX


def test_unregistered_buyer_key_mandate_rejected():
    priv, _ = generate_ed25519_keypair()
    forged = sign_ap2_intent_mandate({
        "vct": "ap2.mandate.intent.1", "kid": "never-registered-kid", "attestation": "buyer_signed",
        "payer": {"email": "aud16@example.com"}, "amount": {"value": "500.00", "currency_code": "USD"},
        "category": "autonomous-node-service", "expires_at": time.time() + 3600,
    }, private_key_hex=priv)
    ok, code, _ = validate_buyer_intent_mandate(forged, contractor_email="aud16@example.com")
    assert not ok and code == "UNTRUSTED_BUYER_KEY"


@finding("AUD-04")
def test_verify_tamper_rejects_self_signed_payload_with_embedded_key():
    attacker = ed25519.Ed25519PrivateKey.generate()
    payload = {
        "vct": "ap2.mandate.intent.1", "contractor_id": "buyer_node_863",
        "business_name": "AP2 Node Network LLC", "monthly_cap_usd": 100,
        "agreed_price_usd": 0.01, "nonce": "aud04", "timestamp": int(time.time()),
        "public_key": attacker.public_key().public_bytes_raw().hex(),
        "kid": "ap2-buyer-ed25519-v1",
    }
    sig = attacker.sign(json.dumps(canonicalize_mandate_payload(payload), sort_keys=True).encode()).hex()
    res = client.post("/api/crypto/verify-tamper", json={"payload": payload, "signature": sig})
    assert res.json()["valid"] is False


@finding("AUD-04")
def test_verify_tamper_malformed_payload_is_not_a_500():
    res = client.post("/api/crypto/verify-tamper", json={"payload": {"timestamp": "abc"}, "signature": "00"})
    assert res.status_code < 500


def test_verify_tamper_plus_one_cent_and_drift():
    proof = client.get("/api/crypto/sample-proof").json()
    tampered = dict(proof["canonical_payload"]); tampered["agreed_price_usd"] = 80.00
    assert client.post("/api/crypto/verify-tamper", json={"payload": tampered, "signature": proof["signature"]}).json()["valid"] is False
    entity = dict(proof["canonical_payload"]); entity["business_name"] = "Evil Corp LLC"
    assert client.post("/api/crypto/verify-tamper", json={"payload": entity, "signature": proof["signature"]}).json()["valid"] is False
    stale = dict(proof["canonical_payload"]); stale["timestamp"] = int(time.time()) - 400
    body = client.post("/api/crypto/verify-tamper", json={"payload": stale, "signature": proof["signature"]}).json()
    assert body["valid"] is False and body["reason"] == "TIMESTAMP_EXPIRED"
    authentic = client.post("/api/crypto/verify-tamper", json={"payload": proof["canonical_payload"], "signature": proof["signature"]}).json()
    assert authentic["valid"] is True


def test_budget_cap_clamps_to_solo_starter_and_rejects_below_floor():
    counter = negotiate("ap2-gateway", "aud-cap@example.com", 60)
    assert counter["status"] == "COUNTER_OFFER" and counter["counter_offer_amount"] == 49.99
    floor = negotiate("ap2-gateway", "aud-floor@example.com", 49.98)
    assert floor["status"] == "REJECTED" and floor["error"] == "BUDGET_EXHAUSTED"


@finding("AUD-09")
@pytest.mark.parametrize("args", [
    {"buyer_agent_id": "a", "amount": "nan", "monthly_budget_cap": 100, "category": "autonomous-node-service"},
    {"buyer_agent_id": "a", "amount": 500, "monthly_budget_cap": "inf", "category": "autonomous-node-service"},
    {"buyer_agent_id": "a", "amount": -1, "monthly_budget_cap": 100, "category": "autonomous-node-service"},
])
def test_nonfinite_or_negative_spending_params_rejected(args):
    res = mcp_raw({"jsonrpc": "2.0", "id": 9, "method": "tools/call", "params": {"name": "evaluate_spending_mandate", "arguments": args}})
    body = res.json()
    assert body.get("error", {}).get("code") == -32602, body


@finding("AUD-09")
def test_rest_spending_mandate_rejects_negative_amount():
    res = client.post("/api/agent/spending-mandate/evaluate", json={
        "buyerAgentId": "a", "amount": -10, "recurrence": "monthly",
        "category": "autonomous-node-service", "monthlyBudgetCap": 100,
    })
    assert res.status_code == 422


@finding("AUD-14")
def test_unsigned_negotiation_caps_are_per_negotiation():
    # Copilot demo flow: same contractor at $60 then $100 still works, and nothing is saved
    assert negotiate("ap2-gateway", "aud14-demo@example.com", 60)["status"] == "COUNTER_OFFER"
    assert negotiate("ap2-gateway", "aud14-demo@example.com", 100)["status"] == "APPROVED"
    assert ledger.get_saved_cap("aud14-demo@example.com") is None


@finding("AUD-14")
def test_saved_registration_cap_binds_other_agents():
    res, _, _ = _register_key("audit-kid-14", "aud14@example.com", cap=60)
    assert res.status_code == 201
    raised = negotiate("ap2-cluster", "aud14@example.com", 5000, agent="other-agent")
    assert raised["status"] == "COUNTER_OFFER" and raised["monthly_budget_cap"] == 60
    assert ledger.get_saved_cap("aud14@example.com") == 60


@finding("AUD-14")
def test_registration_without_cap_saves_nothing():
    res, _, _ = _register_key("audit-kid-14c", "aud14c@example.com")
    assert res.status_code == 201
    assert ledger.get_saved_cap("aud14c@example.com") is None


@finding("AUD-14")
def test_only_the_contractors_own_key_can_change_saved_cap():
    _, _, own_priv = _register_key("audit-kid-14b", "aud14b@example.com", cap=60)
    _, _, other_priv = _register_key("audit-kid-14x", "someone-else@example.com")

    def signed_negotiation(kid, priv, cap):
        mandate = build_buyer_intent_mandate(
            buyer_agent_id=kid, amount=cap, recurrence="monthly", category="autonomous-node-service",
            tier_id="ap2-cluster", contractor_email="aud14b@example.com", private_key_hex=priv, kid=kid,
        )
        return tool("negotiate_tier_terms", {
            "tier_id": "ap2-cluster", "buyer_agent_id": kid, "contractor_email": "aud14b@example.com",
            "monthly_budget_cap": cap, "buyer_intent_mandate": mandate,
        })

    other = signed_negotiation("audit-kid-14x", other_priv, 500)
    assert other["status"] == "COUNTER_OFFER" and ledger.get_saved_cap("aud14b@example.com") == 60
    own = signed_negotiation("audit-kid-14b", own_priv, 200)
    assert own["status"] == "APPROVED" and ledger.get_saved_cap("aud14b@example.com") == 200


# ---------------------------------------------------------------------------
# Threat Vector 1 / 3: route authorization, PII exposure, key onboarding, SSRF
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "/api/harness/run-buyer-agent",
    "/api/agent/spending-mandate/reset",
    "/api/paypal/simulate-approval/I-AUDIT",
])
@pytest.mark.parametrize("headers", [{}, {"X-Admin-Key": "dev-admin-secret-key"}, {"Authorization": "Bearer wrong"}])
def test_admin_routes_reject_missing_or_wrong_key(path, headers):
    res = client.post(path, json={}, headers=headers)
    assert res.status_code == 401
    assert "Traceback" not in res.text


@finding("AUD-05")
@pytest.mark.parametrize("variant", ["query", "bearer"])
def test_fleet_ledger_unmask_requires_admin_key(variant, monkeypatch):
    monkeypatch.delenv("TESTING", raising=False)
    masked = client.get("/api/fleet/ledger").json()["transactions"]
    if variant == "query":
        probe = client.get("/api/fleet/ledger?unmasked=true").json()["transactions"]
    else:
        probe = client.get("/api/fleet/ledger", headers={"Authorization": "Bearer x"}).json()["transactions"]
    assert [t["contractor_name"] for t in probe] == [t["contractor_name"] for t in masked]
    admin = client.get("/api/fleet/ledger", headers={"Authorization": f"Bearer {settings.admin_api_key}"}).json()["transactions"]
    assert any("***" not in t["contractor_name"] for t in admin)


def _register_key(kid, email, cap=None):
    priv, pub = generate_ed25519_keypair()
    ch = client.get("/api/agent/keys/challenge").json()["challenge"]
    body = {"kid": kid, "publicKeyHex": pub, "contractorEmail": email, "businessEntity": "Audit Builders LLC",
            "challenge": ch, "challengeSignature": sign_ed25519_message(ch, priv)}
    if cap is not None:
        body["monthlyBudgetCap"] = cap
    return client.post("/api/agent/keys/register", json=body), body, priv


@finding("AUD-06")
def test_public_key_registry_hides_contractor_emails():
    res, _, _ = _register_key("audit-kid-06", "private06@example.com")
    assert res.status_code == 201
    public = client.get("/api/agent/keys/registry").json()["keys"]
    assert "private06@example.com" not in json.dumps(public)
    admin = client.get("/api/agent/keys/registry", headers=admin_headers()).json()["keys"]
    assert "private06@example.com" in json.dumps(admin)


def test_key_challenge_is_single_use_and_expires():
    res, body, priv = _register_key("audit-kid-15a", "kid15@example.com")
    assert res.status_code == 201
    body["kid"] = "audit-kid-15b"
    assert client.post("/api/agent/keys/register", json=body).status_code == 400
    ch = client.get("/api/agent/keys/challenge").json()["challenge"]
    server_module._ACTIVE_KEY_CHALLENGES[ch] -= 301
    body.update({"kid": "audit-kid-15c", "challenge": ch, "challengeSignature": sign_ed25519_message(ch, priv)})
    assert client.post("/api/agent/keys/register", json=body).status_code == 400


def test_registered_kid_cannot_be_overwritten_and_reserved_kids_blocked():
    assert _register_key("audit-kid-overwrite", "first@example.com")[0].status_code == 201
    assert _register_key("audit-kid-overwrite", "second@example.com")[0].status_code == 409
    assert _register_key("ap2-buyer-ed25519-v1", "x@example.com")[0].status_code == 403


@finding("AUD-11")
def test_key_challenge_store_is_bounded(monkeypatch):
    monkeypatch.setattr(server_module, "_MAX_ACTIVE_KEY_CHALLENGES", 50, raising=False)
    server_module._ACTIVE_KEY_CHALLENGES.clear()
    for _ in range(80):
        client.get("/api/agent/keys/challenge")
    assert len(server_module._ACTIVE_KEY_CHALLENGES) <= 50


@finding("AUD-07")
def test_wire_frames_redact_contractor_identity_and_offer_tokens():
    neg = negotiate("ap2-gateway", "wire07@example.com", 100)
    for path in ("/api/mcp/frames", "/m2m/frames"):
        blob = json.dumps(client.get(path).json()["frames"])
        assert "wire07@example.com" not in blob
        assert neg["offer_id"] not in blob
        assert neg["mandate_proof_hash"] not in blob


@finding("AUD-08")
def test_subscription_details_do_not_leak_email():
    neg = negotiate("ap2-gateway", "details08@example.com", 100)
    sub = tool("purchase_subscription", {"offer_id": neg["offer_id"], "contractor_email": "details08@example.com"})
    details = tool("get_subscription_details", {"subscription_id": sub["subscription_id"]})
    assert details.get("contractor_email") != "details08@example.com"


def test_ssrf_blocks_internal_targets_in_live_mode(monkeypatch):
    from backend.services.backoffice.webhook_dispatcher import is_url_permitted
    monkeypatch.setattr(settings, "mock_external_apis", False)
    for url in [
        "http://127.0.0.1:8000/", "http://localhost:8000/", "http://[::1]/", "http://[::ffff:127.0.0.1]/",
        "http://0.0.0.0:8000/", "http://169.254.169.254/computeMetadata/v1/", "http://10.0.0.5/",
        "http://2130706433/", "file:///etc/passwd", "gopher://hooks.zapier.com/",
    ]:
        assert not is_url_permitted(url), url


@finding("AUD-12")
def test_public_test_sinks_not_permitted_in_live_mode(monkeypatch):
    from backend.services.backoffice.webhook_dispatcher import is_url_permitted
    monkeypatch.setattr(settings, "mock_external_apis", False)
    assert not is_url_permitted("https://webhook.site/00000000-0000-0000-0000-000000000000")
    assert not is_url_permitted("https://abc123.m.pipedream.net/")
    assert is_url_permitted("https://hooks.zapier.com/hooks/catch/1/abc")


def _slot(**overrides):
    import datetime as _dt
    body = {
        "leadId": "lead-audit-1",
        "territoryZone": "Zone 1 - North Lakeland",
        "slotStartIso": (_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=2)).isoformat(),
        "paypalTransactionId": "TXN-AUDIT-1",
    }
    body.update(overrides)
    return client.post("/api/agent/dispatch/lock-slot", json=body)


def test_dispatch_slot_rejects_bad_input():
    assert _slot().status_code == 200
    assert _slot(slotStartIso="not-a-date").status_code == 400
    assert _slot(slotStartIso="2099-01-01T10:00:00Z").status_code == 400
    assert _slot(leadId="x" * 65).status_code == 422
    assert _slot(paypalTransactionId="<script>").status_code == 422


def test_dispatch_slot_lock_rate_is_capped(monkeypatch):
    monkeypatch.setattr(server_module, "_MAX_SLOT_LOCKS_PER_HOUR", 3)
    server_module._RECENT_SLOT_LOCKS.clear()
    codes = [_slot(leadId=f"lead-rate-{i}").status_code for i in range(5)]
    server_module._RECENT_SLOT_LOCKS.clear()
    assert codes == [200, 200, 200, 429, 429]


@pytest.mark.parametrize("body", [
    {"amount": -50, "currency": "USD", "description": "x"},
    {"amount": 0, "currency": "USD", "description": "x"},
    {"amount": 1_000_000, "currency": "USD", "description": "x"},
    {"amount": 10, "currency": "EUR", "description": "x"},
    {"amount": 10, "currency": "USD", "description": "x" * 200},
])
def test_create_order_rejects_out_of_range(body):
    assert client.post("/api/paypal/create-order", json=body).status_code == 422


def test_create_order_accepts_normal_deposit():
    res = client.post("/api/paypal/create-order", json={"amount": 149.0, "currency": "USD", "description": "Compute node deposit"})
    assert res.status_code == 200


def test_backoffice_webhook_override_dropped_without_admin_in_live_mode(monkeypatch):
    sent = []

    async def fake_sync(req):
        sent.append(req.webhook_url)
        return {"success": True}

    from backend.services.zapier_mcp_dispatcher import zapier_mcp_dispatcher as zd
    monkeypatch.setattr(zd, "execute_downline_sync", fake_sync)
    monkeypatch.setattr(settings, "mock_external_apis", False)
    body = {"workflowType": "a2a_onboarding", "webhookUrl": "https://hooks.zapier.com/hooks/catch/1/x"}
    client.post("/api/mcp/zapier-sync", json=body)
    client.post("/api/mcp/zapier-sync", json=body, headers=admin_headers())
    assert sent == [None, "https://hooks.zapier.com/hooks/catch/1/x"]


def test_live_zapier_dispatch_requires_admin(monkeypatch):
    from backend.services.zapier_mcp_dispatcher import zapier_mcp_dispatcher as zd
    monkeypatch.setattr(zd, "mock_mode", False)
    for path in ("/api/mcp/zapier-sync", "/api/export/backoffice"):
        assert client.post(path, json={"workflowType": "a2a_onboarding"}).status_code == 401


# ---------------------------------------------------------------------------
# Threat Vector 4: JSON-RPC 2.0 conformance
# ---------------------------------------------------------------------------

def test_jsonrpc_parse_error_and_unknown_method():
    assert mcp_raw("{not json").json()["error"]["code"] == -32700
    assert mcp_raw({"jsonrpc": "2.0", "id": 1, "method": "no/such"}).json()["error"]["code"] == -32601
    assert tool("no_such_tool", {}).get("error", {}).get("code") == -32601


@finding("AUD-10")
@pytest.mark.parametrize("body,code", [
    ('"just a string"', -32600),
    ("[]", -32600),
    ({"jsonrpc": "1.0", "id": 1, "method": "ping"}, -32600),
    ({"jsonrpc": "2.0", "id": 1}, -32600),
    ({"jsonrpc": "2.0", "id": 1, "method": 42}, -32600),
    ({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": []}, -32602),
    ({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "negotiate_tier_terms", "arguments": []}}, -32602),
    ({"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "negotiate_tier_terms", "arguments": {"monthly_budget_cap": "abc"}}}, -32602),
])
def test_jsonrpc_invalid_envelopes_get_standard_codes(body, code):
    res = mcp_raw(body)
    assert res.status_code == 200
    payload = res.json()
    assert isinstance(payload, dict) and payload["error"]["code"] == code, payload
    assert "could not convert" not in payload["error"].get("message", "")
    assert "constraint" not in payload["error"].get("message", "")


@finding("AUD-10")
def test_jsonrpc_batch_is_supported():
    res = mcp_raw([{"jsonrpc": "2.0", "id": 1, "method": "ping"}, {"jsonrpc": "2.0", "id": 2, "method": "ping"}])
    assert res.status_code == 200
    assert sorted(r["id"] for r in res.json()) == [1, 2]


def test_tool_param_injection_strings_are_inert():
    res = negotiate("ap2-cluster", "' OR 1=1;--@example.com", 200)
    assert res.get("status") in ("APPROVED", "REJECTED")
    stats = client.get("/api/fleet/stats")
    assert stats.status_code == 200


# ---------------------------------------------------------------------------
# Threat Vector 5: zero-speculative metric reconciliation
# ---------------------------------------------------------------------------

def test_fleet_mrr_and_arr_reconcile_with_active_rows():
    rows = client.get("/api/fleet/ledger", headers=admin_headers()).json()["transactions"]
    stats = client.get("/api/fleet/stats").json()
    active = [r for r in rows if r["status"] == "ACTIVE_STREAMING"]
    mrr = round(sum(r["monthly_amount"] for r in active), 2)
    assert stats["total_mrr"] == mrr
    assert stats["active_lines"] == len(active)
    assert math.isclose(stats["annualized_gmv"], round(mrr * 12, 2))
    assert all(r["monthly_amount"] > 0 for r in rows)


@finding("AUD-13")
def test_mandates_cleared_is_not_a_multiplier():
    stats = client.get("/api/fleet/stats").json()
    assert stats["mandates_cleared"] != stats["total_subscribers"] * 12


# ---------------------------------------------------------------------------
# Live read-only probes (opt-in via AP2_AUDIT_BASE_URL); never call purchase/negotiate
# ---------------------------------------------------------------------------

LIVE_BASE = os.getenv("AP2_AUDIT_BASE_URL", "").rstrip("/")
live = pytest.mark.skipif(not LIVE_BASE, reason="set AP2_AUDIT_BASE_URL to run live read-only probes")


@live
class TestLiveReadOnly:
    def _get(self, path, **kw):
        return httpx.get(f"{LIVE_BASE}{path}", timeout=15, **kw)

    def test_live_ledger_unmask_bypass(self):
        masked = self._get("/api/fleet/ledger").json()["transactions"]
        probe = self._get("/api/fleet/ledger", params={"unmasked": "true"}).json()["transactions"]
        assert [t["contractor_name"] for t in probe] == [t["contractor_name"] for t in masked]

    def test_live_registry_hides_emails(self):
        keys = self._get("/api/agent/keys/registry").json().get("keys", [])
        assert not any(k.get("contractorEmail") for k in keys)

    def test_live_admin_routes_require_key(self):
        for path in ("/api/harness/run-buyer-agent", "/api/paypal/simulate-approval/I-AUDIT"):
            assert httpx.post(f"{LIVE_BASE}{path}", json={}, timeout=15).status_code in (401, 403, 404)

    def test_live_jsonrpc_wrong_version_rejected(self):
        res = httpx.post(f"{LIVE_BASE}/a2a/mcp", json={"jsonrpc": "1.0", "id": 1, "method": "ping"}, timeout=15)
        assert res.json().get("error", {}).get("code") == -32600

    def test_live_verify_tamper_rejects_self_signed(self):
        attacker = ed25519.Ed25519PrivateKey.generate()
        payload = {"vct": "ap2.mandate.intent.1", "contractor_id": "c", "business_name": "b",
                   "monthly_cap_usd": 100, "agreed_price_usd": 1, "nonce": "n", "timestamp": int(time.time()),
                   "public_key": attacker.public_key().public_bytes_raw().hex(), "kid": "x"}
        sig = attacker.sign(json.dumps(canonicalize_mandate_payload(payload), sort_keys=True).encode()).hex()
        res = httpx.post(f"{LIVE_BASE}/api/crypto/verify-tamper", json={"payload": payload, "signature": sig}, timeout=15)
        assert res.json()["valid"] is False
