"""
Plan Catalog Drift Tests.
Every agent-facing plan surface must agree on price and workload quota:
the seller MCP tools and instructions, the A2A agent card, and counter-offer text.
"""

import json
import re
import pytest
from fastapi.testclient import TestClient

from backend.server import app
from backend.mcp_server import process_mcp_request
from backend.agents.seller_agent import seller_agent
from backend.models import SpendingMandateRequest, RecurrenceType
from backend.services.mandate_evaluator import evaluate_spending_mandate, ledger
from backend.services.plan_catalog import PLANS, get_plan, plan_summary, quota_label

client = TestClient(app)

CATALOG = {p["website_plan_name"]: (p["monthly_price"], p["workload_tasks_per_month"]) for p in PLANS}


@pytest.fixture(autouse=True)
def reset_ledger():
    from backend.agents.seller_agent import _COMPLETED_SUBSCRIPTIONS, _ACTIVE_CONTRACTOR_SUBSCRIPTIONS
    ledger.reset()
    _COMPLETED_SUBSCRIPTIONS.clear()
    _ACTIVE_CONTRACTOR_SUBSCRIPTIONS.clear()
    yield
    ledger.reset()
    _COMPLETED_SUBSCRIPTIONS.clear()
    _ACTIVE_CONTRACTOR_SUBSCRIPTIONS.clear()


@pytest.mark.asyncio
async def test_seller_surfaces_share_catalog():
    expected = [(p["tier_id"], p["monthly_price"], p["workload_tasks_per_month"]) for p in PLANS]

    tiers = await seller_agent.inspect_subscription_tiers()
    assert [(p["tier_id"], p["monthly_price"], p["workload_tasks_per_month"]) for p in tiers["subscription_plans"]] == expected

    catalog = await seller_agent.get_service_catalog()
    assert [(p["tier_id"], p["monthly_price"], p["workload_tasks_per_month"]) for p in catalog["plans"]] == expected

    init = await process_mcp_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    instructions = init["result"]["instructions"]
    for plan in PLANS:
        assert plan_summary(plan["tier_id"]) in instructions

    card = client.get("/.well-known/agent.json").json()
    assert [(p["tier_id"], p["monthly_price"], p["workload_tasks_per_month"]) for p in card["plans"]] == expected


@pytest.mark.asyncio
async def test_negotiation_quotes_catalog_quota():
    approved = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="catalog-drift-buyer",
        tier_id="ap2-gateway",
        monthly_budget_cap=200.00,
        contractor_email="drift-approved@example.com",
    )
    assert approved["status"] == "APPROVED"
    assert approved["workload_tasks_per_month"] == get_plan("ap2-gateway")["workload_tasks_per_month"]

    counter = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="catalog-drift-buyer-2",
        tier_id="ap2-gateway",
        monthly_budget_cap=60.00,
        contractor_email="drift-counter@example.com",
    )
    batch = get_plan("ap2-batch")
    assert counter["status"] == "COUNTER_OFFER"
    assert counter["counter_offer_amount"] == batch["monthly_price"]
    assert plan_summary("ap2-batch") in counter["reason"]

    evaluated = evaluate_spending_mandate(
        SpendingMandateRequest(
            buyerAgentId="catalog-drift-buyer-3",
            amount=79.99,
            recurrence=RecurrenceType.MONTHLY,
            category="COMPUTE_NODE_SERVICE",
            monthlyBudgetCap=60.00,
        )
    )
    assert evaluated.counter_offer_amount == batch["monthly_price"]
    assert quota_label("ap2-batch") in evaluated.reason
