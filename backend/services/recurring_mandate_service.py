"""
Recurring (merchant-initiated) charge verification under AP2 v0.2 open payment mandates.

At purchase, the owner-signed open payment mandate is stored with the subscription
(`register_recurring_mandate`). Each PayPal sale for that subscription (PAYMENT.SALE.COMPLETED)
is then checked against it (`evaluate_sale`) in this order:

  1. Integrity: the stored mandate still hashes to the recorded value and still verifies
     against the owner's key in the registry (bound to the buyer's email).
  2. Expiry: the mandate was still valid when PayPal charged.
  3. Owner constraints, via the vendored AP2 SDK: AmountRange (per-charge cap),
     Budget (cumulative), AgentRecurrence (max payments), AllowedPayees.
  4. Contract: the amount equals the price the agent agreed to.

PayPal reports a sale after the money has moved, so a webhook cannot stop the charge it
reports. Two things limit exposure:
  - After every authorized charge, the next one is checked in advance. If it could not be
    authorized (payments used up, budget too small, mandate expires first), the subscription
    is cancelled right away, so PayPal never makes that charge.
  - A charge that breaks the owner's limits cancels the subscription; a charge that cannot be
    verified suspends it (reversible) for review. Either way the charge is recorded with its
    outcome so the owner can decide on a refund. Refunds are not issued automatically.

The first sale of a subscription is the charge already verified and counted at purchase; it is
bound to that settlement instead of being counted twice.
"""

from __future__ import annotations

import datetime
import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional, Tuple

from ap2.sdk.constraints import MandateContext, check_payment_constraints
from ap2.sdk.generated.open_payment_mandate import AgentRecurrence, Budget, OpenPaymentMandate
from ap2.sdk.generated.payment_mandate import PaymentMandate
from ap2.sdk.generated.types.amount import Amount
from ap2.sdk.generated.types.merchant import Merchant
from ap2.sdk.generated.types.payment_instrument import PaymentInstrument
from ap2.sdk.mandate import SdJwtMandate
from ap2.sdk.sdjwt import common

from ..database import (
    bind_initial_sale,
    get_open_mandate_total_usage,
    get_recurring_charge,
    get_recurring_mandate,
    is_mandate_revoked,
    record_recurring_charge,
    save_recurring_mandate,
)
from .ap2_service import (
    AP2_MERCHANT_ID,
    AP2_MERCHANT_NAME,
    compute_open_payment_mandate_hash,
    create_renewal_receipt_jwt,
    resolve_root_public_key,
)
from .trusted_surface_service import BILLING_CYCLE_SECONDS

logger = logging.getLogger("recurring_mandate_service")

# Outcomes recorded per sale
INITIAL = "INITIAL"                # first charge, already verified and counted at purchase
VERIFIED = "VERIFIED"              # renewal authorized by the owner's mandate
OUT_OF_MANDATE = "OUT_OF_MANDATE"  # breaks the owner's limits -> cancel
UNVERIFIED = "UNVERIFIED"          # cannot be verified -> suspend for review

# Actions the webhook handler must take on PayPal
ACTION_NONE = "NONE"
ACTION_CANCEL = "CANCEL"
ACTION_SUSPEND = "SUSPEND"

# Subscriptions created by the agent purchase path carry this payment method
AGENT_PAYMENT_METHOD = "paypal_vault_mit"


def root_open_mandate_token(payment_mandate_chain: str) -> str:
    """The owner-signed open payment mandate at the root of a presentation chain."""
    token = payment_mandate_chain.strip()
    if "~~" in token:
        token = token.split("~~")[0].strip()
    if not token.endswith("~"):
        token += "~"
    return token


def register_recurring_mandate(
    subscription_id: str,
    payment_mandate_chain: str,
    mandate_hash: str,
    buyer_email: str,
    amount_cents: int,
    currency: str,
) -> bool:
    """Stores the verified owner mandate behind a new agent subscription so renewals can be checked."""
    if not buyer_email or not buyer_email.strip():
        raise ValueError("buyer_email is required to bind a recurring mandate.")
    token = root_open_mandate_token(payment_mandate_chain)
    if compute_open_payment_mandate_hash(token) != mandate_hash:
        raise ValueError("Open payment mandate does not match the verified mandate hash.")
    return save_recurring_mandate(
        subscription_id=subscription_id,
        mandate_hash=mandate_hash,
        open_payment_mandate_token=token,
        buyer_email=buyer_email,
        agreed_amount_cents=amount_cents,
        currency=currency,
    )


def _parse_cents(raw: Any) -> Optional[int]:
    """Parses a PayPal decimal string ('49.99') into exact integer cents; None if not exact."""
    if not isinstance(raw, str):
        return None
    try:
        value = Decimal(raw.strip())
    except InvalidOperation:
        return None
    cents = value * 100
    if not value.is_finite() or cents != cents.to_integral_value() or cents <= 0:
        return None
    return int(cents)


def _parse_time(raw: Any) -> Optional[datetime.datetime]:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = datetime.datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=datetime.timezone.utc)


def _decision(outcome: str, action: str, reason: str, **extra: Any) -> Dict[str, Any]:
    return {"outcome": outcome, "action": action, "reason": reason, **extra}


def _verify_stored_mandate(record: Dict[str, Any]) -> Tuple[Optional[OpenPaymentMandate], Optional[str]]:
    """Re-verifies the stored owner mandate. Returns (mandate, None) or (None, reason)."""
    token = record.get("open_payment_mandate_token") or ""
    if compute_open_payment_mandate_hash(token) != record.get("mandate_hash"):
        return None, "MANDATE_HASH_MISMATCH: stored mandate no longer matches its recorded hash."
    try:
        root_key = resolve_root_public_key(common.parse_token(token), buyer_email=record.get("buyer_email"))
        mandate = SdJwtMandate.from_sd_jwt(token, root_key, OpenPaymentMandate).mandate_payload
    except Exception as e:
        return None, f"MANDATE_SIGNATURE_INVALID: {e}"
    return mandate, None


def _next_charge_blocker(mandate: OpenPaymentMandate, used_cents: int, used_count: int,
                         next_amount_cents: int, charged_at: datetime.datetime) -> Optional[str]:
    """Why the next monthly charge could not be authorized, or None if it could."""
    recurrence = [c for c in mandate.constraints if isinstance(c, AgentRecurrence)]
    if recurrence and recurrence[0].max_occurrences is not None and used_count >= recurrence[0].max_occurrences:
        return f"MANDATE_FULFILLED: all {recurrence[0].max_occurrences} authorized payments have been made."
    budgets = [c for c in mandate.constraints if isinstance(c, Budget)]
    if budgets:
        budget_cents = int(budgets[0].max * 100)  # same conversion as the SDK's BudgetEvaluator
        if used_cents + next_amount_cents > budget_cents:
            return f"MANDATE_FULFILLED: remaining budget ({budget_cents - used_cents} cents) cannot cover the next charge."
    next_charge_ts = charged_at.timestamp() + BILLING_CYCLE_SECONDS
    if not isinstance(mandate.exp, int) or mandate.exp < next_charge_ts:
        return "MANDATE_FULFILLED: the owner's mandate expires before the next billing date."
    return None


def _usage_summary(mandate: OpenPaymentMandate, used_cents: int, used_count: int) -> Dict[str, Any]:
    recurrence = [c for c in mandate.constraints if isinstance(c, AgentRecurrence)]
    budgets = [c for c in mandate.constraints if isinstance(c, Budget)]
    max_count = recurrence[0].max_occurrences if recurrence else None
    budget_cents = int(budgets[0].max * 100) if budgets else None
    return {
        "payments_used": used_count,
        "payments_remaining": None if max_count is None else max(max_count - used_count, 0),
        "budget_used_cents": used_cents,
        "budget_remaining_cents": None if budget_cents is None else max(budget_cents - used_cents, 0),
    }


def evaluate_sale(resource: Any, subscription_record: Optional[Dict[str, Any]],
                  now: Optional[datetime.datetime] = None) -> Dict[str, Any]:
    """
    Checks one PayPal sale against the owner's mandate and records the outcome.
    Returns a decision with `action` NONE, CANCEL or SUSPEND for the caller to carry out.
    Call only after the webhook's transmission signature has been verified.
    """
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if not isinstance(resource, dict):
        return _decision("IGNORED", ACTION_NONE, "MALFORMED_RESOURCE: sale resource is not an object.")
    sale_id = resource.get("id")
    sub_id = resource.get("billing_agreement_id")
    if not isinstance(sale_id, str) or not sale_id.strip():
        return _decision("IGNORED", ACTION_NONE, "MALFORMED_RESOURCE: sale has no id.")
    if not isinstance(sub_id, str) or not sub_id.strip():
        # One-time order captures are not subscription renewals
        return _decision("IGNORED", ACTION_NONE, "NOT_A_SUBSCRIPTION_SALE", sale_id=sale_id)

    existing = get_recurring_charge(sale_id)
    if existing:
        existing_status = existing.get("status") or ""
        extra_already: Dict[str, Any] = {"sale_id": sale_id, "subscription_id": sub_id}
        if existing_status in (INITIAL, VERIFIED):
            rec_existing = get_recurring_mandate(sub_id)
            if rec_existing:
                extra_already["renewal_receipt_jwt"] = create_renewal_receipt_jwt(
                    sale_id=sale_id,
                    subscription_id=sub_id,
                    mandate_hash=existing.get("mandate_hash") or rec_existing["mandate_hash"],
                    buyer_email=rec_existing.get("buyer_email") or "",
                    amount_cents=int(existing.get("amount_cents") or 0),
                    currency=existing.get("currency") or "USD",
                    outcome=existing_status,
                    charged_at=existing.get("charged_at") or now.isoformat(),
                )
        return _decision("ALREADY_PROCESSED", ACTION_NONE, existing_status, **extra_already)

    record = get_recurring_mandate(sub_id)
    if record is None:
        if isinstance(subscription_record, dict) and subscription_record.get("payment_method") == AGENT_PAYMENT_METHOD:
            # Agent-purchased but no mandate on file: nothing authorizes this charge
            return _decision(UNVERIFIED, ACTION_SUSPEND, "NO_MANDATE_ON_FILE: agent subscription has no stored owner mandate.",
                             sale_id=sale_id, subscription_id=sub_id)
        # Human-approved PayPal subscriptions are authorized by PayPal's own approval, not an AP2 mandate
        return _decision("IGNORED", ACTION_NONE, "NOT_AGENT_MANDATED", sale_id=sale_id, subscription_id=sub_id)

    mandate_hash = record["mandate_hash"]
    charged_at = _parse_time(resource.get("create_time")) or now
    charged_at_iso = charged_at.isoformat()
    amount = resource.get("amount") if isinstance(resource.get("amount"), dict) else {}
    amount_cents = _parse_cents(amount.get("total"))
    currency = amount.get("currency") if isinstance(amount.get("currency"), str) else None

    def finish(outcome: str, action: str, reason: str, mandate: Optional[OpenPaymentMandate] = None) -> Dict[str, Any]:
        record_recurring_charge(
            sale_id=sale_id, subscription_id=sub_id, mandate_hash=mandate_hash,
            amount_cents=amount_cents or 0, currency=currency or "", status=outcome,
            reason=reason, charged_at=charged_at_iso,
        )
        extra: Dict[str, Any] = {"sale_id": sale_id, "subscription_id": sub_id, "amount_cents": amount_cents}
        if mandate is not None:
            extra.update(_usage_summary(mandate, *get_open_mandate_total_usage(mandate_hash)))
        logger.info("[RECURRING] sale %s on %s: %s / %s (%s)", sale_id, sub_id, outcome, action, reason)
        return _decision(outcome, action, reason, **extra)

    if amount_cents is None or not currency:
        return finish(UNVERIFIED, ACTION_SUSPEND, "MALFORMED_AMOUNT: sale amount is missing or not exact to the cent.")

    # 1. Integrity of the stored owner mandate
    mandate, problem = _verify_stored_mandate(record)
    if mandate is None:
        return finish(UNVERIFIED, ACTION_SUSPEND, problem)

    # A charge on a subscription this service already stopped is unauthorized
    if record.get("status") in ("CANCELLED", "SUSPENDED", "STOP_FAILED"):
        return finish(OUT_OF_MANDATE, ACTION_CANCEL,
                      f"CHARGE_AFTER_STOP: subscription was already {record['status'].lower()}.", mandate)

    # A charge on a cryptographically revoked mandate is unauthorized
    if is_mandate_revoked(mandate_hash):
        return finish(OUT_OF_MANDATE, ACTION_CANCEL,
                      "MANDATE_REVOKED: owner revoked this payment mandate.", mandate)

    created_at = _parse_time(record.get("created_at")) or charged_at
    is_initial = (
        not record.get("initial_sale_id")
        and (charged_at - created_at).total_seconds() < BILLING_CYCLE_SECONDS / 2
    )
    if is_initial:
        # The purchase already verified and counted this charge; only check it matches
        if amount_cents != record["agreed_amount_cents"] or currency != record["currency"]:
            return finish(UNVERIFIED, ACTION_SUSPEND,
                          f"AMOUNT_MISMATCH: first charge {amount_cents} {currency} differs from the "
                          f"verified purchase ({record['agreed_amount_cents']} {record['currency']}).", mandate)
        bind_initial_sale(sub_id, sale_id)
        outcome, reason = INITIAL, "First charge matches the AP2-verified purchase."
    else:
        # 2. Expiry at the time PayPal charged
        if not isinstance(mandate.exp, int) or mandate.exp <= charged_at.timestamp():
            return finish(OUT_OF_MANDATE, ACTION_CANCEL, "MANDATE_EXPIRED: the owner's mandate had expired when PayPal charged.", mandate)

        # 3. Owner constraints, evaluated by the vendored AP2 SDK against usage so far
        used_cents, used_count = get_open_mandate_total_usage(mandate_hash)
        candidate = PaymentMandate(
            vct="mandate.payment.1",
            transaction_id=sale_id,
            payment_amount=Amount(amount=amount_cents, currency=currency),
            payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
            payment_instrument=PaymentInstrument(type="paypal_vault", id=f"vault_{sub_id}"),
        )
        try:
            violations = check_payment_constraints(
                mandate, candidate, mandate_context=MandateContext(total_amount=used_cents, total_uses=used_count)
            )
        except Exception as e:
            return finish(UNVERIFIED, ACTION_SUSPEND, f"CONSTRAINT_EVALUATION_FAILED: {e}", mandate)
        if violations:
            return finish(OUT_OF_MANDATE, ACTION_CANCEL, "MANDATE_VIOLATION: " + "; ".join(violations), mandate)

        # 4. The charge must match the price the agent agreed to
        if amount_cents != record["agreed_amount_cents"] or currency != record["currency"]:
            return finish(UNVERIFIED, ACTION_SUSPEND,
                          f"AMOUNT_MISMATCH: renewal {amount_cents} {currency} differs from the agreed "
                          f"{record['agreed_amount_cents']} {record['currency']}.", mandate)
        outcome, reason = VERIFIED, "Renewal authorized by the owner's AP2 mandate."

    # Authorized. Record it, then make sure PayPal is not left able to make an unauthorized next charge.
    record_recurring_charge(
        sale_id=sale_id, subscription_id=sub_id, mandate_hash=mandate_hash, amount_cents=amount_cents,
        currency=currency, status=outcome, reason=reason, charged_at=charged_at_iso,
    )
    renewal_receipt_jwt = create_renewal_receipt_jwt(
        sale_id=sale_id,
        subscription_id=sub_id,
        mandate_hash=mandate_hash,
        buyer_email=record.get("buyer_email") or "",
        amount_cents=amount_cents,
        currency=currency,
        outcome=outcome,
        charged_at=charged_at_iso,
    )
    used_cents, used_count = get_open_mandate_total_usage(mandate_hash)
    blocker = _next_charge_blocker(mandate, used_cents, used_count, record["agreed_amount_cents"], charged_at)
    action = ACTION_CANCEL if blocker else ACTION_NONE
    logger.info("[RECURRING] sale %s on %s: %s (%s)", sale_id, sub_id, outcome, blocker or "next charge authorized")
    return _decision(
        outcome, action, blocker or reason,
        sale_id=sale_id, subscription_id=sub_id, amount_cents=amount_cents,
        renewal_receipt_jwt=renewal_receipt_jwt,
        **_usage_summary(mandate, used_cents, used_count),
    )
