"""
Tests for External Buyer Agent and Headless MCP Client Harness.
Verifies autonomous tool discovery, catalog negotiation, mandate policy rejection on low cap,
and complete procurement cycles across both HTTP and stdio transports in AP2 compute mode.
"""

import pytest
from backend.config import settings
from backend.harness.external_buyer_agent import ExternalBuyerAgent
from backend.services.mandate_evaluator import ledger


@pytest.fixture(autouse=True)
def reset_mandate_ledger():
    ledger.reset()


@pytest.mark.asyncio
async def test_external_buyer_agent_ap2_stdio_success(monkeypatch):
    """Verifies complete autonomous compute procurement cycle over stdio transport in AP2 profile."""
    monkeypatch.setenv("A2A_SELLER_PROFILE", "ap2")
    monkeypatch.setattr(settings, "a2a_seller_profile", "ap2")
    agent = ExternalBuyerAgent(
        transport="stdio",
        profile="ap2",
        budget_cap=100.00,
        verbose=False,
    )

    result = await agent.execute_autonomous_procurement()
    assert result["status"] == "COMPLETED"
    assert result["monthly_amount"] == 79.99
    assert len(result["mandate_proof_hash"]) == 64
    assert result["node_endpoint"].startswith("mcp+https://gateway-01.acme-systems.io/agents/node-gateway-")
    assert result["allocated_node_id"].startswith("node-gateway-")
    assert len(result["audit_log"]) == 5  # 5 tools called (catalog, mandate, purchase, provision_node, zapier)


@pytest.mark.asyncio
async def test_external_buyer_agent_ap2_counter_offer(monkeypatch):
    """Verifies AP2 buyer agent automatically accepts counter-offer down-tier to Batch Worker ($49.99)."""
    monkeypatch.setenv("A2A_SELLER_PROFILE", "ap2")
    monkeypatch.setattr(settings, "a2a_seller_profile", "ap2")
    agent = ExternalBuyerAgent(
        transport="stdio",
        profile="ap2",
        trade_id="ap2-gateway",
        budget_cap=60.00,  # Below $79.99 Gateway, but above $49.99 Batch
        verbose=False,
    )

    result = await agent.execute_autonomous_procurement()
    assert result["status"] == "COMPLETED"
    assert result["monthly_amount"] == 49.99
    assert "Batch" in result["selected_tier"]
    assert result["node_endpoint"].startswith("mcp+https://batch-01.acme-systems.io/agents/node-batch-")
    assert result["allocated_node_id"].startswith("node-batch-")


@pytest.mark.asyncio
async def test_external_buyer_agent_rejects_budget_overrun(monkeypatch):
    """Verifies that an autonomous buyer agent correctly halts when quote exceeds mandate cap."""
    monkeypatch.setenv("A2A_SELLER_PROFILE", "ap2")
    monkeypatch.setattr(settings, "a2a_seller_profile", "ap2")
    agent = ExternalBuyerAgent(
        transport="stdio",
        profile="ap2",
        contractor_name="Tight Budget Buyer",
        business_entity="Low Cap Compute LLC",
        contractor_email="lowcap@compute.org",
        trade_id="ap2-batch",
        budget_cap=40.00,  # Below $49.99/mo minimum tier cost
        verbose=False,
    )

    result = await agent.execute_autonomous_procurement()
    assert result["status"] == "REJECTED"
    assert "exceeds remaining monthly budget cap" in result["reason"]


@pytest.mark.asyncio
async def test_external_buyer_agent_ap2_cluster_success(monkeypatch):
    """Verifies high-volume enterprise cluster procurement over stdio transport."""
    monkeypatch.setenv("A2A_SELLER_PROFILE", "ap2")
    monkeypatch.setattr(settings, "a2a_seller_profile", "ap2")
    agent = ExternalBuyerAgent(
        transport="stdio",
        profile="ap2",
        contractor_name="Enterprise AI Fleet Buyer",
        business_entity="Enterprise AI Fleets Corp",
        contractor_email="procure@enterprise-ai.org",
        trade_id="ap2-cluster",
        budget_cap=250.00,
        verbose=False,
    )

    result = await agent.execute_autonomous_procurement()
    assert result["status"] == "COMPLETED"
    assert result["monthly_amount"] == 179.99
    assert "Cluster" in result["selected_tier"]
    assert result["node_endpoint"].startswith("mcp+https://cluster-01.acme-systems.io/agents/node-cluster-")
    assert result["allocated_node_id"].startswith("node-cluster-")
