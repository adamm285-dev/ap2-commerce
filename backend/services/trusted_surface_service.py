"""
AP2 v0.2 Trusted Surface Service.
Implements the human authorization boundary (non-agentic UI & endpoint)
that mints root Open Checkout and Open Payment mandates conforming to
Google's AP2 reference SDK.

Non-agentic invariants:
1. The human user / Trusted Surface holds the owner P-256 private key.
2. The AI Buyer Agent NEVER holds or sees the owner private key.
3. Open mandates carry strict constraints:
   - AmountRange: monthly spending cap in integer minor units (cents)
   - AgentRecurrence: MONTHLY frequency with max_occurrences = 12
   - Budget: total spending ceiling over the billing term (cents-derived)
   - AllowedMerchants / AllowedPayees: AP2_MERCHANT_ID
   - LineItems: allowed compute tiers (acceptable_items)
   - cnf: confirmation claim binding the agent's public key JWK
   - Expiration: the open checkout mandate (authority to start a purchase) is short-lived;
     the open payment mandate (authority for recurring charges) lasts the billing term,
     long enough to cover every authorized monthly charge.
"""

from __future__ import annotations

import datetime
import json
import logging
import time
from typing import Any, Dict, List, Optional

from jwcrypto.jwk import JWK

from ap2.sdk.generated.open_checkout_mandate import (
    AllowedMerchants,
    Item as CheckoutItem,
    LineItemRequirements,
    LineItems,
    OpenCheckoutMandate,
)
from ap2.sdk.generated.open_payment_mandate import (
    AgentRecurrence,
    AllowedPayees,
    AmountRange,
    Budget,
    Frequency,
    OpenPaymentMandate,
)
from ap2.sdk.generated.types.merchant import Merchant
from ap2.sdk.mandate import MandateClient

from ..database import register_buyer_key
from ..services.mandate_evaluator import ledger
from .ap2_keys import (
    get_demo_agent_key,
    get_demo_user_key,
    jwk_to_cnf,
)
from .ap2_service import (
    AP2_MERCHANT_ID,
    AP2_MERCHANT_NAME,
    dollars_to_minor_units,
)
from .plan_catalog import resolve_plan

logger = logging.getLogger("trusted_surface_service")

# Recurring billing term: the open payment mandate must outlive every authorized monthly charge
MAX_MONTHLY_OCCURRENCES = 12
BILLING_CYCLE_SECONDS = 31 * 86400  # longest calendar month
DEFAULT_BILLING_TERM_SECONDS = MAX_MONTHLY_OCCURRENCES * BILLING_CYCLE_SECONDS


def create_trusted_surface_open_mandates(
    buyer_email: str,
    monthly_budget_cap: float,
    yearly_budget_ceiling: Optional[float] = None,
    allowed_tiers: Optional[List[str]] = None,
    agent_key: Optional[JWK] = None,
    user_key: Optional[JWK] = None,
    validity_seconds: int = 86400,  # 24 hours: window to start a purchase
    billing_term_seconds: Optional[int] = None,  # default: 12 monthly charges
) -> Dict[str, Any]:
    """
    Creates ES256 SD-JWT Open Checkout and Open Payment mandates signed by the human owner.
    Enforces all 7 constraints mandated by AP2 v0.2.
    The checkout mandate expires after `validity_seconds`; the payment mandate expires after
    `billing_term_seconds` so renewals stay authorized for the whole subscription term.
    """
    norm_email = buyer_email.strip().lower()
    if not norm_email or "@" not in norm_email:
        raise ValueError("A valid buyer email is required for the Trusted Surface mandate.")

    # MOCK(M-005): falls back to server-held demo owner and agent keys
    # Default to demo keys if not explicitly supplied (mock/test environments)
    actual_user_key = user_key or get_demo_user_key()
    actual_agent_key = agent_key or get_demo_agent_key()

    agent_cnf = jwk_to_cnf(actual_agent_key)
    mandate_client = MandateClient()

    term_seconds = DEFAULT_BILLING_TERM_SECONDS if billing_term_seconds is None else billing_term_seconds
    if isinstance(term_seconds, bool) or not isinstance(term_seconds, int) or term_seconds <= 0:
        raise ValueError("billing_term_seconds must be a positive integer number of seconds.")

    now_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    exp_ts = now_ts + validity_seconds
    billing_exp_ts = now_ts + term_seconds

    # 1. Open Checkout Mandate Constraints
    tiers = allowed_tiers or ["ap2-batch", "ap2-gateway", "ap2-cluster"]
    acceptable_items = []
    for tid in tiers:
        clean_tid = tid.strip().lower()
        pinfo = resolve_plan(clean_tid) or {}
        title = pinfo.get("title", f"AP2 Compute Tier ({clean_tid})")
        acceptable_items.append(CheckoutItem(id=clean_tid, title=title))

    chk_constraints = [
        AllowedMerchants(
            allowed=[Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME)]
        ),
        LineItems(
            items=[
                LineItemRequirements(
                    id="allowed_compute_tiers",
                    acceptable_items=acceptable_items,
                    quantity=1,
                )
            ]
        ),
    ]

    open_chk = OpenCheckoutMandate(
        vct="mandate.checkout.open.1",
        constraints=chk_constraints,
        cnf=agent_cnf,
        iat=now_ts,
        exp=exp_ts,
    )

    open_checkout_mandate_token = mandate_client.create(
        issuer_key=actual_user_key,
        payloads=[open_chk],
    )

    # 2. Open Payment Mandate Constraints
    monthly_cap_cents = dollars_to_minor_units(monthly_budget_cap)
    if yearly_budget_ceiling is not None:
        yearly_ceiling_cents = dollars_to_minor_units(yearly_budget_ceiling)
    else:
        yearly_ceiling_cents = monthly_cap_cents * 12

    # Compute ceiling in dollars ensuring int(ceiling_dollars * 100) exactly matches integer cents
    yearly_ceiling_dollars = yearly_ceiling_cents / 100.0
    if int(yearly_ceiling_dollars * 100) < yearly_ceiling_cents:
        yearly_ceiling_dollars = (yearly_ceiling_cents + 1e-6) / 100.0
    assert int(yearly_ceiling_dollars * 100) == yearly_ceiling_cents, (
        f"Budget ceiling float precision mismatch: {int(yearly_ceiling_dollars * 100)} != {yearly_ceiling_cents}"
    )

    pay_constraints = [
        AmountRange(currency="USD", min=1, max=monthly_cap_cents),
        AgentRecurrence(frequency=Frequency.MONTHLY, max_occurrences=MAX_MONTHLY_OCCURRENCES),
        Budget(currency="USD", max=yearly_ceiling_dollars),
        AllowedPayees(
            allowed=[Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME)]
        ),
    ]

    open_pay = OpenPaymentMandate(
        vct="mandate.payment.open.1",
        constraints=pay_constraints,
        cnf=agent_cnf,
        iat=now_ts,
        exp=billing_exp_ts,
    )

    open_payment_mandate_token = mandate_client.create(
        issuer_key=actual_user_key,
        payloads=[open_pay],
    )

    owner_kid = getattr(actual_user_key, "kid", None) or "owner-trusted-surface"
    agent_kid = getattr(actual_agent_key, "kid", None) or "buyer-agent"

    summary = {
        "buyer_email": norm_email,
        "monthly_budget_cap_usd": round(monthly_budget_cap, 2),
        "monthly_budget_cap_cents": monthly_cap_cents,
        "yearly_budget_ceiling_usd": round(yearly_ceiling_dollars, 2),
        "yearly_budget_ceiling_cents": yearly_ceiling_cents,
        "recurrence": "MONTHLY",
        "max_occurrences": MAX_MONTHLY_OCCURRENCES,
        "allowed_payee": AP2_MERCHANT_ID,
        "allowed_merchant": AP2_MERCHANT_ID,
        "allowed_tiers": tiers,
        "owner_kid": owner_kid,
        "agent_kid": agent_kid,
        "iat": now_ts,
        "exp": exp_ts,
        "validity_seconds": validity_seconds,
        "billing_term_exp": billing_exp_ts,
        "billing_term_seconds": term_seconds,
    }

    return {
        "status": "AUTHORIZED",
        "open_checkout_mandate_token": open_checkout_mandate_token,
        "open_payment_mandate_token": open_payment_mandate_token,
        "owner_kid": owner_kid,
        "agent_kid": agent_kid,
        "constraints": summary,
        "signed_at": datetime.datetime.fromtimestamp(now_ts, tz=datetime.timezone.utc).isoformat(),
        "expires_at": datetime.datetime.fromtimestamp(exp_ts, tz=datetime.timezone.utc).isoformat(),
        "billing_term_expires_at": datetime.datetime.fromtimestamp(billing_exp_ts, tz=datetime.timezone.utc).isoformat(),
    }


def enroll_trusted_surface_key(
    kid: str,
    public_key_jwk: Dict[str, Any],
    buyer_email: str,
    business_name: str = "Demo Buyer Corp",
    monthly_budget_cap: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Enrolls a human owner's public key (JWK) into the buyer key registry,
    binding it to buyer_email for AP2 root key resolution.
    """
    norm_email = buyer_email.strip().lower()
    clean_kid = kid.strip()
    jwk_str = json.dumps(public_key_jwk)

    register_buyer_key(
        kid=clean_kid,
        public_key_hex=jwk_str,
        contractor_email=norm_email,
        business_name=business_name,
    )

    return {
        "status": "REGISTERED",
        "kid": clean_kid,
        "buyer_email": norm_email,
        "business_name": business_name,
        "registered_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
