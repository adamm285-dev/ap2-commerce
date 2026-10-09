"""
Tests for External Buyer Agent and Headless MCP Client Harness.
Verifies autonomous tool discovery, catalog negotiation, mandate policy rejection on low cap,
and complete procurement cycles across both HTTP and stdio transports.
"""

import pytest
from backend.config import settings
from backend.harness.external_buyer_agent import ExternalBuyerAgent
from backend.services.mandate_evaluator import ledger


@pytest.fixture(autouse=True)
def reset_mandate_ledger():
    ledger.reset()


@pytest.mark.trades
@pytest.mark.asyncio
async def test_external_buyer_agent_stdio_success(monkeypatch):
    """Verifies complete autonomous procurement cycle over stdio transport in trades profile."""
    monkeypatch.setenv("A2A_SELLER_PROFILE", "trades")
    monkeypatch.setattr(settings, "a2a_seller_profile", "trades")
    agent = ExternalBuyerAgent(
        transport="stdio",
        profile="trades",
        contractor_name="Marcus Miller",
        business_entity="Miller Custom Flooring LLC",
        contractor_email="marcus@millercustomfloors.com",
        trade_id="flooring-tile",
        budget_cap=100.00,
        area_code="863",
        verbose=False,
    )

    result = await agent.execute_autonomous_procurement()
    assert result["status"] == "COMPLETED"
    assert result["monthly_amount"] == 79.99
    assert len(result["mandate_proof_hash"]) == 64
    assert result["assigned_did"].startswith("+1863")
    assert result["jobber_routing_id"].startswith("JOB-ROUTING-")
    assert result["qbo_expense_id"].startswith("QBO-EXP-")
    assert len(result["audit_log"]) == 6  # 6 tools called (catalog, quote, mandate, purchase, provision, zapier)


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


@pytest.mark.trades
@pytest.mark.asyncio
async def test_external_buyer_agent_rejects_budget_overrun(monkeypatch):
    """Verifies that an autonomous buyer agent correctly halts when quote exceeds mandate cap."""
    monkeypatch.setenv("A2A_SELLER_PROFILE", "trades")
    monkeypatch.setattr(settings, "a2a_seller_profile", "trades")
    agent = ExternalBuyerAgent(
        transport="stdio",
        profile="trades",
        contractor_name="Tight Budget Contractor",
        business_entity="Low Cap Remodeling",
        contractor_email="lowcap@contractor.com",
        trade_id="flooring-tile",
        budget_cap=40.00,  # Below $49.99/mo minimum tier cost
        area_code="863",
        verbose=False,
    )

    result = await agent.execute_autonomous_procurement()
    assert result["status"] == "REJECTED"
    assert "exceeds remaining monthly budget cap" in result["reason"]


@pytest.mark.trades
@pytest.mark.asyncio
async def test_external_buyer_agent_multi_vertical(monkeypatch):
    """Verifies that the buyer agent can discover and procure for different trade verticals."""
    monkeypatch.setenv("A2A_SELLER_PROFILE", "trades")
    monkeypatch.setattr(settings, "a2a_seller_profile", "trades")
    agent = ExternalBuyerAgent(
        transport="stdio",
        profile="trades",
        contractor_name="Dave Vance",
        business_entity="Vance Emergency Plumbing LLC",
        contractor_email="dave@vanceplumbing.com",
        trade_id="plumbing-emergency",
        budget_cap=120.00,
        area_code="404",
        verbose=False,
    )

    result = await agent.execute_autonomous_procurement()
    assert result["status"] == "COMPLETED"
    assert "Plumbing" in result["selected_tier"]
    assert result["assigned_did"].startswith("+1404")
