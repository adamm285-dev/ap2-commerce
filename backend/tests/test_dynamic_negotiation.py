"""
Tests for Dynamic Tier Negotiation and Autonomous Counter-Offer Resolution.
"""

import pytest
from backend.models import SpendingMandateRequest, RecurrenceType
from backend.services.mandate_evaluator import evaluate_spending_mandate, ledger
from backend.harness.external_buyer_agent import ExternalBuyerAgent


@pytest.fixture(autouse=True)
def reset_ledger():
    ledger.reset()


def test_mandate_generates_dynamic_counter_offer():
    """When requested amount ($79.99) exceeds budget cap ($60.00), seller proposes counter-offer at $49.99."""
    req = SpendingMandateRequest(
        buyerAgentId="buyer-budget-constrained",
        amount=79.99,
        recurrence=RecurrenceType.MONTHLY,
        category="COMPUTE_NODE_SERVICE",
        monthlyBudgetCap=60.00,
    )
    res = evaluate_spending_mandate(req)
    assert res.approved is False
    assert res.counter_offer_available is True
    assert res.counter_offer_amount == 49.99
    assert res.counter_offer_tier == "High-Throughput Batch Worker"
    assert "Counter-offer available" in res.reason


def test_buyer_accepts_and_binds_counter_offer():
    """Submitting the negotiated counter-offer rate ($49.99) within budget cap ($60.00) is approved."""
    req = SpendingMandateRequest(
        buyerAgentId="buyer-budget-constrained",
        amount=49.99,
        recurrence=RecurrenceType.MONTHLY,
        category="COMPUTE_NODE_SERVICE",
        monthlyBudgetCap=60.00,
    )
    res = evaluate_spending_mandate(req)
    assert res.approved is True
    assert res.authorized_amount == 49.99
    assert round(res.monthly_cap_remaining, 2) == 10.01
    assert len(res.mandate_proof_hash) == 64


@pytest.mark.asyncio
async def test_external_buyer_agent_negotiates_under_budget():
    """Headless buyer harness autonomously negotiates from $79.99 down to $49.99 when cap is $60.00."""
    agent = ExternalBuyerAgent(
        transport="stdio",
        contractor_name="Demo Autonomous Buyer",
        business_entity="Demo Buyer Corp",
        contractor_email="agent-alpha@example.com",
        trade_id="ap2-gateway",
        budget_cap=60.00,
        verbose=False,
        reset_ledger=True,
    )
    result = await agent.execute_autonomous_procurement()
    assert result["status"] == "COMPLETED"
    assert result["monthly_amount"] == 49.99
    assert "High-Throughput Batch Worker" in result["selected_tier"]
    assert len(result["mandate_proof_hash"]) == 64
    assert result["assigned_did"].startswith("mcp+https://")
