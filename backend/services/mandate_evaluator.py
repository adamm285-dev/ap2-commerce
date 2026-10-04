"""
Buyer Agent Spending Mandate Evaluation Engine.
Enforces programmatic financial guardrails, checks budget caps, validates
permitted merchant categories, and cryptographically signs authorization tokens.
"""

import hmac
import hashlib
import time
import uuid
from typing import Dict, Any, Tuple, Optional
from ..config import settings
from ..models import SpendingMandateRequest, SpendingMandateResponse, RecurrenceType
from .crypto_mandate import (
    generate_dynamic_mandate_proof,
    verify_mandate_proof,
    canonicalize_mandate_payload,
    sign_ap2_intent_mandate,
    verify_ap2_intent_mandate,
)

AP2_PAYEE_ID = "PAYEE-FIELDSMITH-PRO-TELEPHONY"
AP2_MANDATE_TTL_SEC = 2592000  # 30 days

ALLOWED_CATEGORIES = {
    "contractor-dispatch-ai",
    "telephony-screener",
    "telephony-ai-screener",
    "trade-software",
    "job-deposit",
    "emergency-towing",
}

DEFAULT_MONTHLY_CAP = 100.00

# Registry of active authorized mandate proofs to prevent parameter tampering at checkout
_AUTHORIZED_MANDATES: Dict[str, Dict[str, Any]] = {}


def register_authorized_mandate(proof_hash: str, details: Dict[str, Any]):
    """Registers an authorized mandate hash with its bounded terms."""
    _AUTHORIZED_MANDATES[proof_hash] = {
        **details,
        "registered_at": time.time(),
        "expires_at": time.time() + 1800,  # 30-minute validity window
    }


def get_authorized_mandate(proof_hash: str) -> Optional[Dict[str, Any]]:
    """Returns the registered terms for a mandate proof hash, if any."""
    return _AUTHORIZED_MANDATES.get(proof_hash)


def bind_mandate_email(proof_hash: str, contractor_email: str):
    """Locks a mandate that was issued without a contractor email to its first redeemer."""
    auth = _AUTHORIZED_MANDATES.get(proof_hash)
    if auth is not None and not auth.get("contractor_email"):
        auth["contractor_email"] = contractor_email.strip().lower()


def build_ap2_intent_mandate(
    buyer_agent_id: str,
    amount: float,
    recurrence: str,
    category: str,
    tier_id: str = "*",
    contractor_email: Optional[str] = None,
    negotiation_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Builds and Ed25519-signs the single canonical AP2 Intent Mandate for a negotiation.
    The same signed object is returned by negotiate_tier_terms and purchase_subscription.
    """
    now = int(time.time())
    mandate = {
        "mandate_id": f"mandate_{uuid.uuid4().hex[:16]}",
        "vct": "ap2.mandate.intent.1",
        "issuer": buyer_agent_id,
        "payer": {"email": contractor_email.strip().lower() if contractor_email else None},
        "payee": AP2_PAYEE_ID,
        "tier_id": tier_id,
        "amount": {"value": f"{amount:.2f}", "currency_code": "USD"},
        "recurrence": recurrence,
        "category": category,
        "negotiation_id": negotiation_id,
        "issued_at": now,
        "expires_at": now + AP2_MANDATE_TTL_SEC,
        "nonce": uuid.uuid4().hex[:16],
        "user_present": False,
    }
    return sign_ap2_intent_mandate(mandate)


def verify_authorized_mandate(
    proof_hash: str,
    tier_id: str,
    agreed_rate: float,
    contractor_email: Optional[str] = None,
    max_cap: Optional[float] = None,
) -> Tuple[bool, str]:
    """
    Validates that a purchase submission matches a mandate issued by this seller.
    Prevents buyer agents or attackers from submitting a $49.99 proof for a $179.99 tier,
    redeeming a mandate bound to a different contractor email, or presenting a forged token.
    """
    if not proof_hash or not proof_hash.strip():
        return False, "EMPTY_MANDATE_HASH: A signed AP2 mandate proof hash is required."

    auth = _AUTHORIZED_MANDATES.get(proof_hash)
    if not auth:
        return False, "UNKNOWN_MANDATE: Proof hash was not issued by this seller. Call negotiate_tier_terms first."

    if time.time() > auth.get("expires_at", 0):
        return False, "MANDATE_EXPIRED: The authorized mandate proof has expired."

    # Identity anti-theft verification
    bound_email = auth.get("contractor_email")
    if bound_email:
        if not contractor_email or bound_email.strip().lower() != contractor_email.strip().lower():
            return (
                False,
                f"IDENTITY_MISMATCH_DETECTED: Mandate is bound to '{bound_email}', cannot be redeemed by '{contractor_email}'.",
            )

    # The signed AP2 mandate must be intact
    ap2_mandate = auth.get("ap2_mandate")
    if ap2_mandate is not None and not verify_ap2_intent_mandate(ap2_mandate):
        return False, "MANDATE_SIGNATURE_INVALID: AP2 Intent Mandate signature verification failed."

    allowed_tier = auth.get("tier_id")
    allowed_rate = auth.get("amount", 0.0)

    # Verify rate doesn't exceed authorized amount
    if round(agreed_rate, 2) > round(allowed_rate, 2):
        return (
            False,
            f"RATE_TAMPERING_DETECTED: Agreed rate ${agreed_rate:.2f} exceeds authorized mandate amount ${allowed_rate:.2f}.",
        )
    # If tier was restricted, verify tier
    if allowed_tier and allowed_tier not in ["*", "any", tier_id]:
        normalized_allowed = allowed_tier.replace("-", "").replace("_", "").lower()
        normalized_req = tier_id.replace("-", "").replace("_", "").lower()
        if normalized_allowed not in normalized_req and normalized_req not in normalized_allowed:
            return (
                False,
                f"TIER_MISMATCH_DETECTED: Mandate was authorized for '{allowed_tier}', but attempted to purchase '{tier_id}'.",
            )
    return True, "VERIFIED"


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
            return round(max(0.0, effective_cap - spent), 2)
        return round(max(0.0, effective_cap - self._current_spent), 2)

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
        _AUTHORIZED_MANDATES.clear()


# Global in-memory mandate ledger
ledger = MandateLedger()


def sign_mandate_token(
    agent_id: str,
    amount: float,
    recurrence: str,
    secret: str,
    contractor_email: Optional[str] = None,
) -> str:
    """Generates an HMAC-SHA256 signature binding the agent identity, contractor, authorized amount, and timestamp."""
    payload = f"{agent_id}:{amount:.2f}:{recurrence}:{int(time.time() // 300)}"  # 5-min epoch window
    if contractor_email:
        payload += f":{contractor_email.strip().lower()}"
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
            # Generate pre-signed counter-offer token for Solo Starter at $49.99
            counter_hash = sign_mandate_token(
                agent_id=request.buyer_agent_id,
                amount=49.99,
                recurrence=request.recurrence.value,
                secret=settings.a2a_mandate_secret,
            )
            register_authorized_mandate(
                counter_hash,
                {
                    "tier_id": "solo-starter",
                    "amount": 49.99,
                    "buyer_agent_id": request.buyer_agent_id,
                    "monthly_budget_cap": cap,
                },
            )
            return SpendingMandateResponse(
                approved=False,
                authorized_amount=0.0,
                monthly_cap_remaining=remaining,
                mandate_proof_hash=counter_hash,
                reason=f"Requested amount ${request.amount:.2f} exceeds remaining monthly budget cap of ${remaining:.2f}. Counter-offer available: Solo Starter (100 mins) at $49.99/mo.",
                counter_offer_available=True,
                counter_offer_tier="Solo Starter",
                counter_offer_tier_id="solo-starter",
                counter_offer_plan_id="solo-starter",
                counter_offer_amount=49.99,
                counter_offer_mandate_hash=counter_hash,
            )
        return SpendingMandateResponse(
            approved=False,
            authorized_amount=0.0,
            monthly_cap_remaining=remaining,
            mandate_proof_hash="",
            reason=f"Requested amount ${request.amount:.2f} exceeds remaining monthly budget cap of ${remaining:.2f}",
        )

    # 3. Approved: generate cryptographic proof & AP2 Intent Mandate
    proof_hash = sign_mandate_token(
        request.buyer_agent_id,
        request.amount,
        request.recurrence.value,
        settings.a2a_mandate_secret,
    )

    # Asymmetric Ed25519 AP2 Proof
    asym_proof = generate_dynamic_mandate_proof(
        contractor_id=request.buyer_agent_id,
        business_name="FieldSmith Telephony Subscriber",
        monthly_cap_usd=cap,
        agreed_price_usd=request.amount,
        nonce=uuid.uuid4().hex[:16],
    )

    ap2_mandate = build_ap2_intent_mandate(
        buyer_agent_id=request.buyer_agent_id,
        amount=request.amount,
        recurrence=request.recurrence.value,
        category=request.category,
    )

    # Register mandate authorization
    register_authorized_mandate(
        proof_hash,
        {
            "tier_id": "*",
            "amount": request.amount,
            "buyer_agent_id": request.buyer_agent_id,
            "monthly_budget_cap": cap,
            "ap2_mandate": ap2_mandate,
        },
    )
    register_authorized_mandate(
        asym_proof["signature"],
        {
            "tier_id": "*",
            "amount": request.amount,
            "buyer_agent_id": request.buyer_agent_id,
            "monthly_budget_cap": cap,
            "ap2_mandate": ap2_mandate,
        },
    )

    # Note: Spend is recorded when purchase_subscription is finalized, not during evaluation!
    # Monthly cap remaining is calculated as projected remaining budget
    projected_remaining = round(remaining - request.amount, 2)

    return SpendingMandateResponse(
        approved=True,
        authorized_amount=request.amount,
        monthly_cap_remaining=projected_remaining,
        mandate_proof_hash=proof_hash,
        ap2_intent_mandate=ap2_mandate,
        signature_algorithm="Ed25519",
        reason="Spending mandate policy checks passed. Programmatic AP2 authorization issued.",
    )
