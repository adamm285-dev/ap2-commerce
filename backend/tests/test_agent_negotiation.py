"""
End-to-End Integration Tests for Autonomous Agent-to-Agent (A2A) Negotiation.
"""

import pytest
from ..agents.buyer_agent import BuyerAgent
from ..services.mandate_evaluator import ledger


@pytest.fixture(autouse=True)
def reset_ledger():
    ledger.reset()


@pytest.mark.asyncio
async def test_autonomous_a2a_cycle_approved():
    buyer = BuyerAgent(
        agent_id="test-buyer-agent",
        monthly_budget_cap=100.00,
        contractor_email="test@floorsmith.pro",
    )
    result = await buyer.run_autonomous_onboarding_cycle(
        target_trade="flooring-tile"
    )

    assert result["status"] == "ACTIVE_SUBSCRIPTION"
    assert result["monthly_amount"] == 79.99
    assert result["assigned_did"].startswith("+1863")
    assert result["subscription_id"].startswith("I-A2A-")
    assert len(result["mandate_proof"]) == 64


@pytest.mark.asyncio
async def test_autonomous_a2a_cycle_rejected_on_insufficient_budget():
    buyer = BuyerAgent(
        agent_id="tight-budget-agent",
        monthly_budget_cap=40.00,  # $40 cap < $49.99 minimum tier
        contractor_email="test@floorsmith.pro",
    )
    result = await buyer.run_autonomous_onboarding_cycle(
        target_trade="flooring-tile"
    )

    assert result["status"] == "REJECTED"
    assert "exceeds remaining monthly budget cap" in result["reason"]
