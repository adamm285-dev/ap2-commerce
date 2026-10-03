"""
Tests for FieldSmith Pro MCP (Model Context Protocol) Server.
Verifies JSON-RPC 2.0 initialize, tools/list, and tools/call endpoints.
"""

import pytest
from backend.mcp_server import process_mcp_request


@pytest.mark.asyncio
async def test_mcp_initialize():
    req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "test-agent", "version": "1.0"},
        },
    }
    resp = await process_mcp_request(req)
    assert resp["jsonrpc"] == "2.0"
    assert resp["id"] == 1
    assert "capabilities" in resp["result"]
    assert resp["result"]["serverInfo"]["name"] == "fieldsmith-pro-a2a-seller"


@pytest.mark.asyncio
async def test_mcp_tools_list():
    req = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    }
    resp = await process_mcp_request(req)
    assert resp["id"] == 2
    tools = resp["result"]["tools"]
    tool_names = [t["name"] for t in tools]
    assert "get_service_catalog" in tool_names
    assert "evaluate_spending_mandate" in tool_names
    assert "provision_telecom_line" in tool_names
    assert "dispatch_zapier_mcp" in tool_names


@pytest.mark.asyncio
async def test_mcp_tools_call_catalog():
    req = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "get_service_catalog",
            "arguments": {},
        },
    }
    resp = await process_mcp_request(req)
    assert resp["id"] == 3
    assert not resp["result"]["isError"]
    content = resp["result"]["content"][0]["text"]
    assert "flooring-tile" in content
    assert "79.99" in content


@pytest.mark.asyncio
async def test_mcp_tools_call_mandate():
    req = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {
            "name": "evaluate_spending_mandate",
            "arguments": {
                "buyer_agent_id": "marcus-buyer-01",
                "amount": 79.99,
                "recurrence": "monthly",
                "category": "TELEPHONY_AI_SCREENER",
                "monthly_budget_cap": 100.00,
            },
        },
    }
    resp = await process_mcp_request(req)
    assert resp["id"] == 4
    assert not resp["result"]["isError"]
    content = resp["result"]["content"][0]["text"]
    assert "mandateProofHash" in content or "mandate_proof_hash" in content
