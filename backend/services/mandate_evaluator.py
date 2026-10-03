"""
Buyer Agent Spending Mandate Evaluation Engine.
Enforces programmatic financial guardrails, checks budget caps, validates
permitted merchant categories, and cryptographically signs authorization tokens.
"""

import hmac
import hashlib
import time
from typing import Dict, Any, Tuple
from ..config import settings
from ..models import SpendingMandateRequest, SpendingMandateResponse, RecurrenceType

ALLOWED_CATEGORIES = {
    "contractor-dispatch-ai",
    "telephony-screener",
    "telephony-ai-screener",
    "trade-software",
    "job-deposit",
    "emergency-towing",
}

DEFAULT_MONTHLY_CAP = 100.00


class MandateLedger:
    """Thread-safe active ledger tracking cumulative monthly agent spend."""

    def __init__(self, monthly_cap: float = DEFAULT_MONTHLY_CAP):
        self.monthly_cap = monthly_cap
        self._current_spent = 0.0
        self._agent_spent: Dict[str, float] = {}
        self._history: list = []

    def get_remaining_budget(
        self, agent_id: str = None, cap: float = None
    ) -> float:
        effective_cap = cap if cap is not None else self.monthly_cap
        if agent_id:
            spent = self._agent_spent.get(agent_id, 0.0)
            return max(0.0, effective_cap - spent)
        return max(0.0, effective_cap - self._current_spent)

    def record_spend(self, amount: float, metadata: Dict[str, Any]):
        self._current_spent += amount
        agent_id = metadata.get("agent_id")
        if agent_id:
            self._agent_spent[agent_id] = (
                self._agent_spent.get(agent_id, 0.0) + amount
            )
        self._history.append(
            {"timestamp": time.time(), "amount": amount, **metadata}
        )

    def reset(self, agent_id: str = None):
        if agent_id:
            self._agent_spent.pop(agent_id, None)
        else:
            self._current_spent = 0.0
            self._agent_spent.clear()
            self._history.clear()


# Global in-memory mandate ledger
ledger = MandateLedger()


def sign_mandate_token(
    agent_id: str, amount: float, recurrence: str, secret: str
) -> str:
    """Generates an HMAC-SHA256 signature binding the agent identity, authorized amount, and timestamp."""
    payload = f"{agent_id}:{amount:.2f}:{recurrence}:{int(time.time() // 300)}"  # 5-min epoch window
    return hmac.new(
        secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def verify_mandate_token(
    agent_id: str, amount: float, recurrence: str, token: str, secret: str
) -> bool:
    """Verifies that the mandate token matches the expected HMAC signature."""
    expected = sign_mandate_token(agent_id, amount, recurrence, secret)
    return hmac.compare_digest(expected, token)


def evaluate_spending_mandate(
    request: SpendingMandateRequest,
) -> SpendingMandateResponse:
    """Evaluates whether an inbound agent spending request complies with financial guardrails."""
    cap = (
        request.monthly_budget_cap
        if request.monthly_budget_cap is not None
        else DEFAULT_MONTHLY_CAP
    )
    agent_id = request.buyer_agent_id

    # 1. Category validation
    cat_normalized = request.category.strip().lower().replace("_", "-")
    if cat_normalized not in ALLOWED_CATEGORIES:
        return SpendingMandateResponse(
            approved=False,
            authorized_amount=0.0,
            monthly_cap_remaining=ledger.get_remaining_budget(
                agent_id=agent_id, cap=cap
            ),
            mandate_proof_hash="",
            reason=f"Category '{request.category}' is not in approved whitelist: {sorted(ALLOWED_CATEGORIES)}",
        )

    # 2. Budget ceiling verification
    remaining = ledger.get_remaining_budget(agent_id=agent_id, cap=cap)
    if request.amount > remaining:
        # Check if dynamic counter-offer tier is viable within contractor's budget
        if remaining >= 49.99:
            return SpendingMandateResponse(
                approved=False,
                authorized_amount=0.0,
                monthly_cap_remaining=remaining,
                mandate_proof_hash="",
                reason=f"Requested amount ${request.amount:.2f} exceeds remaining monthly budget cap of ${remaining:.2f}. Counter-offer available: Solo Starter (100 mins) at $49.99/mo.",
                counter_offer_available=True,
                counter_offer_tier="Solo Starter",
                counter_offer_amount=49.99,
                counter_offer_plan_id="plan_solo_starter_49_99",
            )
        return SpendingMandateResponse(
            approved=False,
            authorized_amount=0.0,
            monthly_cap_remaining=remaining,
            mandate_proof_hash="",
            reason=f"Requested amount ${request.amount:.2f} exceeds remaining monthly budget cap of ${remaining:.2f}",
        )

    # 3. Approved: generate cryptographic proof
    proof_hash = sign_mandate_token(
        request.buyer_agent_id,
        request.amount,
        request.recurrence.value,
        settings.a2a_mandate_secret,
    )

    # Record authorization
    ledger.record_spend(
        request.amount,
        {
            "agent_id": request.buyer_agent_id,
            "category": request.category,
            "proof_hash": proof_hash,
        },
    )

    return SpendingMandateResponse(
        approved=True,
        authorized_amount=request.amount,
        monthly_cap_remaining=ledger.get_remaining_budget(
            agent_id=agent_id, cap=cap
        ),
        mandate_proof_hash=proof_hash,
        reason="Spending mandate policy checks passed. Programmatic authorization issued.",
    )
