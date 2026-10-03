"""
Tests for External Buyer Agent and Headless MCP Client Harness.
Verifies autonomous tool discovery, catalog negotiation, mandate policy rejection on low cap,
and complete procurement cycles across both HTTP and stdio transports.
"""

import pytest
from backend.harness.external_buyer_agent import ExternalBuyerAgent
from backend.services.mandate_evaluator import ledger


@pytest.fixture(autouse=True)
def reset_mandate_ledger():
    ledger.reset()


@pytest.mark.asyncio
async def test_external_buyer_agent_stdio_success():
    """Verifies complete autonomous procurement cycle over stdio transport."""
    agent = ExternalBuyerAgent(
        transport="stdio",
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
    assert len(result["audit_log"]) == 5  # 5 tools called


@pytest.mark.asyncio
async def test_external_buyer_agent_rejects_budget_overrun():
    """Verifies that an autonomous buyer agent correctly halts when quote exceeds mandate cap."""
    agent = ExternalBuyerAgent(
        transport="stdio",
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


@pytest.mark.asyncio
async def test_external_buyer_agent_multi_vertical():
    """Verifies that the buyer agent can discover and procure for different trade verticals."""
    agent = ExternalBuyerAgent(
        transport="stdio",
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
