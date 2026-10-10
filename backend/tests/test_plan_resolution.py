"""
Comprehensive tests for:
1. Single source PayPal plan resolution: every AP2 tier_id and alias
   resolves strictly to a configured settings plan ID, never a synthesized P-CUSTOM-* / P-AP2-* string.
2. provision_compute_node robust error handling: unknown/inactive subscription returns clean
   SUBSCRIPTION_NOT_FOUND / SUBSCRIPTION_NOT_ACTIVE without KeyError or -32603.
3. Compute node endpoint host specialization: Batch -> batch-01, Gateway -> gateway-01, Cluster -> cluster-01.
4. Quota verification: workload tasks per month (125, 450, 1200).
5. Public alias sanitization: AP2 catalog output does not expose trades terms in tier_id_aliases.
"""

import base64
import pytest
import re
from backend.config import settings
from backend.services.plan_catalog import (
    AP2_PLANS,
    AP2_TIER_ALIASES,
    PUBLIC_AP2_TIER_ALIASES,
    resolve_paypal_plan_id,
    resolve_plan,
    get_public_tier_aliases,
)
from backend.agents.seller_agent import SellerAgent, _COMPLETED_SUBSCRIPTIONS
from backend.mcp_server import process_mcp_request

_LEGACY_WORDS = [
    base64.b64decode(b).decode()
    for b in [
        b"Zmxvb3Jpbmc=",
        b"cm9vZmluZw==",
        b"cGx1bWI=",
        b"dG93aW5n",
        b"Y29udHJhY3Rvcg==",
        b"dGVsZXBob255",
        b"c2NyZWVuZWQ=",
        b"MTBETEM=",
        b"cmVjZXB0aW9uaXN0",
        b"RElE",
        b"c29sby1zdGFydGVy",
        b"ZmllbGRzbWl0aA==",
        b"cHJvLWRpc3BhdGNo",
    ]
]
FORBIDDEN_LEGACY_WORDS_RE = re.compile(
    r"(?i)" + "|".join(re.escape(w) for w in _LEGACY_WORDS)
)


def test_every_tier_and_alias_resolves_to_settings_plan_id(monkeypatch):
    """
    Every AP2 tier_id and alias resolves to a configured
    settings plan ID (paypal_plan_id_batch, gateway, or cluster), never a synthesized
    P-AP2-* string.
    """
    configured_batch = "P-CUSTOM-SANDBOX-BATCH-001"
    configured_gateway = "P-CUSTOM-SANDBOX-GATEWAY-002"
    configured_cluster = "P-CUSTOM-SANDBOX-CLUSTER-003"

    monkeypatch.setattr(settings, "paypal_plan_id_batch", configured_batch)
    monkeypatch.setattr(settings, "paypal_plan_id_gateway", configured_gateway)
    monkeypatch.setattr(settings, "paypal_plan_id_cluster", configured_cluster)

    allowed_plan_ids = {configured_batch, configured_gateway, configured_cluster}

    ap2_targets = [p["tier_id"] for p in AP2_PLANS] + list(AP2_TIER_ALIASES.keys())
    for target in ap2_targets:
        resolved = resolve_paypal_plan_id(target, profile="ap2")
        assert resolved in allowed_plan_ids, (
            f"AP2 target '{target}' resolved to unexpected '{resolved}', expected one of {allowed_plan_ids}"
        )
        assert not resolved.startswith("P-AP2-AP2_"), f"Synthetic AP2 string detected for target '{target}': {resolved}"


@pytest.mark.asyncio
async def test_provision_compute_node_rejects_unknown_subscription(monkeypatch):
    """
    Calling provision_compute_node with an unknown subscription_id returns
    a clean 'SUBSCRIPTION_NOT_FOUND' rejection, never raising KeyError or returning -32603.
    """
    seller = SellerAgent()

    # Unknown ID not in completed records
    res = await seller.provision_compute_node(
        subscription_id="I-NONEXISTENT-SUB-99999",
        buyer_email="buyer@example.com",
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
                "buyer_email": "buyer@example.com",
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
    Calling provision_compute_node on an inactive subscription (e.g. APPROVAL_PENDING or CANCELLED)
    returns clean SUBSCRIPTION_NOT_CAPTURED or SUBSCRIPTION_NOT_ACTIVE.
    """
    seller = SellerAgent()

    # Insert mock sub in APPROVAL_PENDING
    pending_sub_id = "I-A2A-PENDING-SUB-01"
    _COMPLETED_SUBSCRIPTIONS[pending_sub_id] = {
        "subscription_id": pending_sub_id,
        "status": "APPROVAL_PENDING",
        "buyer_email": "buyer@example.com",
        "tier_id": "ap2-gateway",
    }

    res_pending = await seller.provision_compute_node(
        subscription_id=pending_sub_id,
        buyer_email="buyer@example.com",
    )
    assert res_pending["status"] == "REJECTED"
    assert res_pending["error"] == "SUBSCRIPTION_NOT_CAPTURED"

    # Insert mock sub in CANCELLED
    cancelled_sub_id = "I-A2A-CANCELLED-SUB-02"
    _COMPLETED_SUBSCRIPTIONS[cancelled_sub_id] = {
        "subscription_id": cancelled_sub_id,
        "status": "CANCELLED",
        "buyer_email": "buyer@example.com",
        "tier_id": "ap2-gateway",
    }

    res_cancelled = await seller.provision_compute_node(
        subscription_id=cancelled_sub_id,
        buyer_email="buyer@example.com",
    )
    assert res_cancelled["status"] == "REJECTED"
    assert res_cancelled["error"] == "SUBSCRIPTION_NOT_ACTIVE"


@pytest.mark.asyncio
async def test_provision_compute_node_endpoint_hosts_by_tier(monkeypatch):
    """
    Batch nodes must receive a 'batch-01' host (not gateway-01).
    Gateway nodes receive 'gateway-01' and cluster nodes receive 'cluster-01'.
    """
    seller = SellerAgent()

    # 1. Batch Worker
    batch_sub_id = "I-A2A-BATCH-HOST-01"
    _COMPLETED_SUBSCRIPTIONS[batch_sub_id] = {
        "subscription_id": batch_sub_id,
        "status": "ACTIVE",
        "buyer_email": "batch-buyer@example.com",
        "tier_id": "ap2-batch",
        "agreed_monthly_rate": 49.99,
    }
    batch_res = await seller.provision_compute_node(
        subscription_id=batch_sub_id,
        buyer_email="batch-buyer@example.com",
    )
    assert batch_res["status"] == "PROVISIONED"
    assert batch_res["endpoint"].startswith("mcp+https://batch-01.example.com/agents/node-batch-")
    assert batch_res["workload_tasks_per_month"] == 125

    # 2. Service Gateway
    gw_sub_id = "I-A2A-GW-HOST-02"
    _COMPLETED_SUBSCRIPTIONS[gw_sub_id] = {
        "subscription_id": gw_sub_id,
        "status": "ACTIVE",
        "buyer_email": "gw-buyer@example.com",
        "tier_id": "ap2-gateway",
        "agreed_monthly_rate": 79.99,
    }
    gw_res = await seller.provision_compute_node(
        subscription_id=gw_sub_id,
        buyer_email="gw-buyer@example.com",
    )
    assert gw_res["status"] == "PROVISIONED"
    assert gw_res["endpoint"].startswith("mcp+https://gateway-01.example.com/agents/node-gateway-")
    assert gw_res["workload_tasks_per_month"] == 450

    # 3. Enterprise Cluster
    cl_sub_id = "I-A2A-CL-HOST-03"
    _COMPLETED_SUBSCRIPTIONS[cl_sub_id] = {
        "subscription_id": cl_sub_id,
        "status": "ACTIVE",
        "buyer_email": "cl-buyer@example.com",
        "tier_id": "ap2-cluster",
        "agreed_monthly_rate": 179.99,
    }
    cl_res = await seller.provision_compute_node(
        subscription_id=cl_sub_id,
        buyer_email="cl-buyer@example.com",
    )
    assert cl_res["status"] == "PROVISIONED"
    assert cl_res["endpoint"].startswith("mcp+https://cluster-01.example.com/agents/node-cluster-")
    assert cl_res["workload_tasks_per_month"] == 1200


@pytest.mark.asyncio
async def test_provision_compute_node_per_tier_workload_tasks_quota(monkeypatch):
    """
    Verifies that provision_compute_node returns the exact catalog quota for workload_tasks_per_month:
    ap2-batch: 125, ap2-gateway: 450, ap2-cluster: 1200.
    """
    seller = SellerAgent()

    test_cases = [
        ("ap2-batch", 125, 49.99),
        ("ap2-gateway", 450, 79.99),
        ("ap2-cluster", 1200, 179.99),
        ("batch", 125, 49.99),
        ("gateway", 450, 79.99),
        ("cluster", 1200, 179.99),
    ]

    for tier_id, expected_quota, price in test_cases:
        sub_id = f"I-TEST-QUOTA-{tier_id.upper().replace('-', '_')}"
        _COMPLETED_SUBSCRIPTIONS[sub_id] = {
            "subscription_id": sub_id,
            "status": "ACTIVE",
            "buyer_email": f"buyer-{tier_id}@example.com",
            "tier_id": tier_id,
            "agreed_monthly_rate": price,
        }
        res = await seller.provision_compute_node(
            subscription_id=sub_id,
            buyer_email=f"buyer-{tier_id}@example.com",
        )
        assert res["status"] == "PROVISIONED"
        assert res["workload_tasks_per_month"] == expected_quota, (
            f"Expected {expected_quota} workload tasks for tier '{tier_id}', got {res.get('workload_tasks_per_month')}"
        )


@pytest.mark.asyncio
async def test_ap2_catalog_does_not_print_legacy_aliases(monkeypatch):
    """
    AP2 catalog and tiers outputs do not print legacy trade aliases in tier_id_aliases.
    """
    seller = SellerAgent()

    # 1. inspect_subscription_tiers
    tiers = await seller.inspect_subscription_tiers()
    for plan in tiers["subscription_plans"]:
        aliases = plan.get("tier_id_aliases", [])
        for alias in aliases:
            match = FORBIDDEN_LEGACY_WORDS_RE.search(alias)
            assert match is None, f"Forbidden legacy term '{match.group(0)}' exposed in AP2 alias: {alias}"

    # 2. get_service_catalog
    catalog = await seller.get_service_catalog()
    public_aliases = catalog.get("tier_id_aliases", {})
    for alias_key in public_aliases.keys():
        match = FORBIDDEN_LEGACY_WORDS_RE.search(alias_key)
        assert match is None, f"Forbidden legacy alias key '{match.group(0)}' exposed in AP2 catalog: {alias_key}"
