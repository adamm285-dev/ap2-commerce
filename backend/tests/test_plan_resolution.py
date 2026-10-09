"""
Comprehensive tests for:
1. Single source PayPal plan resolution: in both profiles, every tier_id and alias
   resolves strictly to a configured settings plan ID, never a synthesized P-FLSMITH-* / P-AP2-* string.
2. provision_compute_node robust error handling: unknown/inactive subscription returns clean
   SUBSCRIPTION_NOT_FOUND / SUBSCRIPTION_NOT_ACTIVE without KeyError or -32603.
3. Compute node endpoint host specialization: Batch -> batch-01, Gateway -> gateway-01, Cluster -> cluster-01.
4. Public alias sanitization: AP2 catalog output does not expose trades terms in tier_id_aliases,
   while backward-compatible aliases continue to resolve.
"""

import pytest
import re
from backend.config import settings
from backend.services.plan_catalog import (
    TRADES_PLANS,
    TRADES_TIER_ALIASES,
    AP2_PLANS,
    AP2_TIER_ALIASES,
    PUBLIC_AP2_TIER_ALIASES,
    resolve_paypal_plan_id,
    resolve_plan,
    get_public_tier_aliases,
)
from backend.agents.seller_agent import SellerAgent, _COMPLETED_SUBSCRIPTIONS
from backend.mcp_server import process_mcp_request


FORBIDDEN_TRADES_WORDS_RE = re.compile(
    r"(?i)flooring|roofing|plumb|towing|contractor|telephony|screened|10DLC|receptionist|DID|solo-starter|fieldsmith-pro|pro-dispatch"
)


def test_every_tier_and_alias_resolves_to_settings_plan_id_in_both_profiles(monkeypatch):
    """
    Item 1: In both profiles, every tier_id and alias resolves to a configured
    settings plan ID (paypal_plan_id_solo, pro, or dispatch), never a synthesized
    P-FLSMITH-* or P-AP2-* string.
    """
    configured_solo = "P-CUSTOM-SANDBOX-SOLO-001"
    configured_pro = "P-CUSTOM-SANDBOX-PRO-002"
    configured_dispatch = "P-CUSTOM-SANDBOX-DISPATCH-003"

    monkeypatch.setattr(settings, "paypal_plan_id_solo", configured_solo)
    monkeypatch.setattr(settings, "paypal_plan_id_pro", configured_pro)
    monkeypatch.setattr(settings, "paypal_plan_id_dispatch", configured_dispatch)

    allowed_plan_ids = {configured_solo, configured_pro, configured_dispatch}

    # 1. Test AP2 Profile
    ap2_targets = [p["tier_id"] for p in AP2_PLANS] + list(AP2_TIER_ALIASES.keys())
    for target in ap2_targets:
        resolved = resolve_paypal_plan_id(target, profile="ap2")
        assert resolved in allowed_plan_ids, (
            f"AP2 target '{target}' resolved to unexpected '{resolved}', expected one of {allowed_plan_ids}"
        )
        assert not resolved.startswith("P-AP2-AP2_"), f"Synthetic AP2 string detected for target '{target}': {resolved}"
        assert not resolved.startswith("P-FLSMITH-"), f"Synthetic Trades string detected in AP2 for '{target}': {resolved}"

    # 2. Test Trades Profile
    trades_targets = [p["tier_id"] for p in TRADES_PLANS] + list(TRADES_TIER_ALIASES.keys())
    for target in trades_targets:
        resolved = resolve_paypal_plan_id(target, profile="trades")
        assert resolved in allowed_plan_ids, (
            f"Trades target '{target}' resolved to unexpected '{resolved}', expected one of {allowed_plan_ids}"
        )
        assert not resolved.startswith("P-AP2-"), f"Synthetic AP2 string detected in Trades for '{target}': {resolved}"


@pytest.mark.asyncio
async def test_provision_compute_node_rejects_unknown_subscription(monkeypatch):
    """
    Item 2: Calling provision_compute_node with an unknown subscription_id returns
    a clean 'SUBSCRIPTION_NOT_FOUND' rejection, never raising KeyError or returning -32603.
    """
    monkeypatch.setattr(settings, "a2a_seller_profile", "ap2")
    seller = SellerAgent()

    # Unknown ID not in completed records
    res = await seller.provision_compute_node(
        subscription_id="I-NONEXISTENT-SUB-99999",
        buyer_email="buyer@acme-systems.io",
        node_type="gateway",
    )
    assert res["status"] == "REJECTED"
    assert res["error"] == "SUBSCRIPTION_NOT_FOUND"
    assert "not found" in res["reason"].lower()

    # Verify through MCP JSON-RPC protocol call as well
    rpc_req = {
        "jsonrpc": "2.0",
        "id": "unknown-sub-test",
        "method": "tools/call",
        "params": {
            "name": "provision_compute_node",
            "arguments": {
                "subscription_id": "I-NONEXISTENT-RPC-SUB",
                "buyer_email": "buyer@acme-systems.io",
            },
        },
    }
    rpc_res = await process_mcp_request(rpc_req)
    assert "error" not in rpc_res, f"Unexpected RPC-level protocol error: {rpc_res.get('error')}"
    tool_content = rpc_res["result"]["content"][0]["text"]
    assert "SUBSCRIPTION_NOT_FOUND" in tool_content


@pytest.mark.asyncio
async def test_provision_compute_node_rejects_inactive_subscription(monkeypatch):
    """
    Item 2: Calling provision_compute_node on an inactive subscription (e.g. APPROVAL_PENDING or CANCELLED)
    returns clean SUBSCRIPTION_NOT_CAPTURED or SUBSCRIPTION_NOT_ACTIVE.
    """
    monkeypatch.setattr(settings, "a2a_seller_profile", "ap2")
    seller = SellerAgent()

    # Insert mock sub in APPROVAL_PENDING
    pending_sub_id = "I-A2A-PENDING-SUB-01"
    _COMPLETED_SUBSCRIPTIONS[pending_sub_id] = {
        "subscription_id": pending_sub_id,
        "status": "APPROVAL_PENDING",
        "buyer_email": "buyer@acme-systems.io",
        "tier_id": "ap2-gateway",
    }

    res_pending = await seller.provision_compute_node(
        subscription_id=pending_sub_id,
        buyer_email="buyer@acme-systems.io",
    )
    assert res_pending["status"] == "REJECTED"
    assert res_pending["error"] == "SUBSCRIPTION_NOT_CAPTURED"

    # Insert mock sub in CANCELLED
    cancelled_sub_id = "I-A2A-CANCELLED-SUB-02"
    _COMPLETED_SUBSCRIPTIONS[cancelled_sub_id] = {
        "subscription_id": cancelled_sub_id,
        "status": "CANCELLED",
        "buyer_email": "buyer@acme-systems.io",
        "tier_id": "ap2-gateway",
    }

    res_cancelled = await seller.provision_compute_node(
        subscription_id=cancelled_sub_id,
        buyer_email="buyer@acme-systems.io",
    )
    assert res_cancelled["status"] == "REJECTED"
    assert res_cancelled["error"] == "SUBSCRIPTION_NOT_ACTIVE"


@pytest.mark.asyncio
async def test_provision_compute_node_endpoint_hosts_by_tier(monkeypatch):
    """
    Item 2: Batch nodes must receive a 'batch-01' host (not gateway-01).
    Gateway nodes receive 'gateway-01' and cluster nodes receive 'cluster-01'.
    """
    monkeypatch.setattr(settings, "a2a_seller_profile", "ap2")
    seller = SellerAgent()

    # 1. Batch Worker
    batch_sub_id = "I-A2A-BATCH-HOST-01"
    _COMPLETED_SUBSCRIPTIONS[batch_sub_id] = {
        "subscription_id": batch_sub_id,
        "status": "ACTIVE",
        "buyer_email": "batch-buyer@acme.io",
        "tier_id": "ap2-batch",
        "agreed_monthly_rate": 49.99,
    }
    batch_res = await seller.provision_compute_node(
        subscription_id=batch_sub_id,
        buyer_email="batch-buyer@acme.io",
    )
    assert batch_res["status"] == "PROVISIONED"
    assert batch_res["endpoint"].startswith("mcp+https://batch-01.acme-systems.io/agents/node-batch-")

    # 2. Service Gateway
    gw_sub_id = "I-A2A-GW-HOST-02"
    _COMPLETED_SUBSCRIPTIONS[gw_sub_id] = {
        "subscription_id": gw_sub_id,
        "status": "ACTIVE",
        "buyer_email": "gw-buyer@acme.io",
        "tier_id": "ap2-gateway",
        "agreed_monthly_rate": 79.99,
    }
    gw_res = await seller.provision_compute_node(
        subscription_id=gw_sub_id,
        buyer_email="gw-buyer@acme.io",
    )
    assert gw_res["status"] == "PROVISIONED"
    assert gw_res["endpoint"].startswith("mcp+https://gateway-01.acme-systems.io/agents/node-gateway-")

    # 3. Enterprise Cluster
    cl_sub_id = "I-A2A-CL-HOST-03"
    _COMPLETED_SUBSCRIPTIONS[cl_sub_id] = {
        "subscription_id": cl_sub_id,
        "status": "ACTIVE",
        "buyer_email": "cl-buyer@acme.io",
        "tier_id": "ap2-cluster",
        "agreed_monthly_rate": 179.99,
    }
    cl_res = await seller.provision_compute_node(
        subscription_id=cl_sub_id,
        buyer_email="cl-buyer@acme.io",
    )
    assert cl_res["status"] == "PROVISIONED"
    assert cl_res["endpoint"].startswith("mcp+https://cluster-01.acme-systems.io/agents/node-cluster-")


@pytest.mark.asyncio
async def test_ap2_catalog_does_not_print_trades_aliases(monkeypatch):
    """
    Item 5: AP2 catalog and tiers outputs do not print trades aliases
    (solo-starter, fieldsmith-pro, pro-dispatch, etc.) in tier_id_aliases,
    while backward-compatible aliases still work when passed into resolve_plan.
    """
    monkeypatch.setattr(settings, "a2a_seller_profile", "ap2")
    seller = SellerAgent()

    # 1. inspect_subscription_tiers
    tiers = await seller.inspect_subscription_tiers()
    for plan in tiers["subscription_plans"]:
        aliases = plan.get("tier_id_aliases", [])
        for alias in aliases:
            match = FORBIDDEN_TRADES_WORDS_RE.search(alias)
            assert match is None, f"Forbidden trades term '{match.group(0)}' exposed in AP2 alias: {alias}"

    # 2. get_service_catalog
    catalog = await seller.get_service_catalog()
    public_aliases = catalog.get("tier_id_aliases", {})
    for alias_key in public_aliases.keys():
        match = FORBIDDEN_TRADES_WORDS_RE.search(alias_key)
        assert match is None, f"Forbidden trades alias key '{match.group(0)}' exposed in AP2 catalog: {alias_key}"

    # 3. But backward-compatible alias resolution STILL works internally
    assert resolve_plan("fieldsmith-pro", profile="ap2")["tier_id"] == "ap2-gateway"
    assert resolve_plan("solo-starter", profile="ap2")["tier_id"] == "ap2-batch"
    assert resolve_plan("pro-dispatch", profile="ap2")["tier_id"] == "ap2-cluster"
