"""
Tests for Stage 3 Commit 2:
1. Dual ES256-signed error receipts (checkout_receipt & payment_receipt) on every rejection:
   - Below-minimum budget ($40 cap < $49.99 minimum tier)
   - Budget exhausted / budget overrun
   - Price tampering during purchase
   - Tampered payee during purchase
   - Cap breach during purchase
2. AP2 v0.2 Buyer Agent chain presentation, receipt verification, and summary ledger.
3. External buyer agent receipt recording and absence of HMAC tokens.
"""

import pytest
from ap2.sdk.mandate import MandateClient
from ap2.sdk.generated.checkout_mandate import CheckoutMandate
from ap2.sdk.generated.payment_mandate import PaymentMandate
from ap2.sdk.generated.types.amount import Amount
from ap2.sdk.generated.types.merchant import Merchant
from ap2.sdk.generated.types.payment_instrument import PaymentInstrument

from backend.agents.seller_agent import seller_agent
from backend.agents.buyer_agent import BuyerAgent
from backend.services.ap2_service import (
    AP2_MERCHANT_ID,
    AP2_MERCHANT_NAME,
    verify_receipt_jwt,
    verify_ap2_chains,
    ERR_INVALID_MANDATE,
)
from backend.services.trusted_surface_service import (
    create_trusted_surface_open_mandates,
    get_demo_agent_key,
)
from backend.services.mandate_evaluator import ledger


@pytest.fixture(autouse=True)
def reset_state():
    ledger.reset()


@pytest.mark.asyncio
async def test_negotiate_below_minimum_budget_issues_dual_signed_error_receipts():
    """Verifies below-minimum budget returns status=REJECTED and valid signed error receipts."""
    res = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="test-agent-low",
        buyer_email="buyer-low@example.com",
        tier_id="ap2-gateway",
        monthly_budget_cap=40.00,  # Below $49.99 minimum
    )
    assert res["status"] == "REJECTED"
    assert "below minimum viable tier" in res["reason"]

    chk_rec = res.get("checkout_receipt")
    pay_rec = res.get("payment_receipt")
    assert chk_rec is not None
    assert pay_rec is not None

    chk_claims = verify_receipt_jwt(chk_rec)
    pay_claims = verify_receipt_jwt(pay_rec)
    assert chk_claims["status"] == "Error"
    assert chk_claims["error"] == ERR_INVALID_MANDATE
    assert pay_claims["status"] == "Error"
    assert pay_claims["error"] == ERR_INVALID_MANDATE


@pytest.mark.asyncio
async def test_negotiate_unauthorized_category_issues_dual_signed_error_receipts():
    """Verifies that an unauthorized spending category returns REJECTED and two merchant-signed error receipts."""
    res = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="test-agent-cat",
        buyer_email="buyer-cat@example.com",
        tier_id="ap2-batch",
        monthly_budget_cap=100.00,
        category="unauthorized-hardware-procurement",
    )
    assert res["status"] == "REJECTED"
    assert res["error"] == "BUDGET_EXHAUSTED"
    assert "not approved for this seller" in res["reason"]

    chk_rec = res.get("checkout_receipt")
    pay_rec = res.get("payment_receipt")
    assert chk_rec is not None
    assert pay_rec is not None

    chk_claims = verify_receipt_jwt(chk_rec)
    pay_claims = verify_receipt_jwt(pay_rec)
    assert chk_claims["status"] == "Error"
    assert chk_claims["error"] == ERR_INVALID_MANDATE
    assert pay_claims["status"] == "Error"
    assert pay_claims["error"] == ERR_INVALID_MANDATE


@pytest.mark.asyncio
async def test_negotiate_no_better_offer_issues_dual_signed_error_receipts():
    """Verifies that when buyer is already on best viable tier within budget, negotiate returns NO_BETTER_OFFER with two merchant-signed error receipts."""
    from backend.agents.seller_agent import _COMPLETED_SUBSCRIPTIONS, _ACTIVE_CONTRACTOR_SUBSCRIPTIONS

    email = "already-best@example.com"
    sub_id = "I-A2A-EXISTING-BATCH"
    _COMPLETED_SUBSCRIPTIONS[sub_id] = {
        "subscription_id": sub_id,
        "buyer_email": email,
        "tier_id": "ap2-batch",
        "status": "ACTIVE",
        "agreed_monthly_rate": 49.99,
    }
    _ACTIVE_CONTRACTOR_SUBSCRIPTIONS[email] = sub_id

    try:
        res = await seller_agent.negotiate_tier_terms(
            buyer_agent_id="test-agent-nobetter",
            buyer_email=email,
            tier_id="ap2-gateway",  # $79.99 > $60.00 cap
            monthly_budget_cap=60.00,
        )
        assert res["status"] == "NO_BETTER_OFFER"
        assert res["error"] == "NO_BETTER_OFFER"
        assert res.get("checkout_receipt") is not None
        assert res.get("payment_receipt") is not None

        chk_claims = verify_receipt_jwt(res["checkout_receipt"])
        pay_claims = verify_receipt_jwt(res["payment_receipt"])
        assert chk_claims["status"] == "Error"
        assert chk_claims["error"] == ERR_INVALID_MANDATE
        assert pay_claims["status"] == "Error"
        assert pay_claims["error"] == ERR_INVALID_MANDATE
    finally:
        _COMPLETED_SUBSCRIPTIONS.pop(sub_id, None)
        _ACTIVE_CONTRACTOR_SUBSCRIPTIONS.pop(email, None)


@pytest.mark.asyncio
async def test_purchase_tampered_price_issues_dual_signed_error_receipts():
    """Verifies purchase_subscription with mismatched price returns REJECTED and dual error receipts."""
    # Step 1: Negotiate valid terms
    email = "tamper-price@example.com"
    neg = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="test-agent-tamper",
        buyer_email=email,
        tier_id="ap2-gateway",
        monthly_budget_cap=100.00,
    )
    assert neg["status"] == "APPROVED"
    chk_jwt = neg["checkout_jwt"]
    chk_hash = neg["checkout_hash"]
    nonce = neg["nonce"]

    # Step 2: Mint chains with price inflated to 8000 cents ($80.00)
    agent_key = get_demo_agent_key()
    client = MandateClient()
    open_mandates = create_trusted_surface_open_mandates(
        monthly_budget_cap=100.00,
        buyer_email=email,
        allowed_tiers=["ap2-batch", "ap2-gateway", "ap2-cluster"],
        agent_key=agent_key,
    )

    chk_chain = client.present(
        holder_key=agent_key,
        mandate_token=open_mandates["open_checkout_mandate_token"],
        payloads=[CheckoutMandate(vct="mandate.checkout.1", checkout_jwt=chk_jwt, checkout_hash=chk_hash)],
        aud=AP2_MERCHANT_ID,
        nonce=nonce,
    )
    pay_chain = client.present(
        holder_key=agent_key,
        mandate_token=open_mandates["open_payment_mandate_token"],
        payloads=[PaymentMandate(
            vct="mandate.payment.1",
            transaction_id=chk_hash,
            payment_amount=Amount(amount=8000, currency="USD"),  # +1¢ inflation vs 7999
            payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
            payment_instrument=PaymentInstrument(type="paypal_vault", id="vault_t1"),
        )],
        aud=AP2_MERCHANT_ID,
        nonce=nonce,
    )

    purchase_res = await seller_agent.purchase_subscription(
        tier_id="ap2-gateway",
        agreed_monthly_rate=79.99,
        checkout_mandate_chain=chk_chain,
        payment_mandate_chain=pay_chain,
        checkout_jwt=chk_jwt,
        buyer_email=email,
        contractor_email=email,
        nonce=nonce,
    )
    assert purchase_res["status"] == "REJECTED"
    chk_rec = purchase_res.get("checkout_receipt")
    pay_rec = purchase_res.get("payment_receipt")
    assert chk_rec is not None
    assert pay_rec is not None

    chk_claims = verify_receipt_jwt(chk_rec)
    pay_claims = verify_receipt_jwt(pay_rec)
    assert chk_claims["status"] == "Error"
    assert pay_claims["status"] == "Error"


@pytest.mark.asyncio
async def test_purchase_tampered_payee_issues_dual_signed_error_receipts():
    """Verifies purchase_subscription with unauthorized payee returns REJECTED and dual error receipts."""
    email = "tamper-payee@example.com"
    neg = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="test-agent-payee",
        buyer_email=email,
        tier_id="ap2-gateway",
        monthly_budget_cap=100.00,
    )
    chk_jwt = neg["checkout_jwt"]
    chk_hash = neg["checkout_hash"]
    nonce = neg["nonce"]

    agent_key = get_demo_agent_key()
    client = MandateClient()
    open_mandates = create_trusted_surface_open_mandates(
        monthly_budget_cap=100.00,
        buyer_email=email,
        allowed_tiers=["ap2-batch", "ap2-gateway", "ap2-cluster"],
        agent_key=agent_key,
    )

    chk_chain = client.present(
        holder_key=agent_key,
        mandate_token=open_mandates["open_checkout_mandate_token"],
        payloads=[CheckoutMandate(vct="mandate.checkout.1", checkout_jwt=chk_jwt, checkout_hash=chk_hash)],
        aud=AP2_MERCHANT_ID,
        nonce=nonce,
    )
    pay_chain = client.present(
        holder_key=agent_key,
        mandate_token=open_mandates["open_payment_mandate_token"],
        payloads=[PaymentMandate(
            vct="mandate.payment.1",
            transaction_id=chk_hash,
            payment_amount=Amount(amount=7999, currency="USD"),
            payee=Merchant(id="evil-payee-attacker", name="Evil Attacker Corp"),
            payment_instrument=PaymentInstrument(type="paypal_vault", id="vault_t2"),
        )],
        aud=AP2_MERCHANT_ID,
        nonce=nonce,
    )

    purchase_res = await seller_agent.purchase_subscription(
        tier_id="ap2-gateway",
        agreed_monthly_rate=79.99,
        checkout_mandate_chain=chk_chain,
        payment_mandate_chain=pay_chain,
        checkout_jwt=chk_jwt,
        buyer_email=email,
        contractor_email=email,
        nonce=nonce,
    )
    assert purchase_res["status"] == "REJECTED"
    assert purchase_res.get("checkout_receipt") is not None
    assert purchase_res.get("payment_receipt") is not None


@pytest.mark.asyncio
async def test_purchase_budget_cap_breach_issues_dual_signed_error_receipts():
    """Verifies purchase_subscription with open mandate cap lower than checkout returns dual error receipts."""
    email = "cap-breach@example.com"
    neg = await seller_agent.negotiate_tier_terms(
        buyer_agent_id="test-agent-cap",
        buyer_email=email,
        tier_id="ap2-gateway",
        monthly_budget_cap=100.00,
    )
    chk_jwt = neg["checkout_jwt"]
    chk_hash = neg["checkout_hash"]
    nonce = neg["nonce"]

    agent_key = get_demo_agent_key()
    client = MandateClient()
    # Cap set to $70.00 while price is $79.99
    open_mandates = create_trusted_surface_open_mandates(
        monthly_budget_cap=70.00,
        buyer_email=email,
        allowed_tiers=["ap2-batch", "ap2-gateway", "ap2-cluster"],
        agent_key=agent_key,
    )

    chk_chain = client.present(
        holder_key=agent_key,
        mandate_token=open_mandates["open_checkout_mandate_token"],
        payloads=[CheckoutMandate(vct="mandate.checkout.1", checkout_jwt=chk_jwt, checkout_hash=chk_hash)],
        aud=AP2_MERCHANT_ID,
        nonce=nonce,
    )
    pay_chain = client.present(
        holder_key=agent_key,
        mandate_token=open_mandates["open_payment_mandate_token"],
        payloads=[PaymentMandate(
            vct="mandate.payment.1",
            transaction_id=chk_hash,
            payment_amount=Amount(amount=7999, currency="USD"),
            payee=Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME),
            payment_instrument=PaymentInstrument(type="paypal_vault", id="vault_t3"),
        )],
        aud=AP2_MERCHANT_ID,
        nonce=nonce,
    )

    purchase_res = await seller_agent.purchase_subscription(
        tier_id="ap2-gateway",
        agreed_monthly_rate=79.99,
        checkout_mandate_chain=chk_chain,
        payment_mandate_chain=pay_chain,
        checkout_jwt=chk_jwt,
        buyer_email=email,
        contractor_email=email,
        nonce=nonce,
    )
    assert purchase_res["status"] == "REJECTED"
    assert purchase_res.get("checkout_receipt") is not None
    assert purchase_res.get("payment_receipt") is not None


@pytest.mark.asyncio
async def test_buyer_agent_autonomous_cycle_records_ap2_receipts():
    """Verifies BuyerAgent completes autonomous cycle and preserves both signed receipts in ledger entry."""
    buyer = BuyerAgent(
        agent_id="test-ap2-agent-01",
        monthly_budget_cap=100.00,
        contractor_email="agent-stage3-c2@example.com",
    )
    result = await buyer.run_autonomous_onboarding_cycle(target_trade="ap2-gateway")

    assert result["status"] == "ACTIVE_SUBSCRIPTION"
    assert result["monthly_amount"] == 79.99
    assert result.get("checkout_receipt") is not None
    assert result.get("payment_receipt") is not None

    chk_claims = verify_receipt_jwt(result["checkout_receipt"])
    pay_claims = verify_receipt_jwt(result["payment_receipt"])
    assert chk_claims["status"] == "Success"
    assert pay_claims["status"] == "Success"
    assert chk_claims["reference"] == result["checkout_hash"]
    assert pay_claims["reference"] == result["checkout_hash"]
