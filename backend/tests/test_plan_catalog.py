"""
Plan Catalog Drift Tests.
Every agent-facing plan surface must agree on price and screened-call quota:
the seller MCP tools and instructions, the A2A agent card, counter-offer text,
and the published llms.txt, llms-full.txt, and Stripe product feed.
"""

import csv
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.server import app
from backend.mcp_server import process_mcp_request
from backend.agents.seller_agent import seller_agent
from backend.models import SpendingMandateRequest, RecurrenceType
from backend.services.mandate_evaluator import evaluate_spending_mandate, ledger
from backend.services.plan_catalog import PLANS, get_plan, plan_summary, quota_label

client = TestClient(app)

CATALOG = {p["website_plan_name"]: (p["monthly_price"], p["screened_calls_per_month"]) for p in PLANS}
MINUTE_QUOTA = re.compile(r"\b\d[\d,]*\s*(?:AI\s+)?(?:screening\s+)?min(?:ute)?s?\b", re.IGNORECASE)
UNLIMITED_CALLS = re.compile(r"unlimited\s+(?:FieldSmith|voice|calls|telephony|intake)", re.IGNORECASE)


def _find_upwards(relative: str):
    for parent in Path(__file__).resolve().parents:
        candidate = parent / relative
        if candidate.exists():
            return candidate
    return None


def _calls(text: str) -> int:
    return int(text.replace(",", ""))


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


def test_catalog_matches_llms_txt():
    path = _find_upwards("fieldsmith_web_deploy/llms.txt")
    if path is None:
        pytest.skip("fieldsmith_web_deploy/llms.txt not present in this checkout")
    published = {
        name: (float(price), _calls(calls))
        for name, price, calls in re.findall(
            r"^- (Solo Operator|Pro|Fleet / Crew): \$([\d.]+)/mo \(([\d,]+) AI Screened Calls/mo",
            path.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
    }
    assert published == CATALOG


def test_catalog_matches_llms_full_txt():
    path = _find_upwards("fieldsmith_web_deploy/llms-full.txt")
    if path is None:
        pytest.skip("fieldsmith_web_deploy/llms-full.txt not present in this checkout")
    published = {
        name: (float(price), _calls(calls))
        for name, price, calls in re.findall(
            r"^- \*\*(Solo Operator|Pro|Fleet / Crew):\*\* \$([\d.]+)/month\s*\n\s*- ([\d,]+) Inbound AI Screened Calls / month",
            path.read_text(encoding="utf-8"),
            re.MULTILINE,
        )
    }
    assert published == CATALOG


def test_stripe_feed_matches_catalog():
    path = _find_upwards("fieldsmith_stripe_product_feed.csv")
    if path is None:
        pytest.skip("fieldsmith_stripe_product_feed.csv not present in this checkout")
    by_price = {price: calls for price, calls in CATALOG.values()}
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    for row in rows:
        assert not UNLIMITED_CALLS.search(row["description"]), row["id"]
        size_match = re.search(r"\(([\d,]+) Calls/mo\)", row["size"])
        if not size_match:
            continue
        price = float(row["price"].split()[0])
        calls = _calls(size_match.group(1))
        assert by_price.get(price) == calls, row["id"]
        assert f"{calls:,} screened calls/month" in row["description"], row["id"]


@pytest.mark.asyncio
async def test_seller_surfaces_share_catalog():
    expected = [(p["tier_id"], p["monthly_price"], p["screened_calls_per_month"]) for p in PLANS]

    tiers = await seller_agent.inspect_subscription_tiers()
    assert [(p["tier_id"], p["monthly_price"], p["screened_calls_per_month"]) for p in tiers["subscription_plans"]] == expected

    catalog = await seller_agent.get_service_catalog()
    assert [(p["tier_id"], p["monthly_price"], p["screened_calls_per_month"]) for p in catalog["plans"]] == expected
    assert all("monthly_price" not in trade for trade in catalog["supported_trades"])

    init = await process_mcp_request({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    instructions = init["result"]["instructions"]
    for plan in PLANS:
        assert plan_summary(plan["tier_id"]) in instructions

    card = client.get("/.well-known/agent.json").json()
    assert [(p["tier_id"], p["monthly_price"], p["screened_calls_per_month"]) for p in card["plans"]] == expected

    for surface in (json.dumps(tiers), json.dumps(catalog), instructions, json.dumps(card["plans"])):
        assert not MINUTE_QUOTA.search(surface)
        assert not UNLIMITED_CALLS.search(surface)


@pytest.mark.asyncio
async def test_negotiation_quotes_catalog_quota():
    approved = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="catalog-drift-buyer",
        tier_id="fieldsmith-pro",
        monthly_budget_cap=200.00,
        contractor_email="drift-approved@example.com",
    )
    assert approved["status"] == "APPROVED"
    assert approved["screened_calls_per_month"] == get_plan("fieldsmith-pro")["screened_calls_per_month"]

    counter = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="catalog-drift-buyer-2",
        tier_id="flooring-tile",
        monthly_budget_cap=60.00,
        contractor_email="drift-counter@example.com",
    )
    solo = get_plan("solo-starter")
    assert counter["status"] == "COUNTER_OFFER"
    assert counter["counter_offer_amount"] == solo["monthly_price"]
    assert plan_summary("solo-starter") in counter["reason"]

    evaluated = evaluate_spending_mandate(
        SpendingMandateRequest(
            buyerAgentId="catalog-drift-buyer-3",
            amount=79.99,
            recurrence=RecurrenceType.MONTHLY,
            category="contractor-dispatch-ai",
            monthlyBudgetCap=60.00,
        )
    )
    assert evaluated.counter_offer_amount == solo["monthly_price"]
    assert quota_label("solo-starter") in evaluated.reason
