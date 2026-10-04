"""
Buyer Agent Spending Mandate Evaluation Engine.
Enforces programmatic financial guardrails, checks budget caps, validates
permitted merchant categories, and cryptographically signs authorization tokens.
"""

import hmac
import hashlib
import time
import uuid
import datetime
from typing import Dict, Any, Tuple, Optional
from ..config import settings
from ..models import SpendingMandateRequest, SpendingMandateResponse, RecurrenceType
from .crypto_mandate import (
    generate_dynamic_mandate_proof,
    verify_mandate_proof,
    canonicalize_mandate_payload,
    sign_ap2_intent_mandate,
    verify_ap2_intent_mandate,
    sign_ap2_cart_mandate,
    verify_ap2_cart_mandate,
    DEFAULT_SELLER_KID,
    DEFAULT_BUYER_KID,
    is_trusted_buyer_key,
)

AP2_PAYEE_ID = "PAYEE-FIELDSMITH-PRO-TELEPHONY"
AP2_INTENT_MANDATE_TTL_SEC = 31536000  # 1 year (365 days) standing monthly authorization
AP2_CART_OFFER_TTL_SEC = 1800  # 30 minutes merchant price quote validity
AP2_OFFER_TTL_SEC = AP2_CART_OFFER_TTL_SEC
AP2_MANDATE_TTL_SEC = AP2_INTENT_MANDATE_TTL_SEC

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
    now = time.time()
    expires_at = now + AP2_CART_OFFER_TTL_SEC
    expires_at_iso = datetime.datetime.fromtimestamp(int(expires_at), tz=datetime.timezone.utc).isoformat()
    entry = {
        **details,
        "registered_at": now,
        "expires_at": expires_at,
        "offer_expires_at": expires_at_iso,
        "expires_at_iso": expires_at_iso,
    }
    _AUTHORIZED_MANDATES[proof_hash] = entry
    offer_id = details.get("offer_id")
    if offer_id:
        _AUTHORIZED_MANDATES[offer_id] = entry


def get_authorized_mandate(key: str) -> Optional[Dict[str, Any]]:
    """Returns the registered terms for a mandate proof hash or offer_id, if any."""
    return _AUTHORIZED_MANDATES.get(key)


def bind_mandate_email(proof_hash: str, contractor_email: str):
    """Locks a mandate that was issued without a contractor email to its first redeemer."""
    auth = _AUTHORIZED_MANDATES.get(proof_hash)
    if auth is not None and not auth.get("contractor_email"):
        email = contractor_email.strip().lower()
        auth["contractor_email"] = email
        offer_id = auth.get("offer_id")
        if offer_id and offer_id in _AUTHORIZED_MANDATES:
            _AUTHORIZED_MANDATES[offer_id]["contractor_email"] = email


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
    Builds and Ed25519-signs the canonical AP2 Intent Mandate for standing authorization.
    Valid for 1 year (365 days) to authorize recurring monthly subscription charges.
    """
    now = int(time.time())
    issued_at_iso = datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc).isoformat()
    expires_at = now + AP2_INTENT_MANDATE_TTL_SEC
    expires_at_iso = datetime.datetime.fromtimestamp(expires_at, tz=datetime.timezone.utc).isoformat()
    mandate = {
        "mandate_id": f"mandate_{uuid.uuid4().hex[:16]}",
        "vct": "ap2.mandate.intent.1",
        "attestation": "seller_attested",
        "issuer": buyer_agent_id,
        "payer": {"email": contractor_email.strip().lower() if contractor_email else None},
        "payee": AP2_PAYEE_ID,
        "tier_id": tier_id,
        "amount": {"value": f"{amount:.2f}", "currency_code": "USD"},
        "recurrence": recurrence,
        "category": category,
        "negotiation_id": negotiation_id,
        "issued_at": now,
        "issued_at_iso": issued_at_iso,
        "expires_at": expires_at,
        "expires_at_iso": expires_at_iso,
        "validity_period": "P1Y",
        "nonce": uuid.uuid4().hex[:16],
        "user_present": False,
    }
    return sign_ap2_intent_mandate(mandate)


def validate_buyer_intent_mandate(
    mandate: Dict[str, Any],
    contractor_email: Optional[str] = None,
    service_category: str = "TELEPHONY_AI_SCREENER",
) -> Tuple[bool, str, Optional[float]]:
    """
    Cryptographically and policy-wise validates a buyer-signed AP2 Intent Mandate.
    Enforces:
    1. Registered buyer key (kid -> public_key)
    2. Ed25519 signature verification
    3. Expiration check (expires_at)
    4. Permitted spending category
    5. Contractor email identity binding
    Returns (is_valid, error_code, signed_budget_cap).
    """
    if not isinstance(mandate, dict):
        return False, "INVALID_MANDATE_FORMAT", None

    kid = mandate.get("kid")
    pub_hex = mandate.get("public_key")
    if not is_trusted_buyer_key(kid, pub_hex):
        return False, "UNTRUSTED_BUYER_KEY", None

    if not verify_ap2_intent_mandate(mandate):
        return False, "INVALID_BUYER_INTENT_MANDATE", None

    # Expiry verification: expires_at is strictly required
    expires_at = mandate.get("expires_at")
    if expires_at is None:
        return False, "MANDATE_EXPIRED", None
    try:
        if time.time() > float(expires_at):
            return False, "MANDATE_EXPIRED", None
    except (ValueError, TypeError):
        return False, "MANDATE_EXPIRED", None

    # Category verification: category is strictly required
    category = mandate.get("category")
    if not category:
        return False, "UNAUTHORIZED_CATEGORY", None
    norm_cat = str(category).lower().replace("_", "-")
    allowed_norm = {c.lower().replace("_", "-") for c in ALLOWED_CATEGORIES}
    if norm_cat not in allowed_norm and norm_cat != service_category.lower().replace("_", "-"):
        return False, "UNAUTHORIZED_CATEGORY", None

    # Identity verification: payer.email is strictly required
    payer = mandate.get("payer")
    payer_email = payer.get("email") if isinstance(payer, dict) else None
    if not payer_email or not str(payer_email).strip():
        return False, "MISSING_PAYER_EMAIL", None
    payer_email_clean = str(payer_email).strip().lower()
    if "@" not in payer_email_clean:
        return False, "INVALID_PAYER_EMAIL", None

    if contractor_email:
        if payer_email_clean != contractor_email.strip().lower():
            return False, "IDENTITY_MISMATCH_DETECTED", None

    # Extract signed budget cap
    signed_cap = None
    amt = mandate.get("amount")
    if isinstance(amt, dict):
        try:
            signed_cap = float(amt.get("value"))
        except (ValueError, TypeError):
            pass
    elif isinstance(amt, (int, float)):
        signed_cap = float(amt)

    if signed_cap is None:
        for k in ["monthly_cap_usd", "max_amount", "budget_cap", "monthly_budget_cap"]:
            if k in mandate:
                try:
                    signed_cap = float(mandate[k])
                    break
                except (ValueError, TypeError):
                    pass

    return True, "VERIFIED", signed_cap


def build_ap2_cart_mandate(
    offer_id: str,
    tier_id: str,
    amount: float,
    recurrence: str,
    contractor_email: Optional[str] = None,
    negotiation_id: Optional[str] = None,
    category: str = "TELEPHONY_AI_SCREENER",
) -> Dict[str, Any]:
    """
    Builds and Ed25519-signs the merchant AP2 Cart Mandate (vct: ap2.mandate.cart.1).
    Valid for 30 minutes to reserve the merchant price quote for checkout.
    """
    now = int(time.time())
    issued_at_iso = datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc).isoformat()
    expires_at = now + AP2_CART_OFFER_TTL_SEC
    expires_at_iso = datetime.datetime.fromtimestamp(expires_at, tz=datetime.timezone.utc).isoformat()
    cart = {
        "cart_id": f"cart_{uuid.uuid4().hex[:16]}",
        "offer_id": offer_id,
        "vct": "ap2.mandate.cart.1",
        "merchant_id": AP2_PAYEE_ID,
        "payer": {"email": contractor_email.strip().lower() if contractor_email else None},
        "tier_id": tier_id,
        "plan_id": f"P-FLSMITH-{tier_id.upper().replace('-', '_')}",
        "category": category,
        "amount": {"value": f"{amount:.2f}", "currency_code": "USD"},
        "billing_cadence": recurrence,
        "negotiation_id": negotiation_id,
        "issued_at": now,
        "issued_at_iso": issued_at_iso,
        "expires_at": expires_at,
        "expires_at_iso": expires_at_iso,
        "offer_expires_at": expires_at_iso,
        "nonce": uuid.uuid4().hex[:16],
    }
    return sign_ap2_cart_mandate(cart)


def verify_authorized_mandate(
    proof_hash: Optional[str] = None,
    tier_id: Optional[str] = None,
    agreed_rate: Optional[float] = None,
    contractor_email: Optional[str] = None,
    max_cap: Optional[float] = None,
    offer_id: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Validates that a purchase submission matches a mandate or offer issued by this seller.
    Prevents buyer agents or attackers from submitting a $49.99 proof for a $179.99 tier,
    redeeming a mandate bound to a different contractor email, or presenting a forged token.
    Supports lookup via proof_hash or offer_id.
    """
    lookup_key = proof_hash.strip() if proof_hash and proof_hash.strip() else (offer_id.strip() if offer_id and offer_id.strip() else None)
    if not lookup_key:
        return False, "EMPTY_MANDATE_HASH: A signed AP2 mandate proof hash or offer_id is required."

    auth = _AUTHORIZED_MANDATES.get(lookup_key)
    if not auth and offer_id:
        auth = _AUTHORIZED_MANDATES.get(offer_id.strip())
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

    ap2_cart = auth.get("ap2_cart_mandate")
    if ap2_cart is not None and not verify_ap2_cart_mandate(ap2_cart):
        return False, "CART_SIGNATURE_INVALID: AP2 Cart Mandate signature verification failed."

    allowed_tier = auth.get("tier_id")
    allowed_rate = auth.get("amount", 0.0)

    # Verify rate doesn't exceed authorized amount
    effective_rate = agreed_rate if agreed_rate is not None else allowed_rate
    if round(effective_rate, 2) > round(allowed_rate, 2):
        return (
            False,
            f"RATE_TAMPERING_DETECTED: Agreed rate ${effective_rate:.2f} exceeds authorized mandate amount ${allowed_rate:.2f}.",
        )

    # If tier was restricted, verify tier
    effective_tier = tier_id if tier_id is not None else allowed_tier
    if allowed_tier and effective_tier and allowed_tier not in ["*", "any", effective_tier]:
        normalized_allowed = allowed_tier.replace("-", "").replace("_", "").lower()
        normalized_req = effective_tier.replace("-", "").replace("_", "").lower()
        if normalized_allowed not in normalized_req and normalized_req not in normalized_allowed:
            return (
                False,
                f"TIER_MISMATCH_DETECTED: Mandate was authorized for '{allowed_tier}', but attempted to purchase '{effective_tier}'.",
            )
    return True, "VERIFIED"



class MandateLedger:
    """Thread-safe active ledger tracking cumulative monthly agent spend and active contractor commitments."""

    def __init__(self, monthly_cap: float = DEFAULT_MONTHLY_CAP):
        self.monthly_cap = monthly_cap
        self._current_spent = 0.0
        self._agent_spent: Dict[str, float] = {}
        self._contractor_subscriptions: Dict[str, float] = {}
        self._history: list = []

    def get_remaining_budget(
        self, agent_id: str = None, cap: float = None, contractor_email: str = None
    ) -> float:
        effective_cap = cap if cap is not None else self.monthly_cap
        if contractor_email:
            spent = self._contractor_subscriptions.get(contractor_email.strip().lower(), 0.0)
            return round(max(0.0, effective_cap - spent), 2)
        if agent_id:
            spent = self._agent_spent.get(agent_id, 0.0)
            return round(max(0.0, effective_cap - spent), 2)
        return round(max(0.0, effective_cap - self._current_spent), 2)

    def record_spend(self, amount: float, metadata: Dict[str, Any]):
        email = metadata.get("contractor_email")
        if email:
            norm_email = email.strip().lower()
            old_amount = self._contractor_subscriptions.get(norm_email, 0.0)
            self._contractor_subscriptions[norm_email] = amount
            self._current_spent = max(0.0, self._current_spent - old_amount + amount)
            agent_id = metadata.get("agent_id")
            if agent_id:
                old_agent = self._agent_spent.get(agent_id, 0.0)
                self._agent_spent[agent_id] = max(0.0, old_agent - old_amount + amount)
        else:
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
            self._contractor_subscriptions.clear()
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
