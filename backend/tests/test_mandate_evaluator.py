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
    assert "not in approved whitelist" in res.reason


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
