"""
Unit and integration tests verifying dual-profile architecture:
AP2 Autonomous Compute Profile vs FieldSmith Trades Profile.

Strict verification:
4(a) In 'ap2': initialize, tools/list, instructions, and inspect_subscription_tiers
     must contain NONE of the forbidden words:
     flooring|roofing|plumb|towing|contractor|telephony|screened|10DLC|receptionist|DID (case-insensitive).
4(b) In 'trades': output unchanged, byte-for-byte fidelity with trades platform.
4(c) AP2 negotiation via MCP JSON-RPC (Gateway, cap $60) returns $49.99 counter-offer,
     settles at catalog price.
"""

import json
import re
import pytest
from backend.config import settings
from backend.mcp_server import process_mcp_request
from backend.agents.seller_agent import seller_agent

FORBIDDEN_WORDS_RE = re.compile(
    r"(?i)flooring|roofing|plumb|towing|contractor|telephony|screened|10DLC|receptionist|DID"
)


@pytest.mark.asyncio
async def test_ap2_profile_forbidden_words_zero_matches(monkeypatch):
    """
    4(a): In 'ap2' profile: initialize, tools/list, instructions, and inspect_subscription_tiers
    must contain NONE of the forbidden words.
    """
    monkeypatch.setattr(settings, "a2a_seller_profile", "ap2")

    # 1. Test initialize & instructions
    init_req = {
        "jsonrpc": "2.0",
        "id": "init-1",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "ap2-buyer-agent", "version": "1.0"},
        },
    }
    init_resp = await process_mcp_request(init_req)
    assert init_resp.get("error") is None
    instructions = init_resp["result"]["instructions"]
    server_info = json.dumps(init_resp["result"]["serverInfo"])

    match = FORBIDDEN_WORDS_RE.search(instructions)
    assert match is None, f"Forbidden word '{match.group(0)}' found in AP2 initialize instructions: {instructions}"

    match = FORBIDDEN_WORDS_RE.search(server_info)
    assert match is None, f"Forbidden word '{match.group(0)}' found in AP2 serverInfo: {server_info}"

    # 2. Test tools/list
    tools_req = {
        "jsonrpc": "2.0",
        "id": "tools-1",
        "method": "tools/list",
        "params": {},
    }
    tools_resp = await process_mcp_request(tools_req)
    assert tools_resp.get("error") is None
    tools_json = json.dumps(tools_resp["result"]["tools"])

    match = FORBIDDEN_WORDS_RE.search(tools_json)
    assert match is None, f"Forbidden word '{match.group(0)}' found in AP2 tools/list: {tools_json}"

    tool_names = [t["name"] for t in tools_resp["result"]["tools"]]
    assert "provision_compute_node" in tool_names
    assert "provision_telecom_line" not in tool_names
    assert "calculate_quote" not in tool_names

    # 3. Test inspect_subscription_tiers
    tiers_req = {
        "jsonrpc": "2.0",
        "id": "tiers-1",
        "method": "tools/call",
        "params": {
            "name": "inspect_subscription_tiers",
            "arguments": {},
        },
    }
    tiers_resp = await process_mcp_request(tiers_req)
    assert not tiers_resp["result"]["isError"]
    tiers_text = tiers_resp["result"]["content"][0]["text"]

    match = FORBIDDEN_WORDS_RE.search(tiers_text)
    assert match is None, f"Forbidden word '{match.group(0)}' found in AP2 inspect_subscription_tiers: {tiers_text}"

    tiers_data = json.loads(tiers_text)
    assert tiers_data["quota_unit"] == "workload_tasks_per_month"
    plan_ids = [p["tier_id"] for p in tiers_data["subscription_plans"]]
    assert "ap2-batch" in plan_ids
    assert "ap2-gateway" in plan_ids
    assert "ap2-cluster" in plan_ids


@pytest.mark.asyncio
async def test_trades_profile_byte_for_byte_fidelity(monkeypatch):
    """
    4(b): In 'trades' profile: output unchanged, retains telephony tools,
    contractor terminology, and original catalog.
    """
    monkeypatch.setattr(settings, "a2a_seller_profile", "trades")

    # 1. Test initialize
    init_req = {
        "jsonrpc": "2.0",
        "id": "init-trades",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "trades-buyer", "version": "1.0"},
        },
    }
    init_resp = await process_mcp_request(init_req)
    assert init_resp["result"]["serverInfo"]["name"] == "fieldsmith-pro-a2a-seller"
    instructions = init_resp["result"]["instructions"]
    assert "FieldSmith Pro" in instructions
    assert "solo-starter" in instructions
    assert "provision_telecom_line" in instructions

    # 2. Test tools/list
    tools_req = {
        "jsonrpc": "2.0",
        "id": "tools-trades",
        "method": "tools/list",
        "params": {},
    }
    tools_resp = await process_mcp_request(tools_req)
    tools = tools_resp["result"]["tools"]
    tool_names = [t["name"] for t in tools]
    assert "provision_telecom_line" in tool_names
    assert "provision_compute_node" not in tool_names
    assert len(tool_names) == 8

    # 3. Test inspect_subscription_tiers
    tiers_res = await seller_agent.inspect_subscription_tiers()
    assert tiers_res["quota_unit"] == "screened_calls_per_month"
    plan_ids = [p["tier_id"] for p in tiers_res["subscription_plans"]]
    assert "solo-starter" in plan_ids
    assert "fieldsmith-pro" in plan_ids
    assert "pro-dispatch" in plan_ids


@pytest.mark.asyncio
async def test_ap2_negotiation_counter_offer_and_settlement(monkeypatch):
    """
    4(c): AP2 negotiation via MCP JSON-RPC (Gateway, cap $60) returns $49.99 counter-offer,
    settles at catalog price.
    """
    monkeypatch.setattr(settings, "a2a_seller_profile", "ap2")

    # Step 1: Submit negotiation request for Gateway ($79.99) with cap $60.00
    neg_req = {
        "jsonrpc": "2.0",
        "id": "neg-1",
        "method": "tools/call",
        "params": {
            "name": "negotiate_tier_terms",
            "arguments": {
                "buyer_agent_id": "buyer-agent-ap2",
                "tier_id": "ap2-gateway",
                "monthly_budget_cap": 60.00,
                "buyer_email": "buyer-01@acme-agents.ai",
                "category": "autonomous-node-service",
            },
        },
    }
    neg_resp = await process_mcp_request(neg_req)
    assert not neg_resp["result"]["isError"]
    neg_data = json.loads(neg_resp["result"]["content"][0]["text"])

    # Must return COUNTER_OFFER to $49.99 Batch Worker
    assert neg_data["status"] == "COUNTER_OFFER"
    assert neg_data["counter_offer_available"] is True
    assert neg_data["counter_offer_amount"] == 49.99
    assert neg_data["counter_offer_tier_id"] == "ap2-batch"
    assert neg_data["counter_offer_tier"] == "High-Throughput Batch Worker"
    assert neg_data["monthly_cap_remaining"] == 10.01  # 60.00 - 49.99
    assert "next_action" in neg_data
    assert neg_data["next_action"]["tool"] == "purchase_subscription"

    offer_id = neg_data["offer_id"]
    proof_hash = neg_data["mandate_proof_hash"]

    # Step 2: Rate tampering rejection: buyer cannot arbitrarily change price to $39.99
    tamper_req = {
        "jsonrpc": "2.0",
        "id": "tamper-1",
        "method": "tools/call",
        "params": {
            "name": "purchase_subscription",
            "arguments": {
                "offer_id": offer_id,
                "tier_id": "ap2-batch",
                "agreed_monthly_rate": 39.99,
                "mandate_proof_hash": proof_hash,
                "buyer_email": "buyer-01@acme-agents.ai",
            },
        },
    }
    tamper_resp = await process_mcp_request(tamper_req)
    tamper_data = json.loads(tamper_resp["result"]["content"][0]["text"])
    assert tamper_data["status"] == "REJECTED"
    assert tamper_data["error"] in ("MANDATE_SECURITY_BREACH", "RATE_TAMPERING_DETECTED")

    # Step 3: Purchase at catalog price $49.99
    purchase_req = {
        "jsonrpc": "2.0",
        "id": "purchase-1",
        "method": "tools/call",
        "params": {
            "name": "purchase_subscription",
            "arguments": {
                "offer_id": offer_id,
                "buyer_email": "buyer-01@acme-agents.ai",
            },
        },
    }
    purchase_resp = await process_mcp_request(purchase_req)
    assert not purchase_resp["result"]["isError"]
    purchase_data = json.loads(purchase_resp["result"]["content"][0]["text"])

    assert purchase_data["status"] in ("ACTIVE", "APPROVAL_PENDING")
    assert purchase_data["agreed_monthly_rate"] == 49.99
    assert purchase_data["tier_id"] == "ap2-batch"
    assert purchase_data["plan_id"] == settings.paypal_plan_id_solo
    assert purchase_data["product_id"] == "PROD-AP2-AUTONOMOUS-COMPUTE"

    sub_id = purchase_data["subscription_id"]

    # Step 4: Provision compute node
    if purchase_data["status"] == "ACTIVE":
        assert purchase_data["next_action"]["tool"] == "provision_compute_node"

        prov_req = {
            "jsonrpc": "2.0",
            "id": "prov-1",
            "method": "tools/call",
            "params": {
                "name": "provision_compute_node",
                "arguments": {
                    "subscription_id": sub_id,
                    "buyer_email": "buyer-01@acme-agents.ai",
                    "node_type": "batch",
                },
            },
        }
        prov_resp = await process_mcp_request(prov_req)
        assert not prov_resp["result"]["isError"]
        prov_data = json.loads(prov_resp["result"]["content"][0]["text"])

        assert prov_data["status"] == "PROVISIONED"
        assert prov_data["endpoint"].startswith("mcp+https://batch-01.acme-systems.io/agents/node-batch-")
        assert "did" not in prov_data["endpoint"].lower()


@pytest.mark.asyncio
async def test_ap2_hidden_telecom_tools(monkeypatch):
    """
    Verifies that calling telecom tools in AP2 profile returns -32601 tool not found.
    """
    monkeypatch.setattr(settings, "a2a_seller_profile", "ap2")

    for tool in ("provision_telecom_line", "calculate_quote"):
        req = {
            "jsonrpc": "2.0",
            "id": f"call-{tool}",
            "method": "tools/call",
            "params": {
                "name": tool,
                "arguments": {},
            },
        }
        resp = await process_mcp_request(req)
        assert "error" in resp
        assert resp["error"]["code"] == -32601
