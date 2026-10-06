"""
Integration Tests for Remote Streamable HTTP / SSE FastMCP Endpoint
and US-Domestic Only (NANP) Provisioning Constraints.
"""

import json
import pytest
from starlette.requests import Request
from fastapi.testclient import TestClient
from backend.server import app, mcp_wire_stream, mcp_get_endpoint
from backend.agents.seller_agent import seller_agent, _COMPLETED_SUBSCRIPTIONS

client = TestClient(app)


def test_mcp_get_status():
    """GET /mcp returns FastMCP machine-readable online status when Accept is not SSE."""
    res = client.get("/mcp")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "online"
    assert data["protocolVersion"] == "2024-11-05"
    assert data["transport"] == "streamable_http"
    assert data["mcp_endpoint"] == "/mcp"
    assert data["sse_endpoint"] == "/sse"
    assert data["tools_count"] == 7


@pytest.mark.asyncio
async def test_mcp_sse_handshake_endpoints():
    """GET /sse, GET /mcp/sse, and GET /mcp (Accept: text/event-stream) emit MCP 2024-11-05 discovery handshake."""
    for path in ["/sse", "/mcp/sse", "/api/mcp/sse"]:
        scope = {"type": "http", "method": "GET", "path": path, "headers": []}
        req = Request(scope)
        res = await mcp_wire_stream(req)
        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]
        gen = res.body_iterator
        chunk1 = await anext(gen)
        assert "event: endpoint" in chunk1
        assert "data: /mcp" in chunk1
        chunk2 = await anext(gen)
        assert "connected" in chunk2
        await gen.aclose()

    # Also verify GET /mcp with Accept: text/event-stream
    scope_mcp = {
        "type": "http",
        "method": "GET",
        "path": "/mcp",
        "headers": [(b"accept", b"text/event-stream")],
    }
    req_mcp = Request(scope_mcp)
    res_mcp = await mcp_get_endpoint(req_mcp)
    assert res_mcp.status_code == 200
    assert "text/event-stream" in res_mcp.headers["content-type"]
    gen_mcp = res_mcp.body_iterator
    chunk_mcp = await anext(gen_mcp)
    assert "event: endpoint" in chunk_mcp
    assert "data: /mcp" in chunk_mcp
    await gen_mcp.aclose()


def test_mcp_post_jsonrpc_tools_call():
    """POST /mcp handles initialize, tools/list, and tool execution."""
    # 1. initialize
    init_res = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": "test-init", "method": "initialize", "params": {}},
    )
    assert init_res.status_code == 200
    init_data = init_res.json()
    assert init_data["result"]["protocolVersion"] == "2024-11-05"
    assert init_data["result"]["serverInfo"]["name"] == "fieldsmith-pro-a2a-seller"

    # 2. tools/list
    tools_res = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": "test-tools", "method": "tools/list", "params": {}},
    )
    assert tools_res.status_code == 200
    tools = tools_res.json()["result"]["tools"]
    tool_names = [t["name"] for t in tools]
    assert len(tool_names) == 7
    assert "get_service_catalog" in tool_names
    assert "inspect_subscription_tiers" in tool_names
    assert "negotiate_tier_terms" in tool_names
    assert "evaluate_spending_mandate" in tool_names
    assert "purchase_subscription" in tool_names
    assert "provision_telecom_line" in tool_names
    assert "dispatch_zapier_mcp" in tool_names

    # 3. tools/call -> get_service_catalog
    call_res = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": "test-call-catalog",
            "method": "tools/call",
            "params": {"name": "get_service_catalog", "arguments": {}},
        },
    )
    assert call_res.status_code == 200
    content = json.loads(call_res.json()["result"]["content"][0]["text"])
    assert content["currency"] == "USD"
    assert len(content["plans"]) == 3

    # 4. tools/call -> negotiate_tier_terms
    neg_res = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": "test-call-neg",
            "method": "tools/call",
            "params": {
                "name": "negotiate_tier_terms",
                "arguments": {
                    "buyer_agent_id": "buyer-remote-test",
                    "contractor_email": "contractor.remote@example.com",
                    "tier_id": "solo-starter",
                    "monthly_budget_cap": 60.00,
                },
            },
        },
    )
    assert neg_res.status_code == 200
    neg_content = json.loads(neg_res.json()["result"]["content"][0]["text"])
    assert neg_content["status"] == "APPROVED"
    assert neg_content["agreed_monthly_rate"] == 49.99


@pytest.mark.asyncio
async def test_provision_us_domestic_nanp_validation():
    """Verify that provision_telecom_line strictly enforces 3-digit NANP US area codes."""
    sub_id = "I-TEST-US-DOMESTIC-01"
    contractor_email = "us.contractor@fieldsmith.pro"
    _COMPLETED_SUBSCRIPTIONS[sub_id] = {
        "subscription_id": sub_id,
        "status": "ACTIVE",
        "contractor_email": contractor_email,
        "tier_id": "solo-starter",
        "agreed_monthly_rate": 49.99,
        "subscriber_country_code": "US",
    }

    # 1. Valid US NANP area codes succeed
    for valid_ac in ["863", "813", "214", "305", "415", "212"]:
        res = await seller_agent.provision_telecom_line(
            subscription_id=sub_id,
            contractor_email=contractor_email,
            area_code=valid_ac,
        )
        assert res["status"] in ["ALLOCATED", "RETAINED"]
        assert res["assigned_did"].startswith("+1")

    # 2. Invalid or non-NANP area codes are strictly rejected
    invalid_codes = ["123", "020", "+44", "99", "abc", "1863", "86", "0", "011", "911", ""]
    for bad_ac in invalid_codes:
        res = await seller_agent.provision_telecom_line(
            subscription_id=sub_id,
            contractor_email=contractor_email,
            area_code=bad_ac,
        )
        assert res["status"] == "REJECTED"
        assert res["error"] == "US_DOMESTIC_ONLY"
        assert "NANP +1" in res["reason"]


@pytest.mark.asyncio
async def test_provision_foreign_subscriber_rejected():
    """Verify that provision_telecom_line rejects non-US subscriber accounts."""
    sub_id = "I-TEST-FOREIGN-SUB-01"
    contractor_email = "foreign.agent@example.co.uk"
    _COMPLETED_SUBSCRIPTIONS[sub_id] = {
        "subscription_id": sub_id,
        "status": "ACTIVE",
        "contractor_email": contractor_email,
        "tier_id": "solo-starter",
        "agreed_monthly_rate": 49.99,
        "subscriber_country_code": "GB",
    }

    res = await seller_agent.provision_telecom_line(
        subscription_id=sub_id,
        contractor_email=contractor_email,
        area_code="863",
    )
    assert res["status"] == "REJECTED"
    assert res["error"] == "US_DOMESTIC_ONLY"
    assert "strictly restricted to US entities" in res["reason"]
    assert "GB" in res["reason"]


def test_rest_provision_endpoint_us_domestic_error_code():
    """POST /api/agent/provision rejects invalid area codes with HTTP 403 US_DOMESTIC_ONLY."""
    sub_id = "I-TEST-REST-US-01"
    contractor_email = "rest.us@fieldsmith.pro"
    _COMPLETED_SUBSCRIPTIONS[sub_id] = {
        "subscription_id": sub_id,
        "status": "ACTIVE",
        "contractor_email": contractor_email,
        "tier_id": "solo-starter",
        "agreed_monthly_rate": 49.99,
        "subscriber_country_code": "US",
    }

    # International area code via REST
    res = client.post(
        "/api/agent/provision",
        json={
            "subscription_id": sub_id,
            "contractor_email": contractor_email,
            "area_code": "+44",
        },
    )
    assert res.status_code == 403
    data = res.json()["detail"]
    assert data["status"] == "REJECTED"
    assert data["error"] == "US_DOMESTIC_ONLY"
    assert "NANP +1" in data["reason"]
