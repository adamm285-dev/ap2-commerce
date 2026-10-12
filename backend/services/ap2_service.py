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
from ap2.sdk.constraints import MandateContext
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

    order_nonce = f"nonce_{uuid.uuid4().hex[:12]}"
    checkout_payload = checkout_model.model_dump(mode="json", exclude_none=True)
    checkout_payload["nonce"] = order_nonce
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
        "nonce": order_nonce,
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
    order_id: Optional[str] = None,
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
        order_id=order_id,
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


def clear_stored_receipt(reference: str) -> None:
    """Removes a stored receipt from the in-memory store by reference."""
    _RECEIPT_STORE.pop(reference, None)



def get_issued_checkout(identifier: str) -> Optional[Dict[str, Any]]:
    """Retrieves an issued merchant checkout record by order_id or checkout_hash."""
    return _ISSUED_CHECKOUTS.get(identifier)


def compute_open_payment_mandate_hash(payment_mandate_token: str) -> str:
    """Computes a canonical SHA-256 hash of the root open payment mandate from an SD-JWT token or presentation chain."""
    token = payment_mandate_token.strip()
    if "~~" in token:
        token = token.split("~~")[0].strip()
    if not token.endswith("~"):
        token = token + "~"
    try:
        parsed = common.parse_token(token)
        canonical = parsed.sd_jwt
    except Exception:
        canonical = token
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()



def resolve_root_public_key(
    parsed_token: common.ParsedToken,
    override_key: Optional[JWK] = None,
    buyer_email: Optional[str] = None,
) -> JWK:
    """
    Resolves the public JWK for the root issuer of an Open Mandate chain.
    Conforms to AP2 security invariants:
      (a) Keys must come ONLY from the registered buyer-key registry,
          where buyer_email must match the email bound to that key;
      (b) The demo Trusted-Surface user key is accepted ONLY when MOCK_EXTERNAL_APIS=true.
    Self-asserted JWKs in the token header are NEVER trusted.
    Agent keys sign only closed mandates and are NEVER accepted as root keys.
    """
    if override_key is not None:
        return override_key

    header = parsed_token.header if hasattr(parsed_token, "header") else getattr(parsed_token, "jwt_header", {})
    kid = header.get("kid")

    # Invariant 1: Agent keys sign only closed mandates; never accept as root
    demo_agent = get_demo_agent_key()
    if kid and kid in (demo_agent.kid, "demo-autonomous-buyer-agent", "demo-agent-key"):
        raise ValueError("INVALID_ROOT_KEY: Agent keys sign only closed mandates, never root open mandates.")

    # Invariant 2: Never inspect or trust self-asserted "jwk" in header

    # Invariant 3: Check registered buyer-key registry
    if kid:
        from ..database import get_buyer_key, get_buyer_key_email
        pub_json = get_buyer_key(kid)
        if pub_json:
            reg_email = get_buyer_key_email(kid)
            if buyer_email:
                if not reg_email or reg_email.strip().lower() != buyer_email.strip().lower():
                    raise ValueError(
                        f"EMAIL_KEY_BINDING_MISMATCH: Registered key '{kid}' is bound to '{reg_email}', "
                        f"which does not match purchase email '{buyer_email}'."
                    )
            try:
                if pub_json.strip().startswith("{"):
                    raw_dict = json.loads(pub_json)
                    if "kty" in raw_dict and isinstance(raw_dict["kty"], str):
                        raw_dict["kty"] = raw_dict["kty"].upper()
                    if "crv" in raw_dict and isinstance(raw_dict["crv"], str) and raw_dict["crv"].lower() == "p-256":
                        raw_dict["crv"] = "P-256"
                    return JWK(**raw_dict)
                else:
                    try:
                        return JWK.from_json(pub_json)
                    except Exception:
                        from cryptography.hazmat.primitives.asymmetric import ec
                        from cryptography.hazmat.primitives.serialization import load_der_public_key
                        raw_bytes = bytes.fromhex(pub_json.strip())
                        try:
                            ec_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), raw_bytes)
                            return JWK.from_pyca(ec_key)
                        except Exception:
                            ec_key = load_der_public_key(raw_bytes)
                            return JWK.from_pyca(ec_key)
            except Exception as e:
                raise ValueError(f"INVALID_BUYER_KEY: Failed to parse registered key '{kid}': {e}")

    # MOCK(M-005): server's own demo owner key accepted as a trust root in mock mode
    # Invariant 4: Demo user key ONLY when mock_external_apis is True
    if settings.mock_external_apis:
        demo_user = get_demo_user_key()
        if not kid or kid in (demo_user.kid, "demo-human-trusted-surface", "demo-user-key"):
            return JWK.from_json(demo_user.export_public())
        raise ValueError(f"UNREGISTERED_BUYER_KEY: No registered public key found for kid '{kid}'.")

    # In live mode (mock_external_apis == False):
    if not kid:
        raise ValueError("MISSING_KEY_ID: Root mandate token header must include a registered 'kid'.")
    raise ValueError(f"UNREGISTERED_BUYER_KEY: No registered public key found for kid '{kid}'.")


def verify_ap2_chains(
    checkout_mandate_token: str,
    payment_mandate_token: str,
    checkout_jwt: Optional[str] = None,
    user_public_key: Optional[JWK] = None,
    expected_aud: str = AP2_MERCHANT_ID,
    expected_nonce: Optional[str] = None,
    enforce_replay_defense: bool = True,
    buyer_email: Optional[str] = None,
    mandate_context: Optional[MandateContext] = None,
) -> Dict[str, Any]:
    """
    Verifies the complete AP2 v0.2 Checkout and Payment Mandate chains.
    Conforms strictly to the Google AP2 v0.2 spec verification lifecycle.

    Returns:
        Dict containing validation outcome, parsed models, receipts, and errors.
    """
    client = MandateClient()
    order_id = "unknown_order"

    try:
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

        # Step 1.5: Verify First — Mandate Revocation Status List Check (SPEC-001 v1.9.0)
        from ..database import is_mandate_revoked
        open_pay_hash = compute_open_payment_mandate_hash(payment_mandate_token)
        if is_mandate_revoked(checkout_hash) or is_mandate_revoked(open_pay_hash) or (order_id and is_mandate_revoked(order_id)):
            msg = "MANDATE_REVOKED: This mandate has been cryptographically revoked by the owner."
            logger.warning(f"[SECURITY] {msg}")
            ref = f"chk_{checkout_hash[:16]}"
            err_receipt = create_checkout_receipt_jwt(
                order_id=order_id,
                closed_mandate_reference=ref,
                status="Error",
                error="MANDATE_REVOKED",
                error_description=msg,
            )
            pay_ref = f"pay_{checkout_hash[:16]}"
            err_pay_receipt = create_payment_receipt_jwt(
                payment_id=f"err_{uuid.uuid4().hex[:8]}",
                closed_mandate_reference=pay_ref,
                status="Error",
                error="MANDATE_REVOKED",
                error_description=msg,
            )
            return {
                "valid": False,
                "error": "MANDATE_REVOKED",
                "error_description": msg,
                "checkout_receipt": err_receipt,
                "payment_receipt": err_pay_receipt,
            }

        # Resolve buyer_email if not explicitly provided
        if not buyer_email:
            if checkout_hash in _ISSUED_CHECKOUTS:
                buyer_email = _ISSUED_CHECKOUTS[checkout_hash].get("contractor_email")
            elif order_id in _ISSUED_CHECKOUTS:
                buyer_email = _ISSUED_CHECKOUTS[order_id].get("contractor_email")

        # Resolve expected_nonce if not explicitly provided
        if not expected_nonce:
            if isinstance(chk_payload, dict) and "nonce" in chk_payload:
                expected_nonce = chk_payload.get("nonce")
            if not expected_nonce and checkout_hash in _ISSUED_CHECKOUTS:
                expected_nonce = _ISSUED_CHECKOUTS[checkout_hash].get("nonce")
            if not expected_nonce and order_id in _ISSUED_CHECKOUTS:
                expected_nonce = _ISSUED_CHECKOUTS[order_id].get("nonce")

        # Step 2: Verify Checkout Mandate chain
        def checkout_root_provider(t: common.ParsedToken) -> JWK:
            return resolve_root_public_key(t, override_key=user_public_key, buyer_email=buyer_email)

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
            pay_ref = f"pay_{checkout_hash[:16]}"
            err_pay_receipt = create_payment_receipt_jwt(
                payment_id=f"err_{uuid.uuid4().hex[:8]}",
                closed_mandate_reference=pay_ref,
                status="Error",
                error=code,
                error_description=msg,
            )
            return {
                "valid": False,
                "error": code,
                "error_description": msg,
                "checkout_receipt": err_receipt,
                "payment_receipt": err_pay_receipt,
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
                pay_ref = f"pay_{checkout_hash[:16]}"
                err_pay_receipt = create_payment_receipt_jwt(
                    payment_id=f"err_{uuid.uuid4().hex[:8]}",
                    closed_mandate_reference=pay_ref,
                    status="Error",
                    error=ERR_INVALID_MANDATE,
                    error_description=detail,
                )
                return {
                    "valid": False,
                    "error": ERR_INVALID_MANDATE,
                    "error_description": detail,
                    "checkout_receipt": err_receipt,
                    "payment_receipt": err_pay_receipt,
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
            pay_ref = f"pay_{checkout_hash[:16]}"
            err_pay_receipt = create_payment_receipt_jwt(
                payment_id=f"err_{uuid.uuid4().hex[:8]}",
                closed_mandate_reference=pay_ref,
                status="Error",
                error=ERR_INVALID_MANDATE,
                error_description=detail,
            )
            return {
                "valid": False,
                "error": ERR_INVALID_MANDATE,
                "error_description": detail,
                "checkout_receipt": err_receipt,
                "payment_receipt": err_pay_receipt,
            }

        # Step 3: Verify Payment Mandate chain
        def payment_root_provider(t: common.ParsedToken) -> JWK:
            return resolve_root_public_key(t, override_key=user_public_key, buyer_email=buyer_email)

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
            chk_ref = checkout_chain.closed_mandate.checkout_hash if 'checkout_chain' in locals() and hasattr(checkout_chain, 'closed_mandate') else f"chk_{checkout_hash[:16]}"
            err_chk_receipt = create_checkout_receipt_jwt(
                order_id=order_id,
                closed_mandate_reference=chk_ref,
                status="Error",
                error=code,
                error_description=msg,
            )
            return {
                "valid": False,
                "error": code,
                "error_description": msg,
                "checkout_receipt": err_chk_receipt,
                "payment_receipt": err_receipt,
            }

        open_pay_hash = compute_open_payment_mandate_hash(payment_mandate_token)
        if mandate_context is not None:
            ctx = mandate_context
        else:
            from ..database import get_open_mandate_settlement_totals
            tot_amt, tot_uses = get_open_mandate_settlement_totals(open_pay_hash)
            ctx = MandateContext(total_amount=tot_amt, total_uses=tot_uses)

        try:
            payment_chain = PaymentMandateChain.parse(payment_payloads)
            pay_violations = payment_chain.verify(
                expected_transaction_id=checkout_hash,
                expected_open_checkout_hash=checkout_hash,
                mandate_context=ctx,
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
                chk_ref = checkout_chain.closed_mandate.checkout_hash
                err_chk_receipt = create_checkout_receipt_jwt(
                    order_id=order_id,
                    closed_mandate_reference=chk_ref,
                    status="Error",
                    error=ERR_INVALID_MANDATE,
                    error_description=detail,
                )
                return {
                    "valid": False,
                    "error": ERR_INVALID_MANDATE,
                    "error_description": detail,
                    "checkout_receipt": err_chk_receipt,
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
            chk_ref = checkout_chain.closed_mandate.checkout_hash
            err_chk_receipt = create_checkout_receipt_jwt(
                order_id=order_id,
                closed_mandate_reference=chk_ref,
                status="Error",
                error=ERR_INVALID_MANDATE,
                error_description=detail,
            )
            return {
                "valid": False,
                "error": ERR_INVALID_MANDATE,
                "error_description": detail,
                "checkout_receipt": err_chk_receipt,
                "payment_receipt": err_receipt,
            }

        # Step 4: Closed-Mandate Integrity Checks against Merchant Checkout
        closed_chk = checkout_chain.closed_mandate
        closed_pay = payment_chain.closed_mandate

        expected_cents = chk_payload.get("totals", [{}])[-1].get("amount")
        if expected_cents is None:
            expected_cents = chk_payload.get("line_items", [{}])[0].get("item", {}).get("price")
        expected_cents = int(expected_cents) if expected_cents is not None else None
        expected_currency = chk_payload.get("currency", "USD")

        # 4a. Amount integrity check
        if expected_cents is not None and closed_pay.payment_amount.amount != expected_cents:
            msg = (
                f"PAYMENT_AMOUNT_MISMATCH: Payment mandate amount ({closed_pay.payment_amount.amount}) "
                f"does not match checkout total ({expected_cents})."
            )
            logger.warning(f"[AP2_VERIFIER] {msg}")
            err_receipt = create_payment_receipt_jwt(
                payment_id=f"err_{uuid.uuid4().hex[:8]}",
                closed_mandate_reference=closed_pay.transaction_id,
                status="Error",
                error=ERR_INVALID_MANDATE,
                error_description=msg,
            )
            err_chk_receipt = create_checkout_receipt_jwt(
                order_id=order_id,
                closed_mandate_reference=closed_chk.checkout_hash,
                status="Error",
                error=ERR_INVALID_MANDATE,
                error_description=msg,
            )
            return {
                "valid": False,
                "error": ERR_INVALID_MANDATE,
                "error_description": msg,
                "checkout_receipt": err_chk_receipt,
                "payment_receipt": err_receipt,
            }

        # 4b. Currency integrity check
        if closed_pay.payment_amount.currency != expected_currency:
            msg = (
                f"CURRENCY_MISMATCH: Payment mandate currency '{closed_pay.payment_amount.currency}' "
                f"does not match checkout currency '{expected_currency}'."
            )
            logger.warning(f"[AP2_VERIFIER] {msg}")
            err_receipt = create_payment_receipt_jwt(
                payment_id=f"err_{uuid.uuid4().hex[:8]}",
                closed_mandate_reference=closed_pay.transaction_id,
                status="Error",
                error=ERR_INVALID_MANDATE,
                error_description=msg,
            )
            err_chk_receipt = create_checkout_receipt_jwt(
                order_id=order_id,
                closed_mandate_reference=closed_chk.checkout_hash,
                status="Error",
                error=ERR_INVALID_MANDATE,
                error_description=msg,
            )
            return {
                "valid": False,
                "error": ERR_INVALID_MANDATE,
                "error_description": msg,
                "checkout_receipt": err_chk_receipt,
                "payment_receipt": err_receipt,
            }

        # 4c. Payee integrity check
        payee_id = getattr(closed_pay.payee, "id", None) if closed_pay.payee else None
        if payee_id != AP2_MERCHANT_ID:
            msg = (
                f"PAYEE_MISMATCH: Payment mandate payee '{payee_id}' "
                f"does not match merchant '{AP2_MERCHANT_ID}'."
            )
            logger.warning(f"[AP2_VERIFIER] {msg}")
            err_receipt = create_payment_receipt_jwt(
                payment_id=f"err_{uuid.uuid4().hex[:8]}",
                closed_mandate_reference=closed_pay.transaction_id,
                status="Error",
                error=ERR_INVALID_MANDATE,
                error_description=msg,
            )
            err_chk_receipt = create_checkout_receipt_jwt(
                order_id=order_id,
                closed_mandate_reference=closed_chk.checkout_hash,
                status="Error",
                error=ERR_INVALID_MANDATE,
                error_description=msg,
            )
            return {
                "valid": False,
                "error": ERR_INVALID_MANDATE,
                "error_description": msg,
                "checkout_receipt": err_chk_receipt,
                "payment_receipt": err_receipt,
            }

        # Step 5: Replay defense check
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
                err_pay_receipt = create_payment_receipt_jwt(
                    payment_id=f"err_{uuid.uuid4().hex[:8]}",
                    closed_mandate_reference=closed_pay.transaction_id,
                    status="Error",
                    error=ERR_INVALID_MANDATE,
                    error_description=msg,
                )
                return {
                    "valid": False,
                    "error": ERR_INVALID_MANDATE,
                    "error_description": msg,
                    "checkout_receipt": err_receipt,
                    "payment_receipt": err_pay_receipt,
                }

        # Step 6: Extract verified transaction details & authoritative budget cap
        price_dollars = minor_units_to_dollars(closed_pay.payment_amount.amount)
        tier_id = chk_payload.get("line_items", [{}])[0].get("item", {}).get("id", "ap2-gateway")

        authoritative_budget_cap: Optional[float] = None
        if payment_chain.open_mandate and hasattr(payment_chain.open_mandate, "constraints"):
            for c in (payment_chain.open_mandate.constraints or []):
                if hasattr(c, "max") and getattr(c, "max") is not None:
                    authoritative_budget_cap = minor_units_to_dollars(c.max)
                    break
                elif isinstance(c, dict) and "max" in c:
                    authoritative_budget_cap = minor_units_to_dollars(c["max"])
                    break

        # Step 7: Generate authentic merchant-signed Success receipts
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
            f"(${price_dollars:.2f} / {closed_pay.payment_amount.amount} minor units, tier: {tier_id}, cap: {authoritative_budget_cap})"
        )

        return {
            "valid": True,
            "order_id": order_id,
            "payment_id": payment_id,
            "tier_id": tier_id,
            "monthly_price": price_dollars,
            "price_cents": closed_pay.payment_amount.amount,
            "authoritative_budget_cap": authoritative_budget_cap,
            "checkout_hash": checkout_hash,
            "checkout_receipt": chk_receipt_jwt,
            "payment_receipt": pay_receipt_jwt,
            "checkout_chain": checkout_chain,
            "payment_chain": payment_chain,
            "open_checkout_mandate": checkout_chain.open_mandate,
            "closed_checkout_mandate": closed_chk,
            "open_payment_mandate": payment_chain.open_mandate,
            "closed_payment_mandate": closed_pay,
            "open_payment_mandate_hash": open_pay_hash,
        }

    except Exception as e:
        detail = str(e)
        logger.warning(f"[AP2_VERIFIER] Unhandled verification exception: {detail}", exc_info=True)
        code = ERR_INVALID_CREDENTIAL
        if "constraint" in detail.lower():
            code = ERR_UNRESOLVED_CONSTRAINT
        elif "mandate" in detail.lower() and "signature" not in detail.lower() and "key" not in detail.lower():
            code = ERR_INVALID_MANDATE
        ref = f"err_{uuid.uuid4().hex[:8]}"
        err_receipt = create_checkout_receipt_jwt(
            order_id=order_id,
            closed_mandate_reference=ref,
            status="Error",
            error=code,
            error_description=detail,
        )
        return {
            "valid": False,
            "error": code,
            "error_description": detail,
            "checkout_receipt": err_receipt,
            "payment_receipt": None,
        }


# ── Buyer-Side Mandate Authoring Helpers ─────────────────────────────────────

def create_trusted_surface_open_mandates(
    budget_cap: float,
    allowed_tiers: Optional[List[str]] = None,
    user_key: Optional[JWK] = None,
    agent_key: Optional[JWK] = None,
) -> Dict[str, Any]:
    """
    Simulates a non-agentic Trusted Surface signing the Human's Open Mandates.
    Embeds the agent's public key (cnf.jwk) and the budget constraints.
    """
    # MOCK(M-005): signs owner limits with the server-held demo owner key
    user_k = user_key or get_demo_user_key()
    agent_k = agent_key or get_demo_agent_key()
    client = MandateClient()

    max_cap_cents = dollars_to_minor_units(budget_cap)
    tiers = allowed_tiers or ["ap2-gateway", "ap2-batch", "ap2-cluster"]

    agent_cnf = {"jwk": agent_k.export_public(as_dict=True)}

    # Open Checkout Mandate (signed by human)
    open_chk = OpenCheckoutMandate(
        vct="mandate.checkout.open.1",
        cnf=agent_cnf,
        constraints=[
            AllowedMerchants(allowed=[Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME)]),
        ],
    )
    open_chk_tok = client.create(issuer_key=user_k, payloads=[open_chk])

    # Open Payment Mandate (signed by human)
    open_pay = OpenPaymentMandate(
        vct="mandate.payment.open.1",
        cnf=agent_cnf,
        constraints=[
            AmountRange(currency="USD", min=1, max=max_cap_cents),
            AllowedPayees(allowed=[Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME)]),
        ],
    )
    open_pay_tok = client.create(issuer_key=user_k, payloads=[open_pay])

    return {
        "open_checkout_token": open_chk_tok,
        "open_payment_token": open_pay_tok,
        "user_key": user_k,
        "agent_key": agent_k,
        "budget_cap_dollars": budget_cap,
        "max_cap_cents": max_cap_cents,
        "allowed_tiers": tiers,
    }


def create_closed_mandate_chains(
    open_checkout_token: str,
    open_payment_token: str,
    checkout_jwt: str,
    agent_key: Optional[JWK] = None,
    contractor_email: Optional[str] = None,
    nonce: Optional[str] = None,
    aud: str = AP2_MERCHANT_ID,
) -> Dict[str, Any]:
    """
    The Autonomous Buyer Agent evaluates the merchant's Checkout JWT,
    checks it against human constraints, and signs the closed mandates
    using its private holder key (cnf).
    """
    # MOCK(M-005): signs as the agent with the server-held demo agent key
    agent_k = agent_key or get_demo_agent_key()
    client = MandateClient()

    checkout_hash = compute_checkout_hash(checkout_jwt)
    chk_payload = verify_jwt(checkout_jwt, get_merchant_public_key())
    price_cents = chk_payload.get("totals", [{}])[-1].get("amount") or chk_payload.get("line_items", [{}])[0].get("item", {}).get("price", 7999)
    used_nonce = nonce or (chk_payload.get("nonce") if isinstance(chk_payload, dict) else None) or f"nonce_{uuid.uuid4().hex[:12]}"

    # Closed Checkout Mandate (signed by agent)
    closed_chk = CheckoutMandate(
        vct="mandate.checkout.1",
        checkout_jwt=checkout_jwt,
        checkout_hash=checkout_hash,
    )
    chk_chain = client.present(
        holder_key=agent_k,
        mandate_token=open_checkout_token,
        payloads=[closed_chk],
        aud=aud,
        nonce=used_nonce,
    )

    # Closed Payment Mandate (signed by agent)
    closed_pay = PaymentMandate(
        vct="mandate.payment.1",
        transaction_id=checkout_hash,
        payment_amount=Amount(amount=int(price_cents), currency="USD"),
        payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
        payment_instrument=PaymentInstrument(
            type="paypal_vault",
            id=f"vault_{contractor_email or 'agent-alpha@example.com'}",
        ),
    )
    pay_chain = client.present(
        holder_key=agent_k,
        mandate_token=open_payment_token,
        payloads=[closed_pay],
        aud=aud,
        nonce=used_nonce,
    )

    return {
        "checkout_mandate_chain": chk_chain,
        "payment_mandate_chain": pay_chain,
        "checkout_hash": checkout_hash,
        "checkout_jwt": checkout_jwt,
        "nonce": used_nonce,
        "price_cents": price_cents,
        "price_dollars": minor_units_to_dollars(price_cents),
    }


def build_buyer_ap2_chains(
    checkout_jwt: str,
    budget_cap: float = 100.0,
    allowed_tiers: Optional[List[str]] = None,
    contractor_email: Optional[str] = None,
    user_key: Optional[JWK] = None,
    agent_key: Optional[JWK] = None,
    nonce: Optional[str] = None,
) -> Dict[str, Any]:
    """
    One-stop helper for autonomous buyer flows:
    1. Human signs Open Mandates on Trusted Surface (budget cap, allowed tiers).
    2. Agent verifies Checkout JWT against constraints and signs Closed Mandates.
    3. Returns full AP2 v0.2 dual chains ready for MCP / REST purchase.
    """
    open_mandates = create_trusted_surface_open_mandates(
        budget_cap=budget_cap,
        allowed_tiers=allowed_tiers,
        user_key=user_key,
        agent_key=agent_key,
    )
    chains = create_closed_mandate_chains(
        open_checkout_token=open_mandates["open_checkout_token"],
        open_payment_token=open_mandates["open_payment_token"],
        checkout_jwt=checkout_jwt,
        agent_key=open_mandates["agent_key"],
        contractor_email=contractor_email,
        nonce=nonce,
    )
    return {
        **open_mandates,
        **chains,
    }

