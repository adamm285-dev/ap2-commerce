"""
Unit tests for the Buyer Agent Spending Mandate Evaluator.
Verifies category whitelists, budget ceilings, cryptographic HMAC signatures, and tamper detection.
"""

import pytest
from ..models import SpendingMandateRequest, RecurrenceType
from ..services.mandate_evaluator import (
    evaluate_spending_mandate,
    sign_mandate_token,
    verify_mandate_token,
    ledger,
)
from ..config import settings


@pytest.fixture(autouse=True)
def reset_ledger():
    ledger.reset()


def test_mandate_rejects_unauthorized_category():
    req = SpendingMandateRequest(
        buyerAgentId="agent-01",
        amount=50.00,
        recurrence=RecurrenceType.MONTHLY,
        category="gambling-or-crypto",
        monthlyBudgetCap=100.00,
    )
    res = evaluate_spending_mandate(req)
    assert res.approved is False
    assert res.authorized_amount == 0.0
    assert "is not approved for this seller" in res.reason


def test_mandate_approves_autonomous_node_service_gateway():
    """Verify autonomous-node-service category with $100 cap and $79.99 Gateway is approved."""
    req = SpendingMandateRequest(
        buyerAgentId="agent-ap2-buyer",
        amount=79.99,
        recurrence=RecurrenceType.MONTHLY,
        category="autonomous-node-service",
        monthlyBudgetCap=100.00,
    )
    res = evaluate_spending_mandate(req)
    assert res.approved is True
    assert res.authorized_amount == 79.99
    assert round(res.monthly_cap_remaining, 2) == 20.01
    assert len(res.mandate_proof_hash) == 64


def test_mandate_rejects_exceeded_budget():
    req = SpendingMandateRequest(
        buyerAgentId="agent-01",
        amount=150.00,
        recurrence=RecurrenceType.MONTHLY,
        category="contractor-dispatch-ai",
        monthlyBudgetCap=100.00,
    )
    res = evaluate_spending_mandate(req)
    assert res.approved is False
    assert res.authorized_amount == 0.0
    assert "exceeds remaining monthly budget cap" in res.reason


def test_mandate_approves_within_budget_and_signs_proof():
    req = SpendingMandateRequest(
        buyerAgentId="agent-solo-contractor",
        amount=79.99,
        recurrence=RecurrenceType.MONTHLY,
        category="contractor-dispatch-ai",
        monthlyBudgetCap=100.00,
    )
    res = evaluate_spending_mandate(req)
    assert res.approved is True
    assert res.authorized_amount == 79.99
    assert round(res.monthly_cap_remaining, 2) == 20.01
    assert len(res.mandate_proof_hash) == 64  # SHA-256 hex string

    # Verify signature
    is_valid = verify_mandate_token(
        agent_id="agent-solo-contractor",
        amount=79.99,
        recurrence="monthly",
        token=res.mandate_proof_hash,
        secret=settings.a2a_mandate_secret,
    )
    assert is_valid is True


def test_mandate_detects_tampered_amount():
    token = sign_mandate_token(
        agent_id="agent-solo",
        amount=79.99,
        recurrence="monthly",
        secret=settings.a2a_mandate_secret,
    )
    # Attempting to verify token against an altered amount of $179.99 must fail
    is_valid = verify_mandate_token(
        agent_id="agent-solo",
        amount=179.99,
        recurrence="monthly",
        token=token,
        secret=settings.a2a_mandate_secret,
    )
    assert is_valid is False


def test_mandate_counter_offer_exposes_real_plan_id():
    """Verify counter-offer returns configured solo plan ID, not raw string."""
    req = SpendingMandateRequest(
        buyerAgentId="agent-counter-test",
        amount=79.99,
        recurrence=RecurrenceType.MONTHLY,
        category="autonomous-node-service",
        monthlyBudgetCap=60.00,
    )
    res = evaluate_spending_mandate(req)
    assert res.approved is False
    assert res.counter_offer_available is True
    assert res.counter_offer_amount == 49.99
    assert res.counter_offer_plan_id == settings.paypal_plan_id_solo
    assert res.plan_id == settings.paypal_plan_id_solo
    assert res.tier_id == "solo-starter"


def test_mandate_approved_exposes_tier_and_plan_id():
    """Verify approved mandates expose correct tier_id and plan_id."""
    req_gateway = SpendingMandateRequest(
        buyerAgentId="agent-gw-test",
        amount=79.99,
        recurrence=RecurrenceType.MONTHLY,
        category="autonomous-node-service",
        monthlyBudgetCap=100.00,
    )
    res_gw = evaluate_spending_mandate(req_gateway)
    assert res_gw.approved is True
    assert res_gw.plan_id == settings.paypal_plan_id_pro
    assert res_gw.tier_id == "fieldsmith-pro"

    req_cluster = SpendingMandateRequest(
        buyerAgentId="agent-cl-test",
        amount=179.99,
        recurrence=RecurrenceType.MONTHLY,
        category="autonomous-node-service",
        monthlyBudgetCap=200.00,
    )
    res_cl = evaluate_spending_mandate(req_cluster)
    assert res_cl.approved is True
    assert res_cl.plan_id == settings.paypal_plan_id_dispatch
    assert res_cl.tier_id == "pro-dispatch"


def test_every_evaluator_tier_id_exists_in_plan_catalog_plans():
    """Verify every tier_id that evaluate_spending_mandate can return exists in plan_catalog.PLANS."""
    from ..services.plan_catalog import PLANS

    valid_tier_ids = {p["tier_id"] for p in PLANS}

    # Test all approval tiers
    for amount in [49.99, 79.99, 179.99]:
        req = SpendingMandateRequest(
            buyerAgentId="agent-catalog-check",
            amount=amount,
            recurrence=RecurrenceType.MONTHLY,
            category="autonomous-node-service",
            monthlyBudgetCap=250.00,
        )
        res = evaluate_spending_mandate(req)
        assert res.approved is True
        assert res.tier_id in valid_tier_ids, f"Tier ID '{res.tier_id}' for ${amount} not found in PLANS"

    # Test counter-offer tier
    req_counter = SpendingMandateRequest(
        buyerAgentId="agent-counter-check",
        amount=79.99,
        recurrence=RecurrenceType.MONTHLY,
        category="autonomous-node-service",
        monthlyBudgetCap=60.00,
    )
    res_counter = evaluate_spending_mandate(req_counter)
    assert res_counter.counter_offer_available is True
    assert res_counter.tier_id in valid_tier_ids, f"Counter-offer tier ID '{res_counter.tier_id}' not found in PLANS"
    assert res_counter.counter_offer_tier_id in valid_tier_ids

