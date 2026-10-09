"""
AP2 v0.2 Merchant Service.
Implements Google AP2 v0.2 Protocol (released 2026-04-28) using Google's reference SDK.
Handles:
1. Merchant-signed Checkout JWT issuance (standard and counter-offer orders).
2. Presentation chain verification (Open + Closed Checkout and Payment Mandates).
3. Merchant-signed Checkout and Payment Receipt generation (ES256).
4. Strict constraint validation, error codes, and audit logging.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

from jwcrypto.jwk import JWK
from pydantic import ValidationError

from ap2.sdk.checkout_mandate_chain import CheckoutMandateChain
from ap2.sdk.generated.checkout_receipt import (
    CheckoutReceipt,
    CheckoutReceiptError,
    CheckoutReceiptSuccess,
)
from ap2.sdk.generated.payment_receipt import (
    PaymentReceipt,
    PaymentReceiptError,
    PaymentReceiptSuccess,
)
from ap2.sdk.generated.types.amount import Amount
from ap2.sdk.generated.types.checkout import Checkout, Status
from ap2.sdk.generated.types.item import Item
from ap2.sdk.generated.types.line_item import LineItem
from ap2.sdk.generated.types.link import Link
from ap2.sdk.generated.types.merchant import Merchant
from ap2.sdk.generated.types.total import Total
from ap2.sdk.jwt_helper import create_jwt, verify_jwt
from ap2.sdk.mandate import MandateClient
from ap2.sdk.payment_mandate_chain import PaymentMandateChain
from ap2.sdk.sdjwt import common

from ..config import settings
from .ap2_keys import (
    get_demo_agent_key,
    get_demo_user_key,
    get_merchant_key,
    get_merchant_public_jwk,
    get_merchant_public_key,
)
from .plan_catalog import resolve_plan, quota_label

logger = logging.getLogger("ap2_service")

# Canonical AP2 v0.2 Merchant Identity
AP2_MERCHANT_ID = "merchant-ap2-autonomous"
AP2_MERCHANT_NAME = "AP2 Autonomous Node Network"
AP2_MERCHANT_DOMAIN = "https://ap2-commerce.org"

# Canonical AP2 v0.2 Spec Error Codes
ERR_INVALID_CREDENTIAL = "invalid_credential"
ERR_INVALID_MANDATE = "invalid_mandate"
ERR_UNRESOLVED_CONSTRAINT = "unresolved_constraint"
ERR_MANDATES_NOT_SUPPORTED = "mandates_not_supported"

# In-memory store for issued orders & receipts (for audit & replay defenses)
_ISSUED_CHECKOUTS: Dict[str, Dict[str, Any]] = {}
_RECEIPT_STORE: Dict[str, Dict[str, Any]] = {}


def dollars_to_minor_units(dollars: float) -> int:
    """Converts a USD amount (e.g. 79.99) into integer minor units (e.g. 7999 cents)."""
    return int(round(dollars * 100))


def minor_units_to_dollars(minor: int) -> float:
    """Converts integer minor units (e.g. 7999 cents) into USD dollars (e.g. 79.99)."""
    return round(minor / 100.0, 2)


def compute_checkout_hash(checkout_jwt: str) -> str:
    """Computes SHA-256 digest of serialized checkout JWT."""
    return hashlib.sha256(checkout_jwt.encode("utf-8")).hexdigest()


def create_merchant_checkout(
    tier_id: str,
    monthly_price: float,
    contractor_email: Optional[str] = None,
    order_id: Optional[str] = None,
    is_counter_offer: bool = False,
    counter_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Constructs and ES256-signs an authentic UCP/AP2 Checkout object.
    The returned Checkout JWT binds merchant, line item, and price in integer minor units.
    """
    clean_tier = tier_id.strip().lower()
    plan_info = resolve_plan(clean_tier) or {}
    plan_title = plan_info.get("title", f"AP2 Compute Tier ({clean_tier})")
    price_cents = dollars_to_minor_units(monthly_price)
    chk_id = order_id or f"chk_{uuid.uuid4().hex[:12]}"

    merchant_obj = Merchant(
        id=AP2_MERCHANT_ID,
        name=AP2_MERCHANT_NAME,
        website=AP2_MERCHANT_DOMAIN,
    )

    line_item = LineItem(
        id=f"li_{clean_tier}",
        item=Item(id=clean_tier, title=plan_title, price=price_cents),
        quantity=1,
        totals=[
            Total(type="subtotal", amount=price_cents),
            Total(type="total", amount=price_cents),
        ],
    )

    links = [
        Link(type="terms_of_service", url="https://ap2-commerce.org/terms"),
        Link(type="privacy_policy", url="https://ap2-commerce.org/privacy"),
    ]

    checkout_model = Checkout(
        id=chk_id,
        merchant=merchant_obj,
        line_items=[line_item],
        status=Status.ready_for_complete,
        currency="USD",
        totals=[
            Total(type="subtotal", amount=price_cents),
            Total(type="total", amount=price_cents),
        ],
        links=links,
    )

    checkout_payload = checkout_model.model_dump(mode="json", exclude_none=True)
    if is_counter_offer:
        checkout_payload["is_counter_offer"] = True
        checkout_payload["counter_reason"] = counter_reason or "Budget constrained: recommended tier within approved spending cap."

    merchant_key = get_merchant_key()
    header = {
        "alg": "ES256",
        "typ": "JWT",
        "kid": merchant_key.kid or settings.ap2_merchant_key_id,
    }

    checkout_jwt = create_jwt(header, checkout_payload, merchant_key)
    checkout_hash = compute_checkout_hash(checkout_jwt)

    record = {
        "order_id": chk_id,
        "checkout_id": chk_id,
        "checkout_jwt": checkout_jwt,
        "checkout_hash": checkout_hash,
        "tier_id": clean_tier,
        "title": plan_title,
        "price_cents": price_cents,
        "monthly_price": monthly_price,
        "currency": "USD",
        "contractor_email": contractor_email,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "is_counter_offer": is_counter_offer,
    }
    _ISSUED_CHECKOUTS[chk_id] = record
    _ISSUED_CHECKOUTS[checkout_hash] = record

    return record


def create_merchant_counter_offer(
    requested_tier_id: str,
    counter_tier_id: str = "ap2-batch",
    counter_price: float = 49.99,
    budget_cap: float = 60.00,
    contractor_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Creates a merchant-signed counter-offer Checkout JWT for the down-tier.
    Provides verifiable proof that the merchant proposes the alternative tier within the cap.
    """
    reason = (
        f"Requested tier '{requested_tier_id}' lists above the monthly budget cap of ${budget_cap:.2f}. "
        f"Counter-offer proposed: {counter_tier_id} ({quota_label(counter_tier_id, profile='ap2')}) at ${counter_price:.2f}/mo."
    )
    return create_merchant_checkout(
        tier_id=counter_tier_id,
        monthly_price=counter_price,
        contractor_email=contractor_email,
        is_counter_offer=True,
        counter_reason=reason,
    )


def create_checkout_receipt_jwt(
    order_id: str,
    closed_mandate_reference: str,
    status: str = "Success",
    error: Optional[str] = None,
    error_description: Optional[str] = None,
) -> str:
    """
    Creates an ES256-signed AP2 Checkout Receipt JWT conforming to Google SDK CheckoutReceipt schema.
    """
    merchant_key = get_merchant_key()
    now_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    iss = AP2_MERCHANT_NAME

    if status.lower() == "success":
        receipt_obj = CheckoutReceipt(
            root=CheckoutReceiptSuccess(
                status="Success",
                iss=iss,
                iat=now_ts,
                reference=closed_mandate_reference,
                order_id=order_id,
            )
        )
    else:
        receipt_obj = CheckoutReceipt(
            root=CheckoutReceiptError(
                status="Error",
                iss=iss,
                iat=now_ts,
                reference=closed_mandate_reference,
                error=error or ERR_INVALID_MANDATE,
                error_description=error_description or "Checkout mandate constraint check failed.",
                order_id=order_id,
            )
        )

    header = {
        "alg": "ES256",
        "typ": "JWT",
        "kid": merchant_key.kid or settings.ap2_merchant_key_id,
    }
    payload = receipt_obj.root.model_dump(mode="json", exclude_none=True)
    token = create_jwt(header, payload, merchant_key)
    _RECEIPT_STORE[closed_mandate_reference] = payload
    return token


def create_payment_receipt_jwt(
    payment_id: str,
    closed_mandate_reference: str,
    status: str = "Success",
    error: Optional[str] = None,
    error_description: Optional[str] = None,
) -> str:
    """
    Creates an ES256-signed AP2 Payment Receipt JWT conforming to Google SDK PaymentReceipt schema.
    """
    merchant_key = get_merchant_key()
    now_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
    iss = AP2_MERCHANT_NAME

    if status.lower() == "success":
        receipt_obj = PaymentReceipt(
            root=PaymentReceiptSuccess(
                status="Success",
                iss=iss,
                iat=now_ts,
                reference=closed_mandate_reference,
                payment_id=payment_id,
                psp_confirmation_id=payment_id,
                network_confirmation_id=f"net_{payment_id}",
            )
        )
    else:
        receipt_obj = PaymentReceipt(
            root=PaymentReceiptError(
                status="Error",
                iss=iss,
                iat=now_ts,
                reference=closed_mandate_reference,
                payment_id=payment_id,
                error=error or ERR_INVALID_MANDATE,
                error_description=error_description or "Payment mandate constraint check failed.",
            )
        )

    header = {
        "alg": "ES256",
        "typ": "JWT",
        "kid": merchant_key.kid or settings.ap2_merchant_key_id,
    }
    payload = receipt_obj.root.model_dump(mode="json", exclude_none=True)
    token = create_jwt(header, payload, merchant_key)
    _RECEIPT_STORE[closed_mandate_reference] = payload
    return token


def verify_receipt_jwt(receipt_jwt: str) -> Dict[str, Any]:
    """Verifies the ES256 signature and returns the receipt payload."""
    pub_key = get_merchant_public_key()
    return verify_jwt(receipt_jwt, pub_key)


def get_stored_receipt(reference: str) -> Optional[Dict[str, Any]]:
    """Checks whether a receipt exists for the given closed mandate reference."""
    return _RECEIPT_STORE.get(reference)


def get_issued_checkout(identifier: str) -> Optional[Dict[str, Any]]:
    """Retrieves an issued merchant checkout record by order_id or checkout_hash."""
    return _ISSUED_CHECKOUTS.get(identifier)


def resolve_root_public_key(parsed_token: common.ParsedToken, override_key: Optional[JWK] = None) -> JWK:
    """Resolves the public JWK for the root issuer of a mandate chain."""
    if override_key is not None:
        return override_key

    header = parsed_token.header if hasattr(parsed_token, "header") else getattr(parsed_token, "jwt_header", {})
    kid = header.get("kid")
    demo_user = get_demo_user_key()
    if not kid or kid == demo_user.kid or kid == "demo-user-key":
        return JWK.from_json(demo_user.export_public())

    demo_agent = get_demo_agent_key()
    if kid == demo_agent.kid or kid == "demo-agent-key":
        return JWK.from_json(demo_agent.export_public())

    # Fallback: check database registered buyer keys
    from ..database import get_buyer_key
    pub_json = get_buyer_key(kid)
    if pub_json:
        try:
            return JWK.from_json(pub_json)
        except Exception:
            pass

    # If header contains self-asserted jwk
    if "jwk" in header:
        try:
            jwk_dict = header["jwk"]
            return JWK.from_json(json.dumps(jwk_dict))
        except Exception:
            pass

    # In mock / demo mode, fallback to demo_user
    if settings.mock_external_apis:
        return JWK.from_json(demo_user.export_public())

    raise ValueError(f"UNTRUSTED_ROOT_KEY: No registered public key found for kid '{kid}'.")


def verify_ap2_chains(
    checkout_mandate_token: str,
    payment_mandate_token: str,
    checkout_jwt: Optional[str] = None,
    user_public_key: Optional[JWK] = None,
    expected_aud: str = AP2_MERCHANT_ID,
    expected_nonce: Optional[str] = None,
    enforce_replay_defense: bool = True,
) -> Dict[str, Any]:
    """
    Verifies the complete AP2 v0.2 Checkout and Payment Mandate chains.
    Conforms strictly to the Google AP2 v0.2 spec verification lifecycle.

    Returns:
        Dict containing validation outcome, parsed models, receipts, and errors.
    """
    client = MandateClient()
    order_id = "unknown_order"

    # Step 0: Resolve checkout_jwt if not provided directly
    if not checkout_jwt:
        try:
            parts = checkout_mandate_token.split("~~")
            if len(parts) >= 2:
                from ap2.sdk.utils import b64url_decode
                closed_part = parts[1].split("~")[0]
                payload_b64 = closed_part.split(".")[1]
                payload_json = json.loads(b64url_decode(payload_b64).decode("utf-8"))
                chk_hash = payload_json.get("checkout_hash")
                if chk_hash and chk_hash in _ISSUED_CHECKOUTS:
                    checkout_jwt = _ISSUED_CHECKOUTS[chk_hash]["checkout_jwt"]
        except Exception:
            pass

    if not checkout_jwt:
        ref = f"err_{uuid.uuid4().hex[:8]}"
        err_receipt = create_checkout_receipt_jwt(
            order_id=order_id,
            closed_mandate_reference=ref,
            status="Error",
            error=ERR_INVALID_MANDATE,
            error_description="checkout_jwt is required to verify checkout constraints.",
        )
        return {
            "valid": False,
            "error": ERR_INVALID_MANDATE,
            "error_description": "checkout_jwt is required to verify checkout constraints.",
            "checkout_receipt": err_receipt,
            "payment_receipt": None,
        }

    checkout_hash = compute_checkout_hash(checkout_jwt)

    # Step 1: Verify merchant Checkout JWT signature and integrity
    try:
        chk_payload = verify_jwt(checkout_jwt, get_merchant_public_key())
        order_id = chk_payload.get("id", order_id)
    except Exception as e:
        logger.warning(f"Merchant Checkout JWT signature verification failed: {e}")
        ref = f"chk_hash_{checkout_hash[:16]}"
        err_receipt = create_checkout_receipt_jwt(
            order_id=order_id,
            closed_mandate_reference=ref,
            status="Error",
            error=ERR_INVALID_CREDENTIAL,
            error_description=f"Checkout JWT signature verification failed: {e}",
        )
        return {
            "valid": False,
            "error": ERR_INVALID_CREDENTIAL,
            "error_description": f"Checkout JWT signature verification failed: {e}",
            "checkout_receipt": err_receipt,
            "payment_receipt": None,
        }

    # Step 2: Verify Checkout Mandate chain
    def checkout_root_provider(t: common.ParsedToken) -> JWK:
        return resolve_root_public_key(t, override_key=user_public_key)

    try:
        checkout_payloads = client.verify(
            token=checkout_mandate_token,
            key_or_provider=checkout_root_provider,
            expected_aud=expected_aud,
            expected_nonce=expected_nonce,
        )
    except ValueError as e:
        msg = str(e)
        logger.warning(f"Checkout mandate verification crypto/structure failure: {msg}")
        code = ERR_UNRESOLVED_CONSTRAINT if "constraint" in msg.lower() else ERR_INVALID_CREDENTIAL
        ref = f"chk_{checkout_hash[:16]}"
        err_receipt = create_checkout_receipt_jwt(
            order_id=order_id,
            closed_mandate_reference=ref,
            status="Error",
            error=code,
            error_description=msg,
        )
        return {
            "valid": False,
            "error": code,
            "error_description": msg,
            "checkout_receipt": err_receipt,
            "payment_receipt": None,
        }

    try:
        checkout_chain = CheckoutMandateChain.parse(checkout_payloads)
        chk_violations = checkout_chain.verify(
            expected_checkout_hash=checkout_hash,
            checkout_jwt=checkout_jwt,
        )
        if chk_violations:
            detail = "; ".join(chk_violations)
            logger.warning(f"Checkout mandate constraint violations: {detail}")
            ref = checkout_chain.closed_mandate.checkout_hash
            err_receipt = create_checkout_receipt_jwt(
                order_id=order_id,
                closed_mandate_reference=ref,
                status="Error",
                error=ERR_INVALID_MANDATE,
                error_description=detail,
            )
            return {
                "valid": False,
                "error": ERR_INVALID_MANDATE,
                "error_description": detail,
                "checkout_receipt": err_receipt,
                "payment_receipt": None,
            }
    except Exception as e:
        detail = str(e)
        logger.warning(f"Checkout mandate parsing error: {detail}")
        ref = f"chk_{checkout_hash[:16]}"
        err_receipt = create_checkout_receipt_jwt(
            order_id=order_id,
            closed_mandate_reference=ref,
            status="Error",
            error=ERR_INVALID_MANDATE,
            error_description=detail,
        )
        return {
            "valid": False,
            "error": ERR_INVALID_MANDATE,
            "error_description": detail,
            "checkout_receipt": err_receipt,
            "payment_receipt": None,
        }

    # Step 3: Verify Payment Mandate chain
    def payment_root_provider(t: common.ParsedToken) -> JWK:
        return resolve_root_public_key(t, override_key=user_public_key)

    try:
        payment_payloads = client.verify(
            token=payment_mandate_token,
            key_or_provider=payment_root_provider,
            expected_aud=expected_aud,
            expected_nonce=expected_nonce,
        )
    except ValueError as e:
        msg = str(e)
        logger.warning(f"Payment mandate verification crypto/structure failure: {msg}")
        code = ERR_UNRESOLVED_CONSTRAINT if "constraint" in msg.lower() else ERR_INVALID_CREDENTIAL
        ref = f"pay_{checkout_hash[:16]}"
        err_receipt = create_payment_receipt_jwt(
            payment_id=f"err_{uuid.uuid4().hex[:8]}",
            closed_mandate_reference=ref,
            status="Error",
            error=code,
            error_description=msg,
        )
        return {
            "valid": False,
            "error": code,
            "error_description": msg,
            "checkout_receipt": None,
            "payment_receipt": err_receipt,
        }

    try:
        payment_chain = PaymentMandateChain.parse(payment_payloads)
        pay_violations = payment_chain.verify(
            expected_transaction_id=checkout_hash,
            expected_open_checkout_hash=checkout_hash,
        )
        if pay_violations:
            detail = "; ".join(pay_violations)
            logger.warning(f"Payment mandate constraint violations: {detail}")
            ref = payment_chain.closed_mandate.transaction_id
            err_receipt = create_payment_receipt_jwt(
                payment_id=f"err_{uuid.uuid4().hex[:8]}",
                closed_mandate_reference=ref,
                status="Error",
                error=ERR_INVALID_MANDATE,
                error_description=detail,
            )
            return {
                "valid": False,
                "error": ERR_INVALID_MANDATE,
                "error_description": detail,
                "checkout_receipt": None,
                "payment_receipt": err_receipt,
            }
    except Exception as e:
        detail = str(e)
        logger.warning(f"Payment mandate parsing error: {detail}")
        ref = f"pay_{checkout_hash[:16]}"
        err_receipt = create_payment_receipt_jwt(
            payment_id=f"err_{uuid.uuid4().hex[:8]}",
            closed_mandate_reference=ref,
            status="Error",
            error=ERR_INVALID_MANDATE,
            error_description=detail,
        )
        return {
            "valid": False,
            "error": ERR_INVALID_MANDATE,
            "error_description": detail,
            "checkout_receipt": None,
            "payment_receipt": err_receipt,
        }

    # Step 4: Replay defense check
    closed_ref = checkout_chain.closed_mandate.checkout_hash
    if enforce_replay_defense and get_stored_receipt(closed_ref):
        stored = get_stored_receipt(closed_ref)
        if stored.get("status") == "Success":
            msg = f"REPLAY_DETECTED: Mandate with reference '{closed_ref}' has already been successfully redeemed."
            logger.warning(msg)
            err_receipt = create_checkout_receipt_jwt(
                order_id=order_id,
                closed_mandate_reference=closed_ref,
                status="Error",
                error=ERR_INVALID_MANDATE,
                error_description=msg,
            )
            return {
                "valid": False,
                "error": ERR_INVALID_MANDATE,
                "error_description": msg,
                "checkout_receipt": err_receipt,
                "payment_receipt": None,
            }

    # Step 5: Extract verified transaction details
    closed_chk = checkout_chain.closed_mandate
    closed_pay = payment_chain.closed_mandate

    price_dollars = minor_units_to_dollars(closed_pay.payment_amount.amount)
    tier_id = chk_payload.get("line_items", [{}])[0].get("item", {}).get("id", "ap2-gateway")

    # Step 6: Generate authentic merchant-signed Success receipts
    payment_id = f"pay_{uuid.uuid4().hex[:12]}"
    chk_receipt_jwt = create_checkout_receipt_jwt(
        order_id=order_id,
        closed_mandate_reference=closed_ref,
        status="Success",
    )
    pay_receipt_jwt = create_payment_receipt_jwt(
        payment_id=payment_id,
        closed_mandate_reference=closed_pay.transaction_id,
        status="Success",
    )

    logger.info(
        f"[AP2_VERIFIER] Successfully verified AP2 v0.2 checkout & payment mandate chains for order '{order_id}' "
        f"(${price_dollars:.2f} / {closed_pay.payment_amount.amount} minor units, tier: {tier_id})"
    )

    return {
        "valid": True,
        "order_id": order_id,
        "payment_id": payment_id,
        "tier_id": tier_id,
        "monthly_price": price_dollars,
        "price_cents": closed_pay.payment_amount.amount,
        "checkout_hash": checkout_hash,
        "checkout_receipt": chk_receipt_jwt,
        "payment_receipt": pay_receipt_jwt,
        "checkout_chain": checkout_chain,
        "payment_chain": payment_chain,
        "open_checkout_mandate": checkout_chain.open_mandate,
        "closed_checkout_mandate": closed_chk,
        "open_payment_mandate": payment_chain.open_mandate,
        "closed_payment_mandate": closed_pay,
    }
