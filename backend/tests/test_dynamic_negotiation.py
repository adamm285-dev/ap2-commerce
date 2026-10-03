"""
Tests for Dynamic Tier Negotiation and Nationwide LATA Failover Routing.
"""

import pytest
from backend.models import SpendingMandateRequest, RecurrenceType
from backend.services.mandate_evaluator import evaluate_spending_mandate, ledger
from backend.services.telecom_router import allocate_dynamic_did
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
        category="contractor-dispatch-ai",
        monthlyBudgetCap=60.00,
    )
    res = evaluate_spending_mandate(req)
    assert res.approved is False
    assert res.counter_offer_available is True
    assert res.counter_offer_amount == 49.99
    assert res.counter_offer_tier == "Solo Starter"
    assert "Counter-offer available" in res.reason


def test_buyer_accepts_and_binds_counter_offer():
    """Submitting the negotiated counter-offer rate ($49.99) within budget cap ($60.00) is approved."""
    req = SpendingMandateRequest(
        buyerAgentId="buyer-budget-constrained",
        amount=49.99,
        recurrence=RecurrenceType.MONTHLY,
        category="contractor-dispatch-ai",
        monthlyBudgetCap=60.00,
    )
    res = evaluate_spending_mandate(req)
    assert res.approved is True
    assert res.authorized_amount == 49.99
    assert round(res.monthly_cap_remaining, 2) == 10.01
    assert len(res.mandate_proof_hash) == 64


def test_nationwide_lata_allocation_and_failover():
    """Verify nationwide DID allocation and automated LATA failover when exchange is exhausted."""
    # Standard allocation
    alloc_normal = allocate_dynamic_did(preferred_area_code="863", simulate_exhaustion=False)
    assert alloc_normal["area_code"] == "863"
    assert alloc_normal["failover_triggered"] is False
    assert "+1863" in alloc_normal["did"]

    # Simulated exhaustion triggering failover to contiguous LATA exchange 813 (Tampa)
    alloc_failover = allocate_dynamic_did(preferred_area_code="863", simulate_exhaustion=True)
    assert alloc_failover["area_code"] == "813"
    assert alloc_failover["failover_triggered"] is True
    assert "+1813" in alloc_failover["did"]
    assert "Tampa" in alloc_failover["region"]

    # Nationwide: Texas (Dallas 214), California (San Francisco 415), New York (Manhattan 212)
    alloc_tx = allocate_dynamic_did(preferred_area_code="214")
    assert alloc_tx["area_code"] == "214"
    assert "+1214" in alloc_tx["did"]

    alloc_ca = allocate_dynamic_did(preferred_area_code="415")
    assert alloc_ca["area_code"] == "415"
    assert "+1415" in alloc_ca["did"]

    alloc_ny = allocate_dynamic_did(preferred_area_code="212")
    assert alloc_ny["area_code"] == "212"
    assert "+1212" in alloc_ny["did"]


@pytest.mark.asyncio
async def test_external_buyer_agent_negotiates_under_budget():
    """Headless buyer harness autonomously negotiates from $79.99 down to $49.99 when cap is $60.00."""
    agent = ExternalBuyerAgent(
        transport="stdio",
        contractor_name="Dave Miller",
        business_entity="Miller Custom Flooring LLC",
        contractor_email="dave@millercustomfloors.com",
        trade_id="flooring-tile",
        budget_cap=60.00,
        area_code="863",
        verbose=False,
        reset_ledger=True,
    )
    result = await agent.execute_autonomous_procurement()
    assert result["status"] == "COMPLETED"
    assert result["monthly_amount"] == 49.99
    assert "Solo Starter" in result["selected_tier"]
    assert len(result["mandate_proof_hash"]) == 64
    assert result["assigned_did"].startswith("+1")
