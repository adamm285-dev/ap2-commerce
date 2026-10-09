"""
Stage 2 Merchant Verification Tests.
Verifies AP2 v0.2 Merchant-side capabilities:
1. ES256-signed UCP / AP2 Checkout JWT issuance (standard and counter-offer).
2. Dual-chain verification using Google's AP2 reference SDK.
3. Merchant-signed Checkout Receipt and Payment Receipt JWT generation & validation.
4. Seller Agent tool integration (negotiate_tier_terms, purchase_subscription).
5. FastMCP / REST endpoints for JWKS, Checkouts, and Receipts.
"""

import json
import pytest
from fastapi.testclient import TestClient
from jwcrypto.jwk import JWK

from ap2.sdk.checkout_mandate_chain import CheckoutMandateChain
from ap2.sdk.generated.checkout_mandate import CheckoutMandate
from ap2.sdk.generated.open_checkout_mandate import AllowedMerchants, LineItems, OpenCheckoutMandate
from ap2.sdk.generated.open_payment_mandate import AllowedPayees, AmountRange, OpenPaymentMandate
from ap2.sdk.generated.payment_mandate import PaymentMandate
from ap2.sdk.generated.types.amount import Amount
from ap2.sdk.generated.types.item import Item
from ap2.sdk.generated.types.line_item import LineItem
from ap2.sdk.generated.types.merchant import Merchant
from ap2.sdk.generated.types.payment_instrument import PaymentInstrument
from ap2.sdk.generated.types.total import Total
from ap2.sdk.jwt_helper import verify_jwt
from ap2.sdk.mandate import MandateClient
from ap2.sdk.payment_mandate_chain import PaymentMandateChain

from backend.agents.seller_agent import seller_agent
from backend.server import app
from backend.services.ap2_keys import (
    get_demo_agent_key,
    get_demo_user_key,
    get_merchant_key,
    get_merchant_public_jwk,
    get_merchant_public_key,
    jwk_to_cnf,
)
from backend.services.ap2_service import (
    AP2_MERCHANT_ID,
    ERR_INVALID_CREDENTIAL,
    ERR_INVALID_MANDATE,
    compute_checkout_hash,
    create_checkout_receipt_jwt,
    create_merchant_checkout,
    create_merchant_counter_offer,
    create_payment_receipt_jwt,
    dollars_to_minor_units,
    minor_units_to_dollars,
    verify_ap2_chains,
    verify_receipt_jwt,
)

client = TestClient(app)


def test_minor_units_conversion():
    assert dollars_to_minor_units(79.99) == 7999
    assert dollars_to_minor_units(49.99) == 4999
    assert dollars_to_minor_units(179.99) == 17999
    assert minor_units_to_dollars(7999) == 79.99
    assert minor_units_to_dollars(4999) == 49.99


def test_merchant_checkout_jwt_issuance():
    """Verifies that the merchant creates an authentic ES256-signed Checkout JWT."""
    res = create_merchant_checkout(
        tier_id="ap2-gateway",
        monthly_price=79.99,
        contractor_email="buyer@example.com",
    )
    assert res["price_cents"] == 7999
    assert res["monthly_price"] == 79.99
    assert res["tier_id"] == "ap2-gateway"
    assert res["checkout_jwt"].count(".") == 2

    # Verify signature using merchant public key
    pub_key = get_merchant_public_key()
    payload = verify_jwt(res["checkout_jwt"], pub_key)
    assert payload["id"] == res["order_id"]
    assert payload["merchant"]["id"] == AP2_MERCHANT_ID
    assert payload["totals"][0]["amount"] == 7999
    assert payload["currency"] == "USD"


def test_merchant_counter_offer_checkout_jwt():
    """Verifies counter-offer Checkout JWT issuance with clear reasoning."""
    counter = create_merchant_counter_offer(
        requested_tier_id="ap2-gateway",
        counter_tier_id="ap2-batch",
        counter_price=49.99,
        budget_cap=60.00,
        contractor_email="buyer@example.com",
    )
    assert counter["tier_id"] == "ap2-batch"
    assert counter["price_cents"] == 4999
    assert counter["is_counter_offer"] is True

    pub_key = get_merchant_public_key()
    payload = verify_jwt(counter["checkout_jwt"], pub_key)
    assert payload["is_counter_offer"] is True
    assert "counter_reason" in payload
    assert "ap2-batch" in payload["counter_reason"]


def test_merchant_receipts_conformance():
    """Verifies Success and Error receipts conforming to Google AP2 SDK schema."""
    ref = "ref_test_001"
    chk_success = create_checkout_receipt_jwt(
        order_id="chk_123",
        closed_mandate_reference=ref,
        status="Success",
    )
    chk_payload = verify_receipt_jwt(chk_success)
    assert chk_payload["status"] == "Success"
    assert chk_payload["order_id"] == "chk_123"
    assert chk_payload["reference"] == ref

    pay_success = create_payment_receipt_jwt(
        payment_id="pay_999",
        closed_mandate_reference=ref,
        status="Success",
    )
    pay_payload = verify_receipt_jwt(pay_success)
    assert pay_payload["status"] == "Success"
    assert pay_payload["payment_id"] == "pay_999"

    # Error receipt
    chk_error = create_checkout_receipt_jwt(
        order_id="chk_123",
        closed_mandate_reference=ref,
        status="Error",
        error=ERR_INVALID_MANDATE,
        error_description="Constraint violated: Amount exceeds cap",
    )
    err_payload = verify_receipt_jwt(chk_error)
    assert err_payload["status"] == "Error"
    assert err_payload["error"] == ERR_INVALID_MANDATE
    assert "exceeds cap" in err_payload["error_description"]


def _build_test_chains(
    price_cents: int = 7999,
    max_cap_cents: int = 10000,
    tamper_price: bool = False,
):
    """Helper creating valid AP2 v0.2 checkout & payment mandate chains."""
    user_key = get_demo_user_key()
    agent_key = get_demo_agent_key()
    agent_cnf = jwk_to_cnf(agent_key)
    mandate_client = MandateClient()

    # 1. Merchant Checkout JWT
    dollars = minor_units_to_dollars(price_cents)
    chk_record = create_merchant_checkout(
        tier_id="ap2-gateway",
        monthly_price=dollars,
        contractor_email="buyer@example.com",
    )
    checkout_jwt = chk_record["checkout_jwt"]
    checkout_hash = chk_record["checkout_hash"]

    # 2. Open Checkout Mandate (signed by User / Trusted Surface)
    open_chk = OpenCheckoutMandate(
        vct="mandate.checkout.open.1",
        cnf=agent_cnf,
        constraints=[
            AllowedMerchants(allowed=[Merchant(id=AP2_MERCHANT_ID, name="AP2 Autonomous Node Network")]),
        ],
    )
    open_chk_tok = mandate_client.create(
        issuer_key=user_key,
        payloads=[open_chk],
    )

    # 3. Closed Checkout Mandate (signed by Agent)
    closed_chk_hash = checkout_hash if not tamper_price else compute_checkout_hash("tampered_checkout")
    closed_chk = CheckoutMandate(
        vct="mandate.checkout.1",
        checkout_jwt=checkout_jwt,
        checkout_hash=closed_chk_hash,
    )
    chk_chain = mandate_client.present(
        holder_key=agent_key,
        mandate_token=open_chk_tok,
        payloads=[closed_chk],
        aud=AP2_MERCHANT_ID,
        nonce="test_nonce_checkout",
    )

    # 4. Open Payment Mandate (signed by User)
    open_pay = OpenPaymentMandate(
        vct="mandate.payment.open.1",
        cnf=agent_cnf,
        constraints=[
            AmountRange(currency="USD", min=1, max=max_cap_cents),
            AllowedPayees(allowed=[Merchant(id=AP2_MERCHANT_ID, name="AP2 Autonomous Node Network")]),
        ],
    )
    open_pay_tok = mandate_client.create(
        issuer_key=user_key,
        payloads=[open_pay],
    )

    # 5. Closed Payment Mandate (signed by Agent)
    closed_pay = PaymentMandate(
        vct="mandate.payment.1",
        transaction_id=checkout_hash,
        payment_amount=Amount(amount=price_cents, currency="USD"),
        payee=Merchant(id=AP2_MERCHANT_ID, name="AP2 Autonomous Node Network"),
        payment_instrument=PaymentInstrument(type="paypal_vault", id="vault_demo_01"),
    )
    pay_chain = mandate_client.present(
        holder_key=agent_key,
        mandate_token=open_pay_tok,
        payloads=[closed_pay],
        aud=AP2_MERCHANT_ID,
        nonce="test_nonce_payment",
    )

    return chk_chain, pay_chain, checkout_jwt, checkout_hash


def test_verify_ap2_chains_success():
    """End-to-end verification of valid dual AP2 v0.2 chains."""
    chk_chain, pay_chain, chk_jwt, chk_hash = _build_test_chains(price_cents=7999, max_cap_cents=10000)
    res = verify_ap2_chains(
        checkout_mandate_token=chk_chain,
        payment_mandate_token=pay_chain,
        checkout_jwt=chk_jwt,
        enforce_replay_defense=False,
    )
    assert res["valid"] is True
    assert res["monthly_price"] == 79.99
    assert res["price_cents"] == 7999
    assert res["checkout_receipt"] is not None
    assert res["payment_receipt"] is not None

    # Verify receipts
    chk_rec = verify_receipt_jwt(res["checkout_receipt"])
    assert chk_rec["status"] == "Success"
    pay_rec = verify_receipt_jwt(res["payment_receipt"])
    assert pay_rec["status"] == "Success"


def test_verify_ap2_chains_budget_exceeded():
    """Constraint violation: Price exceeds the human-authorized AmountRange max."""
    chk_chain, pay_chain, chk_jwt, chk_hash = _build_test_chains(price_cents=7999, max_cap_cents=6000)
    res = verify_ap2_chains(
        checkout_mandate_token=chk_chain,
        payment_mandate_token=pay_chain,
        checkout_jwt=chk_jwt,
        enforce_replay_defense=False,
    )
    assert res["valid"] is False
    assert res["error"] == ERR_INVALID_MANDATE
    assert "exceeds maximum 6000" in res["error_description"]
    assert res["payment_receipt"] is not None


def test_verify_ap2_chains_price_tamper():
    """Hash mismatch rejection: Closed mandate checkout_hash does not match Checkout JWT."""
    chk_chain, pay_chain, chk_jwt, chk_hash = _build_test_chains(price_cents=7999, max_cap_cents=10000, tamper_price=True)
    res = verify_ap2_chains(
        checkout_mandate_token=chk_chain,
        payment_mandate_token=pay_chain,
        checkout_jwt=chk_jwt,
        enforce_replay_defense=False,
    )
    assert res["valid"] is False
    assert res["error"] == ERR_INVALID_MANDATE
    assert "checkout_hash mismatch" in res["error_description"]


def test_verify_ap2_chains_replay_defense():
    """Replay defense: Re-presenting an already redeemed closed mandate reference fails."""
    chk_chain, pay_chain, chk_jwt, chk_hash = _build_test_chains(price_cents=7999, max_cap_cents=10000)
    res1 = verify_ap2_chains(
        checkout_mandate_token=chk_chain,
        payment_mandate_token=pay_chain,
        checkout_jwt=chk_jwt,
        enforce_replay_defense=True,
    )
    assert res1["valid"] is True

    # Replay
    res2 = verify_ap2_chains(
        checkout_mandate_token=chk_chain,
        payment_mandate_token=pay_chain,
        checkout_jwt=chk_jwt,
        enforce_replay_defense=True,
    )
    assert res2["valid"] is False
    assert res2["error"] == ERR_INVALID_MANDATE
    assert "REPLAY_DETECTED" in res2["error_description"]


@pytest.mark.asyncio
async def test_seller_agent_negotiate_returns_checkout_jwt():
    """Verifies that seller_agent.negotiate_tier_terms attaches Checkout JWT & hash."""
    neg = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="buyer-001",
        tier_id="ap2-gateway",
        monthly_budget_cap=100.0,
        buyer_email="buyer-stage2@example.com",
    )
    assert neg["status"] == "APPROVED"
    assert "checkout_jwt" in neg
    assert "checkout_hash" in neg
    assert "order_id" in neg
    assert "checkout_jwt" in neg["next_action"]["parameters"]


@pytest.mark.asyncio
async def test_seller_agent_counter_offer_returns_counter_checkout_jwt():
    """Verifies that over-budget negotiation returns counter-offer Checkout JWT for ap2-batch at $49.99."""
    neg = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="buyer-001",
        tier_id="ap2-gateway",
        monthly_budget_cap=60.0,
        buyer_email="buyer-stage2-counter@example.com",
    )
    assert neg["status"] == "COUNTER_OFFER"
    assert neg["counter_offer_amount"] == 49.99
    assert "checkout_jwt" in neg
    assert "counter_offer_checkout_jwt" in neg
    assert neg["next_action"]["parameters"]["agreed_monthly_rate"] == 49.99


@pytest.mark.asyncio
async def test_seller_agent_purchase_with_chains():
    """Verifies that seller_agent.purchase_subscription accepts and verifies AP2 v0.2 chains."""
    chk_chain, pay_chain, chk_jwt, chk_hash = _build_test_chains(price_cents=7999, max_cap_cents=10000)
    pur = await seller_agent.purchase_subscription(
        buyer_email="buyer-stage2-chains@example.com",
        checkout_mandate_chain=chk_chain,
        payment_mandate_chain=pay_chain,
        checkout_jwt=chk_jwt,
    )
    assert pur["status"] == "ACTIVE"
    assert pur["agreed_monthly_rate"] == 79.99
    assert "checkout_receipt" in pur
    assert "payment_receipt" in pur

    # Verify receipts returned by seller_agent
    chk_rec = verify_receipt_jwt(pur["checkout_receipt"])
    assert chk_rec["status"] == "Success"
    pay_rec = verify_receipt_jwt(pur["payment_receipt"])
    assert pay_rec["status"] == "Success"


def test_rest_endpoints_jwks_and_receipts():
    """Tests /api/agent/keys/jwks.json, /api/checkout/{order_id}, and /api/receipts/{reference}."""
    # 1. JWKS
    jwks_res = client.get("/.well-known/jwks.json")
    assert jwks_res.status_code == 200
    keys = jwks_res.json()["keys"]
    assert len(keys) >= 1
    assert keys[0]["kty"] == "EC"
    assert keys[0]["crv"] == "P-256"

    # 2. Checkout lookup
    chk = create_merchant_checkout("ap2-batch", 49.99, "test@example.com")
    chk_res = client.get(f"/api/checkout/{chk['order_id']}")
    assert chk_res.status_code == 200
    assert chk_res.json()["tier_id"] == "ap2-batch"

    # 3. Receipt lookup
    ref = f"ref_{chk['order_id']}"
    rec_jwt = create_checkout_receipt_jwt(chk["order_id"], ref, "Success")
    rec_res = client.get(f"/api/receipts/{ref}")
    assert rec_res.status_code == 200
    assert rec_res.json()["receipt"]["status"] == "Success"

    # Direct JWT verification via query param
    verify_res = client.get(f"/api/receipts/{ref}?jwt={rec_jwt}")
    assert verify_res.status_code == 200
    assert verify_res.json()["receipt"]["status"] == "Success"
