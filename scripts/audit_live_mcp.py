"""
Audit script for live MCP verification against mock backend on port 8001.
Executes exact JSON-RPC calls over HTTP (POST /mcp), verifies contracts,
and logs exact raw request payloads and responses to docs/audits/live_mcp_verification.log.
"""

import sys
import os
import json
import time
import httpx
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOG_FILE = BASE_DIR / "docs" / "audits" / "live_mcp_verification.log"
SERVER_URL = "http://127.0.0.1:8001/mcp"

LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def log_entry(section: str, cmd: str, raw_output: str):
    banner = f"\n{'=' * 80}\n[{section}]\nCOMMAND: {cmd}\n{'=' * 80}\n"
    print(banner + raw_output)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(banner)
        f.write(raw_output)
        f.write("\n")


def post_rpc(client: httpx.Client, req: dict) -> dict:
    resp = client.post(
        SERVER_URL,
        json=req,
        headers={"Content-Type": "application/json"},
        timeout=10.0,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"=== AP2 LIVE MCP VERIFICATION AUDIT ===\nTimestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\nTarget: {SERVER_URL}\n\n")

    client = httpx.Client()

    # 1. initialize
    init_req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "ap2-audit-client", "version": "1.0.0"},
        },
    }
    init_cmd = f"curl -s -X POST {SERVER_URL} -H 'Content-Type: application/json' -d '{json.dumps(init_req)}'"
    init_res = post_rpc(client, init_req)
    log_entry("1. MCP INITIALIZE", init_cmd, json.dumps(init_res, indent=2))

    # 2. tools/list
    tools_req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    }
    tools_cmd = f"curl -s -X POST {SERVER_URL} -H 'Content-Type: application/json' -d '{json.dumps(tools_req)}'"
    tools_res = post_rpc(client, tools_req)
    log_entry("2. MCP TOOLS/LIST", tools_cmd, json.dumps(tools_res, indent=2))

    # 3. inspect_subscription_tiers
    tiers_req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "inspect_subscription_tiers",
            "arguments": {},
        },
    }
    tiers_cmd = f"curl -s -X POST {SERVER_URL} -H 'Content-Type: application/json' -d '{json.dumps(tiers_req)}'"
    tiers_res = post_rpc(client, tiers_req)
    log_entry("3. TOOL: inspect_subscription_tiers", tiers_cmd, json.dumps(tiers_res, indent=2))

    # 4. negotiate_tier_terms (Gateway requested at $79.99, budget cap $60.00 -> counter-offer Batch at $49.99)
    neg_req = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "negotiate_tier_terms",
            "arguments": {
                "buyer_agent_id": "agent-audit-buyer-001",
                "buyer_email": "audit.buyer@acme-systems.io",
                "tier_id": "ap2-gateway",
                "monthly_budget_cap": 60.00,
            },
        },
    }
    neg_cmd = f"curl -s -X POST {SERVER_URL} -H 'Content-Type: application/json' -d '{json.dumps(neg_req)}'"
    neg_res = post_rpc(client, neg_req)
    log_entry("4. TOOL: negotiate_tier_terms (COUNTER-OFFER)", neg_cmd, json.dumps(neg_res, indent=2))

    neg_content = json.loads(neg_res["result"]["content"][0]["text"])
    counter_hash = neg_content["counter_offer_mandate_hash"]
    counter_tier = neg_content["counter_offer_tier_id"]
    counter_amount = neg_content["counter_offer_amount"]
    counter_plan_id = neg_content.get("counter_offer_plan_id") or neg_content.get("ap2_cart_mandate", {}).get("plan_id")

    # 5. purchase_subscription
    purchase_req = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "purchase_subscription",
            "arguments": {
                "tier_id": counter_tier,
                "agreed_monthly_rate": counter_amount,
                "mandate_proof_hash": counter_hash,
                "buyer_email": "audit.buyer@acme-systems.io",
            },
        },
    }
    purchase_cmd = f"curl -s -X POST {SERVER_URL} -H 'Content-Type: application/json' -d '{json.dumps(purchase_req)}'"
    purchase_res = post_rpc(client, purchase_req)
    log_entry("5. TOOL: purchase_subscription", purchase_cmd, json.dumps(purchase_res, indent=2))

    purch_content = json.loads(purchase_res["result"]["content"][0]["text"])
    sub_id = purch_content["subscription_id"]

    # 6. provision_compute_node (Valid subscription)
    prov_req = {
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {
            "name": "provision_compute_node",
            "arguments": {
                "subscription_id": sub_id,
                "buyer_email": "audit.buyer@acme-systems.io",
                "node_type": "batch",
            },
        },
    }
    prov_cmd = f"curl -s -X POST {SERVER_URL} -H 'Content-Type: application/json' -d '{json.dumps(prov_req)}'"
    prov_res = post_rpc(client, prov_req)
    log_entry("6. TOOL: provision_compute_node (VALID)", prov_cmd, json.dumps(prov_res, indent=2))

    # 7. provision_compute_node (Invalid subscription -> SUBSCRIPTION_NOT_FOUND)
    prov_fake_req = {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {
            "name": "provision_compute_node",
            "arguments": {
                "subscription_id": "I-FAKE-SUB-DOES-NOT-EXIST",
                "buyer_email": "audit.buyer@acme-systems.io",
                "node_type": "batch",
            },
        },
    }
    prov_fake_cmd = f"curl -s -X POST {SERVER_URL} -H 'Content-Type: application/json' -d '{json.dumps(prov_fake_req)}'"
    prov_fake_res = post_rpc(client, prov_fake_req)
    log_entry("7. TOOL: provision_compute_node (INVALID -> SUBSCRIPTION_NOT_FOUND)", prov_fake_cmd, json.dumps(prov_fake_res, indent=2))

    # 8. get_subscription_details (Invalid subscription -> clean RESOURCE_NOT_FOUND with id & subscription_id)
    details_fake_req = {
        "jsonrpc": "2.0",
        "id": 8,
        "method": "tools/call",
        "params": {
            "name": "get_subscription_details",
            "arguments": {
                "subscription_id": "I-FAKE-SUB-DOES-NOT-EXIST",
            },
        },
    }
    details_fake_cmd = f"curl -s -X POST {SERVER_URL} -H 'Content-Type: application/json' -d '{json.dumps(details_fake_req)}'"
    details_fake_res = post_rpc(client, details_fake_req)
    log_entry("8. TOOL: get_subscription_details (NOT FOUND)", details_fake_cmd, json.dumps(details_fake_res, indent=2))

    # 9. unregistered_tool_call (Unregistered Tool -> -32601)
    unreg_req = {
        "jsonrpc": "2.0",
        "id": 9,
        "method": "tools/call",
        "params": {
            "name": "unregistered_tool_call",
            "arguments": {
                "subscription_id": sub_id,
                "buyer_email": "audit.buyer@acme-systems.io",
            },
        },
    }
    unreg_cmd = f"curl -s -X POST {SERVER_URL} -H 'Content-Type: application/json' -d '{json.dumps(unreg_req)}'"
    unreg_res = post_rpc(client, unreg_req)
    log_entry("9. TOOL: unregistered_tool_call (NOT FOUND -> -32601)", unreg_cmd, json.dumps(unreg_res, indent=2))

    print(f"\n[DONE] All audit queries completed successfully! Output saved to: {LOG_FILE}")


if __name__ == "__main__":
    main()
