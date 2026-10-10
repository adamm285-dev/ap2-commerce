"""
Comprehensive Security PoC Regression Tests for AP2 v0.2 Protocol.
Addresses all 7 security and compliance findings verified by Claude:
1. Root key forgery protection (self-asserted jwk, unregistered kid, agent key as root, buyer_email binding)
2. Closed-mandate integrity checks (payment amount, currency, payee ID)
3. Authoritative budget cap from signed Open Mandate chains (cluster at $179.99 under $200 cap)
4. Robust exception handling (no unhandled 500s on malformed or bad tokens)
5. Enforce Key Binding Nonce & Aud
"""

import json
import pytest
from jwcrypto.jwk import JWK

from ap2.sdk.checkout_mandate_chain import CheckoutMandateChain
from ap2.sdk.generated.checkout_mandate import CheckoutMandate
from ap2.sdk.generated.open_checkout_mandate import AllowedMerchants, OpenCheckoutMandate
from ap2.sdk.generated.open_payment_mandate import AllowedPayees, AmountRange, OpenPaymentMandate
from ap2.sdk.generated.payment_mandate import PaymentMandate
from ap2.sdk.generated.types.amount import Amount
from ap2.sdk.generated.types.merchant import Merchant
from ap2.sdk.generated.types.payment_instrument import PaymentInstrument
from ap2.sdk.jwt_helper import create_jwt, verify_jwt
from ap2.sdk.mandate import MandateClient
from ap2.sdk.payment_mandate_chain import PaymentMandateChain

from backend.agents.seller_agent import seller_agent
from backend.config import settings
from backend.database import register_buyer_key
from backend.services.ap2_keys import (
    get_demo_agent_key,
    get_demo_user_key,
    get_merchant_public_key,
    jwk_to_cnf,
)
from backend.services.ap2_service import (
    AP2_MERCHANT_ID,
    AP2_MERCHANT_NAME,
    ERR_INVALID_CREDENTIAL,
    ERR_INVALID_MANDATE,
    compute_checkout_hash,
    create_merchant_checkout,
    resolve_root_public_key,
    verify_ap2_chains,
    verify_receipt_jwt,
)


def _build_test_chains_custom(
    user_key: JWK,
    agent_key: JWK,
    tier_id: str = "ap2-gateway",
    price_cents: int = 7999,
    monthly_price: float = 79.99,
    max_cap_cents: int = 10000,
    contractor_email: str = "agent-alpha@example.com",
    nonce: str | None = None,
    aud: str = AP2_MERCHANT_ID,
    payee_id: str = AP2_MERCHANT_ID,
    pay_amount_cents: int | None = None,
    pay_currency: str = "USD",
):
    """Flexible test harness for building AP2 v0.2 dual chains with configurable properties."""
    mandate_client = MandateClient()
    agent_cnf = jwk_to_cnf(agent_key)

    chk_record = create_merchant_checkout(
        tier_id=tier_id,
        monthly_price=monthly_price,
        contractor_email=contractor_email,
    )
    checkout_jwt = chk_record["checkout_jwt"]
    checkout_hash = chk_record["checkout_hash"]
    checkout_nonce = nonce or chk_record.get("nonce", "nonce_default_test")

    open_chk = OpenCheckoutMandate(
        vct="mandate.checkout.open.1",
        cnf=agent_cnf,
        constraints=[
            AllowedMerchants(allowed=[Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME)]),
        ],
    )
    open_chk_tok = mandate_client.create(issuer_key=user_key, payloads=[open_chk])

    closed_chk = CheckoutMandate(
        vct="mandate.checkout.1",
        checkout_jwt=checkout_jwt,
        checkout_hash=checkout_hash,
    )
    chk_chain = mandate_client.present(
        holder_key=agent_key,
        mandate_token=open_chk_tok,
        payloads=[closed_chk],
        aud=aud,
        nonce=checkout_nonce,
    )

    open_pay = OpenPaymentMandate(
        vct="mandate.payment.open.1",
        cnf=agent_cnf,
        constraints=[
            AmountRange(currency="USD", min=1, max=max_cap_cents),
            AllowedPayees(allowed=[Merchant(id=AP2_MERCHANT_ID, name=AP2_MERCHANT_NAME)]),
        ],
    )
    open_pay_tok = mandate_client.create(issuer_key=user_key, payloads=[open_pay])

    actual_pay_cents = pay_amount_cents if pay_amount_cents is not None else price_cents
    closed_pay = PaymentMandate(
        vct="mandate.payment.1",
        transaction_id=checkout_hash,
        payment_amount=Amount(amount=actual_pay_cents, currency=pay_currency),
        payee=Merchant(id=payee_id, name=AP2_MERCHANT_NAME),
        payment_instrument=PaymentInstrument(
            type="paypal_vault",
            id=f"vault_{contractor_email}",
        ),
    )
    pay_chain = mandate_client.present(
        holder_key=agent_key,
        mandate_token=open_pay_tok,
        payloads=[closed_pay],
        aud=aud,
        nonce=checkout_nonce,
    )

    return chk_chain, pay_chain, checkout_jwt, checkout_hash, checkout_nonce


# ── 1. Root Key Forgery & Binding Tests ───────────────────────────────────────

@pytest.mark.parametrize("mock_mode", [True, False])
def test_reject_self_asserted_jwk_in_token_header(monkeypatch, mock_mode):
    """
    Security PoC 1a: Attackers must NOT be able to forge trust roots by embedding
    a self-asserted 'jwk' in the open mandate token header.
    Must return invalid_credential in both mock and live mode.
    """
    monkeypatch.setattr(settings, "mock_external_apis", mock_mode)

    attacker_key = JWK.generate(kty="EC", crv="P-256", kid="attacker-injected-jwk")
    agent_key = get_demo_agent_key()

    chk_chain, pay_chain, chk_jwt, chk_hash, nonce = _build_test_chains_custom(
        user_key=attacker_key,
        agent_key=agent_key,
    )

    res = verify_ap2_chains(
        checkout_mandate_token=chk_chain,
        payment_mandate_token=pay_chain,
        checkout_jwt=chk_jwt,
        expected_nonce=nonce,
        enforce_replay_defense=False,
    )

    assert res["valid"] is False
    assert res["error"] == ERR_INVALID_CREDENTIAL
    assert res["checkout_receipt"] is not None
    rec = verify_receipt_jwt(res["checkout_receipt"])
    assert rec["status"] == "Error"
    assert rec["error"] == ERR_INVALID_CREDENTIAL


@pytest.mark.parametrize("mock_mode", [True, False])
def test_reject_unregistered_kid(monkeypatch, mock_mode):
    """
    Security PoC 1b: Unregistered key IDs must be rejected with invalid_credential
    in both mock and live mode.
    """
    monkeypatch.setattr(settings, "mock_external_apis", mock_mode)

    unreg_key = JWK.generate(kty="EC", crv="P-256", kid="unknown-unregistered-key-id")
    agent_key = get_demo_agent_key()

    chk_chain, pay_chain, chk_jwt, chk_hash, nonce = _build_test_chains_custom(
        user_key=unreg_key,
        agent_key=agent_key,
    )

    res = verify_ap2_chains(
        checkout_mandate_token=chk_chain,
        payment_mandate_token=pay_chain,
        checkout_jwt=chk_jwt,
        expected_nonce=nonce,
        enforce_replay_defense=False,
    )

    assert res["valid"] is False
    assert res["error"] == ERR_INVALID_CREDENTIAL


@pytest.mark.parametrize("mock_mode", [True, False])
def test_reject_agent_key_used_as_root(monkeypatch, mock_mode):
    """
    Security PoC 1c: Agent keys sign only closed mandates; an agent key must
    NEVER be accepted as a root issuer for an Open Mandate.
    """
    monkeypatch.setattr(settings, "mock_external_apis", mock_mode)

    agent_key = get_demo_agent_key()

    chk_chain, pay_chain, chk_jwt, chk_hash, nonce = _build_test_chains_custom(
        user_key=agent_key,
        agent_key=agent_key,
    )

    res = verify_ap2_chains(
        checkout_mandate_token=chk_chain,
        payment_mandate_token=pay_chain,
        checkout_jwt=chk_jwt,
        expected_nonce=nonce,
        enforce_replay_defense=False,
    )

    assert res["valid"] is False
    assert res["error"] == ERR_INVALID_CREDENTIAL
    assert "Agent keys sign only closed mandates" in res["error_description"]


@pytest.mark.parametrize("mock_mode", [True, False])
def test_reject_buyer_email_binding_mismatch(monkeypatch, mock_mode):
    """
    Security PoC 1d: When a key is registered in buyer_keys, the purchase's
    buyer_email must match the registered email bound to that key.
    """
    monkeypatch.setattr(settings, "mock_external_apis", mock_mode)

    # Register Bob's key
    bob_key = JWK.generate(kty="EC", crv="P-256", kid="registered-bob-key")
    bob_pub_json = bob_key.export_public()
    register_buyer_key(
        kid="registered-bob-key",
        public_key_hex=bob_pub_json,
        contractor_email="bob@example.com",
        business_name="Bob Systems",
    )

    agent_key = get_demo_agent_key()

    chk_chain, pay_chain, chk_jwt, chk_hash, nonce = _build_test_chains_custom(
        user_key=bob_key,
        agent_key=agent_key,
        contractor_email="bob@example.com",
    )

    # 1. Attacker attempts purchase for mallory@example.com using Bob's key
    res_mismatch = verify_ap2_chains(
        checkout_mandate_token=chk_chain,
        payment_mandate_token=pay_chain,
        checkout_jwt=chk_jwt,
        expected_nonce=nonce,
        enforce_replay_defense=False,
        buyer_email="mallory@example.com",
    )
    assert res_mismatch["valid"] is False
    assert res_mismatch["error"] == ERR_INVALID_CREDENTIAL
    assert "EMAIL_KEY_BINDING_MISMATCH" in res_mismatch["error_description"]

    # 2. Legitimate purchase matching registered email succeeds
    res_match = verify_ap2_chains(
        checkout_mandate_token=chk_chain,
        payment_mandate_token=pay_chain,
        checkout_jwt=chk_jwt,
        expected_nonce=nonce,
        enforce_replay_defense=False,
        buyer_email="bob@example.com",
    )
    assert res_match["valid"] is True


# ── 2. Closed-Mandate Integrity Checks ───────────────────────────────────────

def test_reject_closed_mandate_payment_amount_tamper():
    """
    Security PoC 2a: Reject payment mandate paying 1 cent on a $179.99 checkout.
    Must return valid=False, error=invalid_mandate, and signed error receipt.
    """
    user_key = get_demo_user_key()
    agent_key = get_demo_agent_key()

    chk_chain, pay_chain, chk_jwt, chk_hash, nonce = _build_test_chains_custom(
        user_key=user_key,
        agent_key=agent_key,
        tier_id="ap2-cluster",
        price_cents=17999,
        monthly_price=179.99,
        max_cap_cents=20000,
        pay_amount_cents=1,  # 1 cent attack on $179.99
    )

    res = verify_ap2_chains(
        checkout_mandate_token=chk_chain,
        payment_mandate_token=pay_chain,
        checkout_jwt=chk_jwt,
        expected_nonce=nonce,
        enforce_replay_defense=False,
    )

    assert res["valid"] is False
    assert res["error"] == ERR_INVALID_MANDATE
    assert "PAYMENT_AMOUNT_MISMATCH" in res["error_description"]
    assert res["payment_receipt"] is not None
    pay_rec = verify_receipt_jwt(res["payment_receipt"])
    assert pay_rec["status"] == "Error"
    assert pay_rec["error"] == ERR_INVALID_MANDATE


def test_reject_closed_mandate_currency_mismatch():
    """Security PoC 2b: Reject payment mandate with mismatched currency."""
    user_key = get_demo_user_key()
    agent_key = get_demo_agent_key()

    chk_chain, pay_chain, chk_jwt, chk_hash, nonce = _build_test_chains_custom(
        user_key=user_key,
        agent_key=agent_key,
        tier_id="ap2-gateway",
        price_cents=7999,
        monthly_price=79.99,
        max_cap_cents=10000,
        pay_currency="EUR",  # Mismatched currency
    )

    res = verify_ap2_chains(
        checkout_mandate_token=chk_chain,
        payment_mandate_token=pay_chain,
        checkout_jwt=chk_jwt,
        expected_nonce=nonce,
        enforce_replay_defense=False,
    )

    assert res["valid"] is False
    assert res["error"] == ERR_INVALID_MANDATE
    assert "currency mismatch" in res["error_description"].lower()


def test_reject_closed_mandate_payee_mismatch():
    """Security PoC 2c: Reject payment mandate paying some-other-merchant."""
    user_key = get_demo_user_key()
    agent_key = get_demo_agent_key()

    chk_chain, pay_chain, chk_jwt, chk_hash, nonce = _build_test_chains_custom(
        user_key=user_key,
        agent_key=agent_key,
        tier_id="ap2-gateway",
        price_cents=7999,
        monthly_price=79.99,
        max_cap_cents=10000,
        payee_id="some-other-merchant",  # Foreign payee
    )

    res = verify_ap2_chains(
        checkout_mandate_token=chk_chain,
        payment_mandate_token=pay_chain,
        checkout_jwt=chk_jwt,
        expected_nonce=nonce,
        enforce_replay_defense=False,
    )

    assert res["valid"] is False
    assert res["error"] == ERR_INVALID_MANDATE
    assert "payee" in res["error_description"].lower()


# ── 3. Authoritative Budget Cap Tests ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_cluster_tier_purchase_succeeds_under_adequate_signed_cap():
    """
    Security PoC 3a: An ap2-cluster purchase ($179.99) succeeds when the human
    signed an open mandate with a $200.00 cap (authoritative cap extracted from chain).
    """
    user_key = get_demo_user_key()
    agent_key = get_demo_agent_key()

    chk_chain, pay_chain, chk_jwt, chk_hash, nonce = _build_test_chains_custom(
        user_key=user_key,
        agent_key=agent_key,
        tier_id="ap2-cluster",
        price_cents=17999,
        monthly_price=179.99,
        max_cap_cents=20000,  # $200 cap > $179.99
        contractor_email="cluster-buyer@example.com",
    )

    pur = await seller_agent.purchase_subscription(
        buyer_email="cluster-buyer@example.com",
        checkout_mandate_chain=chk_chain,
        payment_mandate_chain=pay_chain,
        checkout_jwt=chk_jwt,
        nonce=nonce,
    )

    assert pur["status"] == "ACTIVE"
    assert pur["tier_id"] == "ap2-cluster"
    assert pur["agreed_monthly_rate"] == 179.99
    assert pur["checkout_receipt"] is not None
    assert pur["payment_receipt"] is not None


@pytest.mark.asyncio
async def test_cluster_tier_purchase_rejected_when_cap_below_price():
    """
    Security PoC 3b: An ap2-cluster purchase ($179.99) is rejected with invalid_mandate
    when the human signed an open mandate with a $100.00 cap.
    """
    user_key = get_demo_user_key()
    agent_key = get_demo_agent_key()

    chk_chain, pay_chain, chk_jwt, chk_hash, nonce = _build_test_chains_custom(
        user_key=user_key,
        agent_key=agent_key,
        tier_id="ap2-cluster",
        price_cents=17999,
        monthly_price=179.99,
        max_cap_cents=10000,  # $100 cap < $179.99
        contractor_email="cluster-low-cap@example.com",
    )

    pur = await seller_agent.purchase_subscription(
        buyer_email="cluster-low-cap@example.com",
        checkout_mandate_chain=chk_chain,
        payment_mandate_chain=pay_chain,
        checkout_jwt=chk_jwt,
        nonce=nonce,
    )

    assert pur["status"] == "REJECTED"
    assert pur["error"] == ERR_INVALID_MANDATE


# ── 4. Robust Exception Handling Tests ───────────────────────────────────────

def test_verify_ap2_chains_malformed_token_boundary():
    """
    Security PoC 4: Passing malformed or corrupted tokens must return
    valid=False, error=invalid_credential with signed error receipt, never an unhandled 500.
    """
    res = verify_ap2_chains(
        checkout_mandate_token="not.a.valid.jwt.token~~gibberish",
        payment_mandate_token="also.not.valid~~garbage",
        checkout_jwt=None,
    )
    assert res["valid"] is False
    assert res["error"] == ERR_INVALID_MANDATE  # Missing checkout_jwt early guard
    assert res["checkout_receipt"] is not None

    # Even with random strings for all inputs
    res2 = verify_ap2_chains(
        checkout_mandate_token="bad~~token",
        payment_mandate_token="bad~~token",
        checkout_jwt="eyJhbGciOiAiRVMyNTYiLCAidHlwIjogIkpXVCJ9.eyJpZCI6ICIxMjMifQ.bad_signature",
    )
    assert res2["valid"] is False
    assert res2["error"] == ERR_INVALID_CREDENTIAL
    assert res2["checkout_receipt"] is not None


# ── 5. Nonce & Aud Verification Tests ────────────────────────────────────────

def test_reject_tampered_or_wrong_nonce():
    """Security PoC 5a: Closed mandate Key Binding with mismatched nonce is rejected."""
    user_key = get_demo_user_key()
    agent_key = get_demo_agent_key()

    chk_chain, pay_chain, chk_jwt, chk_hash, nonce = _build_test_chains_custom(
        user_key=user_key,
        agent_key=agent_key,
        nonce="legitimate_nonce_1234",
    )

    # Verify with different expected_nonce
    res = verify_ap2_chains(
        checkout_mandate_token=chk_chain,
        payment_mandate_token=pay_chain,
        checkout_jwt=chk_jwt,
        expected_nonce="wrong_attacker_nonce_5678",
        enforce_replay_defense=False,
    )

    assert res["valid"] is False
    assert res["error"] == ERR_INVALID_CREDENTIAL
    assert res["checkout_receipt"] is not None


def test_reject_tampered_or_wrong_aud():
    """Security PoC 5b: Closed mandate Key Binding with wrong audience is rejected."""
    user_key = get_demo_user_key()
    agent_key = get_demo_agent_key()

    chk_chain, pay_chain, chk_jwt, chk_hash, nonce = _build_test_chains_custom(
        user_key=user_key,
        agent_key=agent_key,
        aud="wrong-attacker-aud",
    )

    res = verify_ap2_chains(
        checkout_mandate_token=chk_chain,
        payment_mandate_token=pay_chain,
        checkout_jwt=chk_jwt,
        expected_aud=AP2_MERCHANT_ID,
        expected_nonce=nonce,
        enforce_replay_defense=False,
    )

    assert res["valid"] is False
    assert res["error"] == ERR_INVALID_CREDENTIAL
